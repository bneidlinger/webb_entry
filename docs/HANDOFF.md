# WebbWatch AI — Session Handoff & Context Primer

**Audience.** A Claude (or human engineer) opening this repo cold who needs to be production-effective inside one session. This document complements — does not replace — [`CLAUDE.md`](../CLAUDE.md) (per-session orientation) and [`webbwatch_ai_project_plan.md`](../webbwatch_ai_project_plan.md) (design source of truth). Read this once at the start of any meaningful work; it codifies *why*, *what we know*, and *what we deliberately don't*. Skim in 3 min; deep-read in 10. Length is the price of not repeating mistakes.

**Last updated.** End of Phase 4 (2026-05-25).

---

## 1. Project mental model (one paragraph)

WebbWatch AI is an **observatory-as-service** layer over public JWST data. STScI publishes JWST observations and their derived products through MAST (catalog/API) and the AWS Open Data program (file storage at `s3://stpubdata/jwst`). We poll those public surfaces, persist metadata in our own DB, run watchlist matching against newly-arrived products, generate deterministic previews/spectrum charts from FITS, and overlay an optional LLM "explainer" pass. Everything we *produce* (DB, previews, AI artifacts) lives in Azure; everything we *consume* (JWST data) is hosted by STScI on AWS and read anonymously. The product is a public discovery feed plus per-user watchlist alerts — the academic value-add is reducing time-to-awareness for newly public data without imposing on the MAST infrastructure.

---

## 2. Architectural invariants (don't re-litigate)

Each of these is a deliberate, load-bearing decision. Changing one cascades. Bring receipts before re-opening any of them.

| Invariant | Rationale | Where enforced |
|---|---|---|
| **Anonymous S3 reads from `stpubdata/jwst`** (botocore `UNSIGNED`) | The bucket is part of the AWS Open Data program — requesters don't need AWS accounts and Amazon eats egress. Adding IAM here would be both unnecessary and a deployment burden. | `services/worker/worker/jobs/s3_jwst_listing.py`; future Phase 3 FITS fetcher must do the same. |
| **Azure for our output, AWS for their input** | Pragmatic asymmetry: forcing JWST data to Azure first would 2× our egress for zero gain. Conversely, our previews/DB stay in the same cloud as compute. | `infra/docker-compose.yml`, `services/api/app/config.py` (split AWS/Azure env namespaces). |
| **`MastClient.assemble()` is the only place we touch astroquery Tables** | Astropy `Table` semantics (masked values, numpy scalars, MJD time) are sharp edges; isolating them keeps the rest of the codebase trivially unit-testable with dataclasses. | `services/api/app/clients/mast.py`. |
| **Ingest is idempotent on `(mast_obs_id)` and `(observation_id, filename)`** | MAST query results overlap by design (re-polling same instrument returns overlapping windows). Upsert keys make polling safe at any cadence. | `services/api/app/services/ingest.py:46-149`. |
| **Alerts fire on *create only*, never *update*** | A product is "new" iff its row is inserted, not updated. Re-ingesting an unchanged payload must not re-alert (user trust). | `services/api/app/services/ingest.py:130-135`; tested in `tests/test_alert_emission.py::test_re_ingest_does_not_re_alert`. |
| **Watchlist criteria: AND across keys, OR within a key** | This is the obvious interpretation of "want X and Y" with multi-valued slots ("any of these instruments"). Don't surprise users with implicit logic. | `services/api/app/services/match.py:55-`. |
| **Workers `pip install -e ../api`** | Avoids `packages/shared/` premature factoring. Both services import the *same* `app.*` namespace; the worker depends on the api, not vice versa. | `services/worker/pyproject.toml`, `services/worker/README.md`. |
| **`user_id="default"` hardcoded until Phase 8** | Auth is deferred; building multi-user data semantics now is speculative work. The string is the FK target everywhere. | `services/api/app/routes/watchlists.py:14`. |
| **Cadence: MAST 30 min, S3 6 h** | User-selected lighter cadence (vs plan default 15/60). JWST releases follow daily-ish science cadences anyway. | `services/worker/worker/config.py`. |
| **SQLite locally, Postgres in prod, same SQLAlchemy code** | No dialect-conditional model code. JSON columns use `sqlalchemy.JSON` (both backends support it). | `services/api/app/models/`. |
| **SNS endpoint default-off** | Until we have a public Azure Container Apps URL registered with AWS SNS, the endpoint serves 503 to refuse spoofed traffic. | `services/api/app/routes/webhooks.py:30-32`, `JWST_SNS_ENABLE` env flag. |
| **Preview-gen orchestration lives in `app.services.preview_job`** (api-side) | Worker is a thin re-export so RQ's dotted path still works, but tests in the api venv can drive `_run()` directly without standing up rq/redis or putting the worker package on sys.path. | `services/api/app/services/preview_job.py`; `services/worker/worker/jobs/preview_gen.py` (5-line shim). |
| **Previews enqueued only for watchlist-matched products** | User-selected to bound egress (FITS files 10–500 MB, AWS us-east-1 → Azure). All-products mode is a one-line change if Phase 4+ wants it. | `services/api/app/services/ingest.py` near `enqueue_preview_gen(prod.id, ...)`. |
| **Preview storage backend selected by env, not code change** | `LocalFilesystemStorage` when no Azure connection string is set (writes under `services/api/preview_cache/`, served via `/api/previews/{path}`); `AzureBlobStorage` otherwise. Lets dev work without Docker/Azurite. | `services/api/app/services/storage.py::get_preview_storage`. |
| **Analyses enqueued under the same gate as previews** | Same egress trade-off. Analyses are CPU-bound after fetch, so they re-pay the S3 cost rather than coupling to preview_job — clearer scheduling, separate retry semantics. | `services/api/app/services/ingest.py` near `enqueue_analyze_product(prod.id, ...)`. |
| **Analyzer dispatch is hardcoded; no plugin registry** | N=2 (image + spectrum). A registry adds indirection for hypothetical future analyzers we don't have requirements for. Cube (s3d) returns None from the dispatcher → job-layer skip. | `services/api/app/services/analysis/__init__.py::get_analyzer_for`. |
| **Reproducibility metadata lives inside `measurements_json`** | scipy/numpy/astropy versions + crds_context + calibration_version under `measurements_json["meta"]`. Keeps schema stable while letting future re-runs diff against past ones. | `services/api/app/services/analysis_job.py::_build_meta`. |
| **Version bumps preserve history; same-version re-runs overwrite** | Unique constraint on `(data_product_id, analyzer_name, analyzer_version)`. Re-running v1 is a no-op; bumping the analyzer to v2 creates a new row alongside v1 for diffing. API returns only the latest per analyzer name. | `services/api/app/models/data_product_analysis.py`; `services/api/app/routes/analyses.py`. |

---

## 3. Code map — where business logic actually lives

A topological reading order for a fresh session. Each line is a single read; no exploration needed.

```
services/api/app/
  config.py                        # All env vars. Read first.
  db.py                            # Engine + session_scope + get_session DI.
  main.py                          # FastAPI app + router registration.
  models/
    base.py                        # Declarative Base + TimestampMixin.
    observation.py, data_product.py  # Phase 1 schema.
    watchlist.py, alert.py          # Phase 2 schema.
    data_product_preview.py         # Phase 3 schema (one row per (product, variant)).
    data_product_analysis.py        # Phase 4 schema (one row per (product, analyzer, version)).
  clients/mast.py                  # Astroquery wrapper. assemble() is pure.
  services/
    ingest.py                      # Upsert + alert hook + preview/analysis enqueue. The hot path.
    match.py                       # Pure function: (product, obs, criteria) -> (bool, reason).
    alerts.py                      # evaluate_watchlists + deliver_pending_alerts.
    delivery/discord.py            # Webhook POST. Env-gated.
    sns.py                         # AWS SNS RSA signature verification.
    previews.py                    # Pure renderers: image / spectrum / cube → PNG bytes.
    preview_types.py               # Light: is_supported() + URL extraction. No matplotlib import.
    preview_job.py                 # Orchestration: fetch → render → upload → persist.
    analysis/                      # Phase 4: pure analyzers + dispatch.
      base.py                      # Analyzer protocol, AnalysisResult, AnalysisError.
      image.py                     # ImageAnalyzer (pixel stats + bg + source count).
      spectrum.py                  # SpectrumAnalyzer (wavelength/flux + peaks + SNR).
      __init__.py                  # get_analyzer_for(product_type) dispatch.
    analysis_types.py              # Light: is_analyzable(). No scipy import.
    analysis_job.py                # Orchestration: fetch → analyze → persist.
    storage.py                     # Local fs / Azure Blob backends.
    queue.py                       # Soft-import rq + best-effort enqueue (preview + analysis).
  routes/                          # FastAPI routers, one per resource.
    previews.py                    # Serves local-fs PNGs at /api/previews/{path}.
    analyses.py                    # GET /api/products/{id}/analysis.
  schemas/                         # Pydantic response models.
  cli/                             # Typer subcommands. Entry: python -m app

services/worker/worker/
  config.py                        # Worker-specific env.
  run.py                           # RQ worker entry + schedule bootstrap.
  schedule.py                      # rq-scheduler registration (idempotent).
  jobs/
    mast_poll.py                   # 30-min: walk instruments → ingest → deliver.
    s3_jwst_listing.py             # 6-h: anonymous list, detect unknown keys.
    preview_gen.py                 # Thin re-export of app.services.preview_job.generate_for_product.
    analyze_product.py             # Thin re-export of app.services.analysis_job.generate_analysis_for_product.

apps/web/
  app/page.tsx                     # Feed (server component).
  app/alerts/page.tsx              # Alerts (server component).
  app/products/[id]/page.tsx       # Phase 4 detail page (server component, parallel-fetches product + analysis).
  components/                      # ProductFeed, AlertFeed, HealthBadge.
  lib/api.ts                       # Typed fetch wrappers + Result<T>.
```

**Reading order recommendation for a deep understanding:** `config.py` → `models/*` → `clients/mast.py::assemble` → `services/ingest.py` → `services/match.py` → `services/alerts.py` → `routes/*` → `worker/jobs/*`. ~25 min cold.

---

## 4. JWST + MAST domain primer

Future work (Phase 3 onward) requires this to make non-naive choices. None of this lives in code yet, but every Phase 3 decision touches it.

### 4.1 The JWST data hierarchy

```
Program (proposal_id, e.g. "1234")
  └── Observation (mast_obs_id, "obsid" in MAST)
        └── Visit
              └── Exposure (a single integration sequence)
                    └── Detector readout
                          └── Data products (one per (detector, calibration_stage))
```

We model **Program → Observation → DataProduct** and elide Visit/Exposure (they're encoded in the filename). For most use cases this is sufficient; if Phase 5+ deterministic analysis needs visit grouping, decompose the filename rather than adding a model.

### 4.2 Calibration levels

JWST's Science Calibration Pipeline emits products at four levels. The MAST column is `calib_level` (we expose it on `MastProduct` but don't yet persist it — Phase 3 should fix this).

| Level | Suffix | What it is | Phase 3 relevance |
|---|---|---|---|
| 1 | `uncal` | Raw multi-accumulation ramps; ~GB. | Skip for previews — too heavy. |
| 2a | `rate`, `rateints` | Slope-fitted countrate frames after up-the-ramp fit. | Skip. |
| 2b | `cal`, `calints` | Flat-fielded, dark-subtracted single-exposure calibrated frames. | Possible preview source for imaging when no L3 exists. |
| 3 | `i2d`, `x1d`, `s2d`, `s3d`, `c1d` | Combined/extracted science-ready products. | **Primary preview target.** |

Product suffix → meaning (extends the `_PRODUCT_SUFFIX_RE` in `clients/mast.py`):

- **`i2d`** — combined 2D image (imaging). FITS image extension. Use `astropy.visualization.ZScaleInterval` + `AsinhStretch` for previews; never plot linearly.
- **`x1d`** — extracted 1D spectrum (single integration or combined). Binary table with `WAVELENGTH`, `FLUX`, `FLUX_ERROR`, `DQ` columns. Wavelength is in microns for IR instruments.
- **`c1d`** — combined 1D spectrum across exposures. Same structure as x1d.
- **`s2d`** — rectified 2D spectrum (slit-spectroscopy intermediate).
- **`s3d`** — IFU data cube (NIRSpec IFU, MIRI MRS). Three axes: (RA, Dec, λ).
- **`cat`** — source catalog (ECSV/CSV). Photometric or astrometric.
- **`segm`** — segmentation map (which pixels belong to which source).
- **`preview`** — pre-rendered preview (PNG/JPG). When present, prefer over generating our own — but they're not always available, especially for fresh releases.

### 4.3 MAST quirks worth knowing

- **`obsid` vs `obs_id`.** MAST has both. We key on `obsid` (numeric, unique). `obs_id` is a human-readable string like `jw01234001001_02101_00001`.
- **`instrument_name` is composite.** E.g. `"NIRCAM/IMAGE"`, `"MIRI/IFU"`. We split on `/` and store the instrument prefix only. The mode (`IMAGE`, `IFU`, `MRS`, `MOS`, `WFSS`) is in `filters` or derivable from suffix.
- **Time columns are MJD (Modified Julian Date).** Always convert via `astropy.time.Time(mjd, format="mjd", scale="utc")`. The `_mjd_to_datetime` helper in `clients/mast.py` does this. Never assume the column is ISO.
- **Wildcard `instrument_name="NIRCAM*"`.** Required to catch all NIRCam modes. Don't filter `==` against the bare instrument name — you'll miss most data.
- **`dataURI` may be `mast:` or `s3:` prefixed.** Both refer to the same file; the s3 form is what AWS Open Data exposes anonymously. `assemble()` already disambiguates into `cloud_uri` vs `mast_download_uri`.
- **Re-ingests overlap.** Polling NIRCam with `limit=100` returns the most recent 100 regardless of release date. Use `t_min` or `t_obs_release` to filter newly-released data when that matters.
- **CRDS context.** Calibration reference files have a versioned context string (`jwst_1234.pmap`). We have a `crds_context` column but don't populate it yet. Important for reproducibility audits — populate in Phase 3 from FITS headers.

### 4.4 The AWS Open Data side

- **Bucket:** `s3://stpubdata/jwst` in `us-east-1`. Anonymous reads via `botocore.UNSIGNED`.
- **Key layout:** `jwst/<program>/<observation>/<filename>` roughly; not strictly stable. Don't parse paths to derive identity — use the filename's `_<ptype>.fits` suffix and the JWST naming convention instead.
- **SNS topic:** `arn:aws:sns:us-east-1:879230861493:stpubdata/jwst` publishes notifications on object creation. Subscribing requires a public HTTPS endpoint that performs the AWS handshake (we have the endpoint; subscription itself is deferred until prod Azure URL exists).
- **Latency.** Empirically, new releases land in S3 first and become discoverable via MAST queries within minutes. The 30-min MAST poll is fine; SNS is the eventual upgrade path for sub-minute freshness.

### 4.5 astroquery surface (what we actually call)

```python
from astroquery.mast import Observations

# Query by criteria. Returns astropy.table.Table.
tbl = Observations.query_criteria(
    obs_collection="JWST",
    instrument_name="NIRCAM*",   # wildcard mandatory
    proposal_id="1234",          # optional
)

# Get per-observation products. Pass the obs Table directly.
products = Observations.get_product_list(tbl)
```

We deliberately do *not* use `Observations.download_products()` — Phase 3 will fetch FITS via boto3 to bypass MAST's egress and stay anonymous-S3 throughout.

### 4.6 FITS handling reference (Phase 3 prep)

The relevant astropy reading API:

```python
from astropy.io import fits
from astropy.wcs import WCS

with fits.open("jw...i2d.fits") as hdul:
    sci = hdul["SCI"].data           # 2D ndarray for imaging
    wcs = WCS(hdul["SCI"].header)    # World Coordinate System (RA/Dec ↔ pixel)
    pri = hdul[0].header             # primary header — instrument, filter, etc.
```

For spectra (`x1d.fits`):

```python
with fits.open("jw...x1d.fits") as hdul:
    spec = hdul[1].data              # FITS_rec; access as columns
    wavelength = spec["WAVELENGTH"]  # microns (IR) or angstroms — check TUNIT
    flux = spec["FLUX"]              # mJy or Jy — check TUNIT
```

**Units matter.** Always read the column's `TUNIT*` header and convert via `astropy.units` before plotting — flux densities can be mJy, MJy/sr, erg/s/cm²/Å, photlam, etc., depending on instrument and pipeline version.

**Imaging stretch.** Never display JWST images linearly — the dynamic range is enormous (faint extended emission + bright point sources). Use:

```python
from astropy.visualization import ZScaleInterval, AsinhStretch, ImageNormalize
norm = ImageNormalize(data, interval=ZScaleInterval(), stretch=AsinhStretch())
```

This matches what JWST QuickLook and `jdaviz` use.

---

## 5. Data model — canonical reference

Schema docs that don't fit in model file docstrings.

### `observations`
- `mast_obs_id` is the natural key (MAST `obsid`, numeric string).
- `instrument` is the prefix only (`"NIRCAM"` not `"NIRCAM/IMAGE"`).
- `ra`, `dec` are degrees, ICRS. Cone matching is haversine — accurate to sub-arcsecond at JWST resolution.
- `observation_date` is the start time (MJD `t_min`). `public_release_date` is `t_obs_release`.
- No exposure-level data; visit/exposure live in the filename.

### `data_products`
- Dedup key: `(observation_id, filename)`. MAST sometimes exposes the same file twice via `mast:` and `s3:` URIs — we collapse them.
- `product_type` is lowercase suffix (`i2d`, `x1d`, ...). `_PRODUCT_SUFFIX_RE` in `clients/mast.py` is the canonical list.
- `cloud_uri` always starts `s3://stpubdata/`. `mast_download_uri` is the portal fallback.
- `first_seen_at` is "when we noticed it"; `last_seen_at` updates on every re-ingest. These power Phase 2's "this is new" semantics.
- `calibration_version`, `crds_context` exist in the schema but are **not yet populated** — Phase 3 should extract from FITS headers.

### `watchlists`
- `criteria_json` is a free-form JSON blob. Schema validated *at the API boundary* (`schemas/watchlist.py`) but stored without validation, so adding a new criterion type is a one-file change to `match.py` plus a schema update.
- `user_id` is a literal string, currently always `"default"`.

### `alerts`
- One row per `(watchlist, data_product)` match. Multiple watchlists matching the same product create multiple rows.
- `delivery_status` is `{}` until `deliver_pending_alerts` runs; then it's `{"discord": {"status": "sent"|"skipped"|"error", "at": "..."}}`.
- `read_at` is null until the API's `POST /api/alerts/{id}/read` fires.
- `reason` is human text constructed by `match.matches()` — surface it in any UI, log line, or webhook payload.

### `data_product_previews` (Phase 3)
- One row per `(data_product_id, variant)`. Unique constraint enforces it.
- `variant` is `"full"` or `"thumbnail"` (constants in `app.services.previews`).
- `storage_uri` is null until rendering succeeds; non-null = the row is usable. Absolute URL for Azure Blob, `http://.../api/previews/{path}` for local fallback.
- Failure model: `attempts` JSON array records each attempt (`{at, error, permanent}`). `last_error` is the most recent message. `is_permanent_failure=True` makes the job skip this product forever (malformed FITS, missing SCI extension, unsupported type, 404 from S3). Transient failures (network, BotoCoreError) leave it False so a re-enqueue retries.
- `format` is `"png"` for now; the column exists so JPEG/WebP variants don't need a migration later.
- `calibration_version` and `crds_context` on `data_products` are populated as a side effect of preview generation (extracted from the primary header) — null only if generation never ran or the header lacked the keys.

### `data_product_analyses` (Phase 4)
- One row per `(data_product_id, analyzer_name, analyzer_version)`. Unique constraint enforces it.
- `analyzer_name` is `"image"` or `"spectrum"` (constants in the per-analyzer modules). Bumping `VERSION` in `image.py` / `spectrum.py` makes the next run create a new row alongside the old.
- `measurements_json` is null until analysis succeeds; non-null = the row is usable. Shape varies by `analyzer_name` — image analyzers include `kind: "image"` plus pixel/background/source-count fields; spectrum analyzers include `kind: "spectrum"` plus wavelength/flux/peak/SNR fields. Always includes `meta` with `scipy_version`, `numpy_version`, `astropy_version`, `calibration_version`, `crds_context` for reproducibility diffs.
- Failure model is identical to previews: `attempts` JSON, `last_error`, `is_permanent_failure`. Permanent: malformed FITS, missing extension, all-NaN data. Transient: S3 network errors after a successful URI parse.
- `calibration_version` and `crds_context` on `data_products` are populated by analysis as a side effect too (same `extract_calibration_metadata` helper from `previews.py`) — first one to run wins; neither preview_gen nor analysis_job overwrites an existing value.

---

## 6. What's deferred (and why) — read before assuming something is "missing"

Through Phase 3 we explicitly do *not* do these. If you find yourself wanting one, check the rationale before building.

- **Per-watchlist RSS tokens.** `/api/feed.rss` is public. Privacy lands with auth in Phase 8.
- **Acting on SNS Notifications.** Endpoint logs them but doesn't enqueue a targeted poll. Wire-up happens when the AWS subscription is registered.
- **Email delivery.** Skipped per user decision; Azure Communication Services is a half-day on its own.
- **S3 listing → ingest trigger.** The S3 job detects unknown keys but doesn't act on them. Phase 3+ should use this to drive a MAST re-poll for the program containing those keys, not to ingest from S3 directly (MAST has the metadata; S3 doesn't).
- **Multi-user data isolation.** No `user_id` filtering except watchlist scoping. Alerts table has no `user_id` (it inherits via `watchlist_id`).
- **Backfill.** Re-polling MAST with a larger `limit` will pull older data, but there's no "ingest everything from program X" CLI yet. Add when needed; the existing ingest function handles arbitrary input.
- **Auth.** No user model, no sessions, no API keys. CORS allows `localhost:3000`. The admin endpoint at `/api/admin/*` is unauthenticated — *fix before public deploy*.
- **Previews + analyses for non-watchlist-matched products.** Phase 3/4 only render/analyze for products that fire an Alert. The deterministic-first vision (plan §7) eventually wants both for all Level 3 products; switch by removing the `if new_alerts` gate in `ingest_observations` (single branch covers both enqueues).
- **Periodic sweep backstop for failed previews + analyses.** Transient failures get one shot from the ingest enqueue; no scheduled retry runs. Pattern: `worker/jobs/preview_sweep.py` + `worker/jobs/analysis_sweep.py`, each querying their table for `storage_uri IS NULL` / `measurements_json IS NULL` with `is_permanent_failure=False`. Skipped because the volume is small while watchlist-only.
- **Spectrum line annotations.** Renderer plots wavelength vs flux as-is. No Hα/[OIII]/PAH overlay markers. A static line list keyed by wavelength range is the obvious next step; redshift-aware annotation needs the observation's `z`, which isn't in our schema yet.
- **Image stretch presets per instrument.** All imaging uses ZScale + Asinh. MIRI long-wave and NIRCam short-wave actually want different choices — when bias becomes visible, branch on `observation.instrument`.
- **Cube collapse strategy.** `s3d` cubes are summed along the wavelength axis for *previews*. *Analysis* skips cubes entirely (see §7b.4). Median-collapse + band-selected slices for previews, plus a real `CubeAnalyzer`, when an IFU product needs serious treatment.
- **next/image optimization.** Frontend uses `<img>` with eslint-disable. Switching to `next/image` requires adding the API host to `next.config.js`'s `images.domains` (which differs between dev/prod) — defer until image volumes warrant it.
- **Photometry / calibrated SNR.** Phase 4 source count is coarse (connected components); SNR is a `|median|/MAD` proxy. photutils is the right tool for photometry — already declared as an *optional* extra in the worker pyproject. Wire it when Phase 5+ wants flux-per-source or SNR-per-resel.
- **Analysis history endpoint.** API returns only the latest row per analyzer name. The DB keeps every version. Add `/api/products/{id}/analysis/history` when version diffing becomes a real workflow.

---

## 7. Phase 3 — preview + spectrum chart generation (shipped, retained for reference)

### 7.1 What landed

1. **Image previews** for `i2d`, `s2d`, `cal`: PNG, max-dim 512 (full) / 128 (thumbnail), ZScale + Asinh. Greyscale, north-up. PIL.thumbnail-driven — small inputs preserve native size (never upscales).
2. **Spectrum charts** for `x1d`, `c1d`: PNG, 800×400 (full) / 256×128 (thumbnail). Matplotlib line plot with wavelength + flux units pulled from `TUNIT*` headers.
3. **Cube previews** for `s3d`: same renderer as imaging, fed a wavelength-axis `nansum` collapse.
4. **Calibration metadata** populated as a side effect: `calibration_version` from `CAL_VER`/`CAL_VCS`/`CALVER`; `crds_context` from `CRDS_CTX`/`CRDSCTX`/`PMAP`. Never overwrites a pre-populated value.

### 7.2 How it's wired

- New ORM model `DataProductPreview` (one row per `(data_product_id, variant)`). Migration `c471d6cc58ae`. Failure model: `attempts` JSON + `last_error` + `is_permanent_failure` flag.
- `app/services/previews.py` — pure renderers + S3 fetch. `Preview` dataclass, `PreviewError(is_permanent: bool)`.
- `app/services/preview_job.py` — orchestration (`generate_for_product`, `_run`). Idempotent; skips variants whose row already has a `storage_uri`. Permanent failures mark the product and never retry.
- `app/services/storage.py` — `LocalFilesystemStorage` writes under `services/api/preview_cache/` and returns `{api_public_url}/api/previews/{key}`; `AzureBlobStorage` activates when an Azure connection string or account URL is set. Selection in `get_preview_storage(settings)`.
- `app/services/queue.py::enqueue_preview_gen(product_id, product_type)` soft-imports rq+redis, pings, and returns False on any failure. `ingest_observations` calls it for *newly created* products that fire an Alert (and are eligible — `is_supported(product_type)`).
- `worker/jobs/preview_gen.py` is a 5-line re-export so the RQ string `worker.jobs.preview_gen.generate_for_product` still resolves to the API-side orchestration.
- API: `ProductRow`, `DataProductRead`, `AlertRead` carry `thumbnail_url` + `preview_url`. New `/api/previews/{path}` route serves the local fallback (404s when Azure is configured — that path returns absolute blob URLs directly).
- Frontend: product feed got a Preview column; alert cards a 14×14 thumbnail. Both link to the full preview when present.

### 7.3 Decisions baked in (don't re-litigate — see issue notes if changing)

| Question | Choice | Why |
|---|---|---|
| Sync vs async generation | Async via RQ `analyze` queue | Latency-isolated from MAST polls; failed renders don't break ingest |
| Storage schema | New `data_product_previews` table, one row per (product, variant) | Variant explosion (thumb, full, future jpg/webp) without column churn |
| Trigger scope | Only watchlist-matched products | User-selected. Caps egress while we don't have a CDN. One-line change to broaden. |
| Local dev backend | Filesystem fallback under `preview_cache/` | Docker still not installed; unblocks dev today, swaps to Azure when conn string is set |
| Image stretch | ZScale + Asinh, greyscale | Matches JWST QuickLook / jdaviz defaults. Per-instrument tuning deferred. |
| Cube collapse | `nansum` along spectral axis | Cheapest "show something useful"; median/band-slice are obvious next steps |
| Spectrum annotations | None | Static line list (Hα, [OIII], PAH) is the obvious next step; redshift-aware needs an `obs.z` we don't have |
| Failure retry | Permanent flag + JSON attempts log; no scheduled sweep | Volume is small while watchlist-only. Sweep is a 30-line `worker/jobs/preview_sweep.py` when needed. |

### 7.4 What we intentionally do *not* do

- We don't generate science-grade products. The JWST calibration pipeline does that; we display its output.
- We don't run the JWST calibration pipeline. Ever.
- We don't write to `s3://stpubdata/`. Read-only.
- We don't cache FITS files locally beyond a single job execution. Storage cost dwarfs re-fetch cost; egress is the limiting resource and we're already bounded by the watchlist gate.

---

## 7b. Phase 4 — deterministic analysis engine (shipped, retained for reference)

### 7b.1 What landed

1. **Image analyzer** for `i2d`, `s2d`, `cal`: pixel statistics (min/max/mean/median/std), NaN count, sigma-clipped background (σ=3, 5 iterations), connected-components source count (`scipy.ndimage.label` on a `bg + 3σ` threshold), saturated-pixel count (≥99% of finite max).
2. **Spectrum analyzer** for `x1d`, `c1d`: sample count, wavelength + flux range with units, `scipy.signal.find_peaks` peak + trough count (prominence ≥ 3 × MAD), robust S/N proxy from MAD.
3. **No cube analyzer.** s3d returns None from `get_analyzer_for` and the job layer skips entirely — no failed row created. Cube measurements need their own design (per-slice stats? band-collapsed source counts? IFU spectrum extraction?) which Phase 4 doesn't scope.
4. **Reproducibility metadata** embedded in every successful `measurements_json["meta"]`: `scipy_version`, `numpy_version`, `astropy_version`, plus `calibration_version` and `crds_context` from the FITS primary header. Lets future re-runs diff against past ones.
5. **Product detail page** at `/products/{id}` — server component that parallel-fetches product + analysis, renders the full preview large, file metadata, and a structured measurements view grouped by section (pixel stats / background / source detection for images; wavelength / flux / features for spectra). Linked from product feed + alert cards.

### 7b.2 How it's wired

- New ORM model `DataProductAnalysis` (one row per `(data_product_id, analyzer_name, analyzer_version)`). Migration `7ed3b023ed62`. Failure model identical to `DataProductPreview`: `attempts` JSON + `last_error` + `is_permanent_failure`.
- `app/services/analysis/` — pure dispatch + analyzers. `base.py` has the `Analyzer` Protocol + `AnalysisResult` + `AnalysisError(is_permanent)`. Each analyzer module declares `NAME` + `VERSION` module-level constants so a bump creates a new DB row alongside the old.
- `app/services/analysis_types.py` — lightweight `is_analyzable()` parallel to `preview_types.py`. Doesn't import scipy, so the ingest hot path stays cheap.
- `app/services/analysis_job.py` — orchestration mirroring `preview_job.py`. Reuses `previews.fetch_fits_anonymous` + `previews.extract_calibration_metadata`. Idempotent on `(product, analyzer, version)`.
- `app/services/queue.py::enqueue_analyze_product` — soft-import RQ, ping Redis, enqueue against the same `analyze` queue as previews. Returns False on any failure.
- `ingest_observations` calls both `enqueue_preview_gen` and `enqueue_analyze_product` under the *same* watchlist-matched gate. `IngestResult.analyses_enqueued` count surfaces alongside `previews_enqueued`.
- `worker/jobs/analyze_product.py` — 5-line shim so the RQ string `worker.jobs.analyze_product.generate_analysis_for_product` resolves to the API-side orchestration.
- API: new `app/routes/analyses.py` + `app/schemas/analysis.py`. `GET /api/products/{id}/analysis` returns the latest row per analyzer.
- API gained `scipy>=1.14` (signal.find_peaks + ndimage.label). photutils stays out — coarse source count is enough for MVP "is there structure here"; photometry is Phase 5+.
- Frontend: `lib/api.ts` gains `getProduct(id)` + `getProductAnalyses(id)` + `DataProductRead` + `AnalysisRead` types. New page `apps/web/app/products/[id]/page.tsx`. `ProductFeed` and `AlertFeed` link the filename to the detail page.
- Tests (35 new, 122 total): analyzer unit tests with synthetic FITS containing injected sources/peaks; analysis_job integration with mocked S3 + tmp DB; route tests covering 404 + empty + latest-per-analyzer + failure surface; ingest-enqueue tests for the analysis path.

### 7b.3 Decisions baked in (don't re-litigate)

| Question | Choice | Why |
|---|---|---|
| Analyzer registry vs. hardcoded dispatch | Hardcoded `get_analyzer_for(product_type)` | N=2. Registry indirection adds zero value while easy to refactor later. |
| Same job as preview_gen vs separate | Separate `analysis_job.py` | Analysis is CPU-bound, previews are I/O-bound — sharing fetch saves one S3 GET but couples scheduling/retry. Re-paying egress beats coupled failure modes. |
| Public API shape | Dedicated `GET /api/products/{id}/analysis` | Keeps `ProductRow`/`DataProductRead` lean. List endpoint stays fast; detail page fetches both in parallel. |
| Detail page now vs Phase 4.5 | Now | Analysis is useless without a place to see it. Same commit lets us verify end-to-end. |
| Source detection: photutils vs scipy.ndimage | scipy.ndimage.label | photutils is the right call for photometry (Phase 5+). For "how many distinct bright regions exist", a 3σ-threshold + connected components is the simpler, lighter-dep answer. |
| Spectrum peak detection | `scipy.signal.find_peaks` with prominence = 3 × MAD | Robust to continuum slope; no need to fit a continuum first. |
| S/N "proxy" naming | Explicitly *proxy*, not SNR | `|median| / MAD` is a relative quality indicator. Calibrated SNR-per-resel needs FITS-header noise estimates — Phase 5+ AI consumers should know to treat this as relative. |
| Reproducibility metadata location | Inside `measurements_json["meta"]`, not separate columns | Schema doesn't churn when we add/rename analyzer outputs. Trade-off: can't index on `crds_context` per-analysis (but the column on `data_products` *is* indexable for the cross-cutting query). |
| Cube analysis | Skipped entirely, no failed row | A "not implemented" failed row is noise. Skipping cleanly leaves room for a real CubeAnalyzer later without migrating away from junk rows. |
| Frontend rendering | Generic dispatch on `measurements_json["kind"]` | Image/spectrum sections hardcoded. New analyzer = new `<XMeasurements>` component, no schema work. |

### 7b.4 What we intentionally do *not* do

- We don't run photutils source extraction. Source count is a coarse "how many distinct bright regions" estimate, not photometry.
- We don't compute calibrated SNR per resolution element. The `snr_proxy` is `|median| / MAD` — a relative quality number, not a science measurement.
- We don't analyze cubes (s3d) yet. The dispatcher returns None and the job skips. No failed row created — adding cube support later is purely additive.
- We don't surface analyzer-version history through the API. The DB keeps every (product, analyzer, version) row; the endpoint returns only the latest per analyzer name. Add `/api/products/{id}/analysis/history` when needed.
- We don't trigger analysis for non-watchlist-matched products (same egress gate as previews). Switch by removing the `if new_alerts` branch in `ingest_observations` — same one-line change for both.
- We don't periodically sweep failed analyses for retry. Same rationale as preview-sweep deferral: low volume while watchlist-gated. A `worker/jobs/analysis_sweep.py` is a 30-line copy of the preview-sweep pattern when needed.

---

---

## 8. Verification conventions — copy-paste commands

A future session should be able to validate end-to-end without thinking. From repo root:

```powershell
# API: lint + tests
cd services\api
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest

# API: migration sanity
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check    # no pending model drift

# Worker: lint (shares api's venv)
cd ..\worker
..\api\.venv\Scripts\python.exe -m ruff check .

# Frontend: typecheck + build (typed routes require build for new pages)
cd ..\..\apps\web
npm run typecheck
npm run build

# End-to-end smoke (live MAST, ~60s)
cd ..\..\services\api
.\.venv\Scripts\python.exe -m app ingest mast --instrument NIRCAM --limit 5
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
# Then: curl localhost:8000/api/products | jq '.total'
```

**Encoding.** Set `$env:PYTHONIOENCODING = "utf-8"` before any CLI that prints Unicode. PowerShell defaults to cp1252 and will `UnicodeEncodeError` on `→` and similar.

---

## 9. Concrete pitfalls observed across sessions

Things that already cost us debugging time. Read this before re-falling into them.

1. **In-memory SQLite is per-connection.** The default `sqlite:///:memory:` engine creates fresh tables per connection. When a test uses both a session fixture *and* a FastAPI `TestClient` (which opens its own connection), tables vanish. Fix: `StaticPool` + `check_same_thread=False` — already in `tests/conftest.py`. If you add a new test fixture, copy this pattern.

2. **FastAPI dependency overrides don't commit by default.** The real `get_session` commits on success; a naive `def _override(): yield session` does not. Writes the API makes are invisible to subsequent reads. The `client` fixture in `conftest.py` mirrors the commit semantics — keep them in sync.

3. **Ruff isort treats `app.*` as third-party from the worker.** The worker's `pyproject.toml` declares `worker` as the package; ruff infers everything else (including `app.*`, despite being our code) as third-party. Imports must be grouped: stdlib → third-party (`app.*`, `sqlalchemy`, etc.) → first-party (`worker.*`). `ruff check --fix` handles it.

4. **Next.js `typedRoutes` requires `next build` to regenerate types.** Adding a new page → `npm run typecheck` will error until a build runs. CI must build, not just typecheck.

5. **ESLint blocks unescaped apostrophes (`react/no-unescaped-entities`).** Use `&apos;` in JSX text. `npm run typecheck` won't catch it; `npm run build` will.

6. **`@lru_cache` on `get_settings()` bites tests.** Toggling env vars between tests has no effect because the settings instance is cached. Either `get_settings.cache_clear()` in a fixture (see `test_sns_webhook.py::_reset_settings`) or `monkeypatch.setattr("app.routes.X.get_settings", lambda: ...)` for per-route overrides.

7. **MAST queries are slow.** A live `Observations.query_criteria()` takes 30-90s. Never put one in a unit test. Drive `MastClient.assemble()` with synthetic `astropy.table.Table` objects (see `test_mast_assemble.py`).

8. **Astropy masked values look real until they don't.** A `Table` cell with `np.ma.masked` evaluates falsy in boolean context but is *not* `None`. Use `_cell()` in `clients/mast.py` for any new column access; never index a row directly.

9. **Don't put real secrets in `.env.example`.** GitHub push protection blocks even false-positive matches like the Azurite well-known dev key (which is documented public). Use `UseDevelopmentStorage=true` instead of the literal connection string.

10. **`pip install -e ../api` must happen before `pip install -e .` in the worker** — otherwise the worker's resolver hasn't seen `webbwatch-api` and will fail to import `app.*` at job runtime.

11. **`PIL.Image.thumbnail()` never upscales.** Pass a 64×80 array and ask for 512×512; you get 64×80 back. The image renderer is correct (preserves aspect, doesn't fabricate detail) — but tests that assert `max(width, height) == IMAGE_FULL_DIM` need synthetic inputs *larger* than the clamp dim, otherwise they'll fail.

12. **`pathlib.Path.is_absolute()` is platform-conditional.** `Path("/abs/path").is_absolute()` returns False on Windows because there's no drive letter. A traversal guard that only relies on `is_absolute()` will let POSIX-style absolute paths through on Windows. `storage._safe_relative_key` has an explicit `startswith(("/", "\\"))` check in front for that reason — don't remove it.

13. **`app.services.previews` transitively imports matplotlib + numpy + PIL.** That's fine for the worker and preview job, but the hot path (ingest) shouldn't pay that cost just to check eligibility. Lightweight checks live in `app.services.preview_types` (no matplotlib import); import from there in `ingest.py` or `routes/products.py`.

14. **ESLint `@next/next/no-img-element` only suppresses the immediately-following line.** A multi-line `<img ...>` JSX block won't be silenced by `// eslint-disable-next-line` placed before the variable declaration. Collapse to `const img = <img ... />;` on one line, or use `{/* eslint-disable-next-line ... */}` inside JSX.

15. **The worker's `preview_gen.py` is intentionally trivial.** The orchestration lives in `app.services.preview_job` so tests in the api venv can drive `_run()` directly without standing up rq/redis. If you're adding logic to "the worker job," you're probably looking in the wrong file — edit `preview_job.py` instead.

---

## 10. Pointers — primary sources to cite, not paraphrase

When a decision needs justification beyond what's in this repo, these are the authoritative references. Read directly, don't summarize from memory.

- **JWST Data Calibration Pipeline.** https://jwst-pipeline.readthedocs.io/ — for calibration level semantics, product suffix definitions, CRDS context handling.
- **MAST API.** https://mast.stsci.edu/api/v0/ — observation fields (`_o_data_summary.html`), product fields (`_productsfields.html`).
- **astroquery.mast.** https://astroquery.readthedocs.io/en/latest/mast/mast.html — the only Python interface to MAST we use.
- **JWST data product types.** https://jwst-docs.stsci.edu/understanding-data-files — suffix taxonomy and what each product *means* scientifically.
- **AWS Open Data — JWST.** https://registry.opendata.aws/stpubdata/ — bucket details, SNS topic ARN, access patterns.
- **AWS SNS HTTP signature verification.** https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html — the canonical-string + RSA-PKCS1v15 spec we implement in `services/api/app/services/sns.py`.
- **JWST instrument modes.** https://jwst-docs.stsci.edu/ — for understanding why `instrument_name` is composite and what `IMAGE`/`MOS`/`IFU`/`MRS`/`WFSS` mean.
- **astropy.visualization.** https://docs.astropy.org/en/stable/visualization/ — for Phase 3 stretch + interval choices.

---

## 11. Conventions reference card

Already in `CLAUDE.md` but repeated here so this document is freestanding.

- Python ≥ 3.12, PEP 695 generics OK (`class Page[T]`).
- SQLAlchemy 2.0 typed declarative; never use legacy `Column()`.
- FastAPI deps as default args (`Depends(get_session)`); B008 ignored in `app/routes/*.py`.
- Migrations: autogenerate, *read the diff*, then apply. `alembic check` to catch drift.
- Tests: in-memory SQLite per test, `StaticPool` if a `TestClient` is involved.
- Linting: ruff `E F I B UP SIM`, line 100. Per-file ignores in `pyproject.toml`, not `# noqa`.
- Commits: one per phase or cohesive change. `Phase N: ...` or `<area>: ...`. Co-author trailer for AI-assisted work. No `--no-verify`, no force-push.
- Frontend: server components by default. `next: { revalidate: N }` for feed data, not `cache: "no-store"`.

---

## 12. If you change something on this list, update this document

This file is the contract between past and future sessions. If you change an invariant, a code map entry, a deferred-work entry, or a known pitfall, update *this* file in the same commit. Otherwise the next session will be wrong before it starts.
