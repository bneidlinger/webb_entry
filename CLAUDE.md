# CLAUDE.md

Orientation for Claude sessions in this repo. Keep this file tight — it loads on every session.

## What this is

**WebbWatch AI** — a public-data discovery and analysis platform for the James Webb Space Telescope. Watches MAST + the AWS Open Data mirror for newly public JWST data products, generates previews, runs deterministic-first analysis with optional local and cloud AI review, and surfaces results in a shareable feed.

Source of truth for design decisions: [`webbwatch_ai_project_plan.md`](webbwatch_ai_project_plan.md). Defer to it for the *why*; this file covers *how things are wired right now*.

**Deep context for a fresh session: [`docs/HANDOFF.md`](docs/HANDOFF.md).** Read it before any non-trivial work — it codifies invariants, JWST/MAST domain knowledge, deferred-work rationale, and pitfalls already paid for in past sessions.

GitHub: <https://github.com/bneidlinger/webb_entry>

## Stack

| Layer | Local dev | Production (Azure) |
|---|---|---|
| Frontend | Next.js 15 + TS + Tailwind App Router | Azure Static Web Apps |
| API | FastAPI + Python 3.12+ | Azure Container Apps |
| Workers | RQ + Redis (not wired yet) | Azure Container Apps + Azure Cache for Redis |
| DB | SQLite at `services/api/webbwatch.db` | Azure Database for PostgreSQL Flexible Server |
| Object storage | Azurite (Azure Blob emulator) | Azure Blob Storage |
| Cloud AI | OpenAI **or** Azure OpenAI behind `AI_PROVIDER` env var | Same |
| Secrets | `.env` | Azure Key Vault via managed identity |

**JWST source data lives on AWS** (`s3://stpubdata/jwst`) because STScI hosts it there — we read anonymously, no AWS account needed. Everything *we* produce goes to Azure.

## Repo layout

```
apps/web/                Next.js frontend
services/api/            FastAPI + SQLAlchemy + Alembic + CLI
  app/
    main.py              create_app(), router wiring
    config.py            pydantic-settings (reads .env, ../../.env)
    db.py                Engine + session_scope() + get_session()
    cli/                 typer subcommands; entry point is app/__main__.py
    clients/mast.py      astroquery.mast wrapper → dataclasses
    clients/ai/          Provider interface + OpenAI + Azure OpenAI adapters
    models/              SQLAlchemy 2.0 declarative
    routes/              FastAPI routers (one per resource)
    schemas/             Pydantic response models
    services/ingest.py   MAST → DB upsert (idempotent)
  alembic/               Migrations (autogenerate enabled)
  tests/                 pytest with in-memory SQLite fixtures
services/worker/         RQ + rq-scheduler; preview_gen + analyze_product + mast_poll + s3_listing jobs
packages/shared/         JSON Schema + TS types for cross-language contracts
infra/docker-compose.yml Postgres + Redis + Azurite + api + worker + web
docs/                    HANDOFF.md, azure-deployment.md, local-dev-without-docker.md, ollama_setup.md
```

## Local dev

Without Docker (current state — Docker Desktop not installed yet):

```powershell
# One-time
cd services\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m alembic upgrade head

# Ingest real JWST metadata (limit small; MAST queries take ~30-90s)
$env:PYTHONIOENCODING = "utf-8"   # avoid cp1252 errors from any Unicode in CLI output
python -m app ingest mast --instrument NIRCAM --limit 10 --json

# API
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/health, /api/products, /docs

# Frontend (separate terminal)
cd ..\..\apps\web
npm install
npm run dev
# → http://localhost:3000
```

With Docker (once Docker Desktop is installed):

```powershell
Copy-Item .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

**Local AI (Ollama).** To run the Phase 5/5.5 local AI summaries (text + on-demand vision) on your machine, see [`docs/ollama_setup.md`](docs/ollama_setup.md).

## Conventions

These are decisions already made; follow them unless there's a real reason to change.

- **Python**: requires 3.12+ (uses PEP 695 generics like `class Page[T](BaseModel)`).
- **SQLAlchemy**: 2.0 typed declarative (`Mapped[X]`, `mapped_column(...)`). No legacy `Column()`.
- **FastAPI deps**: use `Session = Depends(get_session)` as a default arg. Ruff is configured to ignore B008 in `app/routes/*.py` (idiomatic FastAPI).
- **CLI**: typer + rich. Entry point is `python -m app ...`. Add new subcommands under `app/cli/` and register them in `app/__main__.py`.
- **Migrations**: generate with `python -m alembic revision --autogenerate -m "..."`, then read the diff before committing (autogenerate misses things). Apply with `python -m alembic upgrade head`.
- **Tests**: in-memory SQLite (`sqlite+pysqlite:///:memory:`) per test via the `session` fixture in `tests/conftest.py`. No live MAST in tests — drive `MastClient.assemble()` with synthetic astropy `Table` objects.
- **Encoding**: prefer ASCII in CLI output strings. PowerShell defaults to cp1252 and will raise `UnicodeEncodeError` on chars like `→`. Rich's box-drawing in tables is fine; only watch f-string literals.
- **Linting**: ruff (`E F I B UP SIM`, line 100). Per-file ignores in `services/api/pyproject.toml` — extend that list rather than adding `# noqa` comments unless they're truly local.
- **Frontend**: server components by default. Fetch from the API with `fetch(...)`; use `next: { revalidate: N }` rather than `cache: "no-store"` for feed-style data so the page stays fast.
- **Commits**: one commit per phase or per cohesive change. Conventional-ish ("Phase N: ..." or "<area>: ..."). Co-author trailer for AI assistance. No `--no-verify`, no `--amend` on pushed commits.
- **Secrets**: never put real secrets in `.env.example`. GitHub push protection is on; even false-positive matches (like the Azurite well-known dev key) get blocked. Use `UseDevelopmentStorage=true` for Azurite.

## State (2026-05-30)

**Phase 0 — scaffold** ✓ shipped (`commit 22223f3`)
- Monorepo, Next.js 15 + Tailwind, FastAPI with `/health`, RQ worker skeleton, Azurite/Postgres/Redis in compose, GitHub Actions CI, `CloudAIProvider` interface with OpenAI + Azure OpenAI adapters.

**Phase 1 — MAST metadata ingestion** ✓ shipped (`commit 08ff118`)
- SQLAlchemy ORM (Observation, DataProduct) + Alembic migration.
- `MastClient` (astroquery wrapper) + `ingest_observations()` (idempotent upsert).
- CLI: `python -m app ingest mast --instrument NIRCAM --limit 100`.
- API: `GET /api/observations`, `GET /api/observations/{id}`, `GET /api/products`, `GET /api/products/{id}`, `POST /api/admin/ingest/mast-sync`.
- Frontend home page shows real JWST products as a table.

**Phase 2 — new-data detection + alerts** ✓ shipped
- Worker pip-installs `services/api` editable so it imports the same `app.clients.mast` + `app.services.ingest`. `worker/schedule.py` registers two periodic jobs via `rq-scheduler`: MAST poll every 30 min, anonymous S3 listing every 6 h (defaults; tune via env).
- New ORM models: `Watchlist(user_id="default", name, criteria_json, enabled)`, `Alert(watchlist_id, data_product_id, reason, delivery_status, read_at)`. Migration `2d50cfb24ccd`.
- Matching engine: `app/services/match.py` evaluates instruments / programs / targets / product_types / cone (haversine) / keywords against `(product, observation)`. AND across keys, OR within a key.
- `ingest_observations` calls `evaluate_watchlists` for every *newly created* product — updates never re-alert. `alerts_created` count surfaces in `IngestResult`.
- Delivery: `app/services/delivery/discord.py` posts an embed to `DISCORD_WEBHOOK_URL` (no-op when unset). `deliver_pending_alerts` runs after each ingest pass and stamps `delivery_status`.
- API: `GET/POST/GET/PATCH/DELETE /api/watchlists`, `GET /api/alerts`, `POST /api/alerts/{id}/read`, `GET /api/feed.rss` (RSS 2.0), `POST /api/webhooks/aws/jwst` (off by default, SubscriptionConfirmation handshake + RSA SHA1/SHA256 signature verification when enabled).
- Frontend: new `/alerts` page with cards per match + delivery-status badge; home page links to it.
- Tests (31 new): matching matrix, alert emission e2e, SNS handshake + signature gating, watchlist CRUD, alerts feed + RSS. 39 total, all pass.

**Phase 3 — preview + spectrum chart generation** ✓ shipped
- New ORM model `DataProductPreview` (one row per (product, variant)), unique on `(data_product_id, variant)`. Migration `c471d6cc58ae`. Side-effect: `calibration_version` + `crds_context` get populated from FITS primary header during generation.
- `app/services/previews.py` — pure renderers: image (ZScale + Asinh) for i2d/s2d/cal, line plot for x1d/c1d, wavelength-collapsed image for s3d. `Preview` dataclass + `PreviewError(is_permanent)`. Synthetic-FITS unit tests.
- `app/services/storage.py` — `LocalFilesystemStorage` (default, writes under `services/api/preview_cache/`, served via new `/api/previews/{path}` route) and `AzureBlobStorage` (activates when `AZURE_STORAGE_CONNECTION_STRING` or `AZURE_STORAGE_ACCOUNT_URL` set). Path traversal blocked.
- `app/services/preview_job.py` — orchestration: fetch → open → extract metadata → render each missing variant → upload → persist. Idempotent. `worker/jobs/preview_gen.py` is a thin re-export so the RQ string `worker.jobs.preview_gen.generate_for_product` still resolves.
- `app/services/queue.py` — soft-imports rq/redis, returns False if Redis unreachable (CLI mode). `ingest_observations` enqueues only for *watchlist-matched* newly-created products (user choice, HANDOFF §7.3-6 egress trade-off). `IngestResult` gains `previews_enqueued`.
- API: `ProductRow`, `DataProductRead`, `AlertRead` schemas + their routes return `thumbnail_url` + `preview_url`. New `previews` route serves the local fallback.
- API deps gained `matplotlib`, `pillow`, `numpy`, `boto3`, `botocore` (preview_job lives api-side for testability).
- Frontend: product feed has a Preview column; alert cards have a thumbnail. Both link to the full preview when present.
- Tests (48 new, 87 total): renderer unit tests with synthetic HDULists; storage backend selection + traversal-safety; ingest enqueue gating; full `_run()` integration with mocked S3 + tmp filesystem.

**Phase 4 — deterministic analysis engine** ✓ shipped
- New ORM model `DataProductAnalysis` (one row per `(product, analyzer_name, analyzer_version)`). Migration `7ed3b023ed62`. Version bumps preserve history; same-version re-runs overwrite.
- `app/services/analysis/` — pure analyzers. `ImageAnalyzer` (pixel stats, σ-clipped background, `scipy.ndimage.label` source count, saturated-pixel count) for `i2d`/`s2d`/`cal`. `SpectrumAnalyzer` (wavelength/flux range, `scipy.signal.find_peaks` peak count with prominence ≥ 3·MAD, robust S/N proxy) for `x1d`/`c1d`. Cube (s3d) intentionally unhandled — dispatcher returns None, job skips.
- `app/services/analysis_types.py` — light `is_analyzable()` parallel to `preview_types.py` so the ingest hot path doesn't pay scipy import cost.
- `app/services/analysis_job.py` — orchestration mirroring `preview_job`. Reuses `previews.fetch_fits_anonymous` + `extract_calibration_metadata`. Idempotent on `(product, analyzer, version)`. Embeds `scipy_version`/`numpy_version`/`astropy_version`/`crds_context`/`calibration_version` inside `measurements_json["meta"]` for reproducibility diffs.
- `app/services/queue.py::enqueue_analyze_product` — soft-import RQ, same `analyze` queue as previews. `ingest_observations` enqueues analyses alongside previews under the same watchlist-matched gate. `IngestResult.analyses_enqueued` joins `previews_enqueued`.
- `worker/jobs/analyze_product.py` — 5-line shim so the RQ string resolves.
- API: new `GET /api/products/{id}/analysis` returning latest row per analyzer. `app/schemas/analysis.py::AnalysisRead`.
- API deps gained `scipy>=1.14` (signal.find_peaks + ndimage.label). photutils stays optional in worker pyproject for future photometry.
- Frontend: new `/products/[id]` server component page with structured measurements display (pixel stats / background / source detection for images; wavelength / flux / features for spectra) + reproducibility-metadata details panel. `ProductFeed` filename + alert-card filename both link to it.
- Tests (35 new, 122 total): analyzer unit tests with synthetic FITS (injected sources/peaks); orchestration integration with mocked S3; route shape + idempotency + failure surface; ingest enqueue gate.

**Phase 5 — local AI analysis (Ollama)** ✓ shipped
- New ORM model `AiReport` (one row per `(product, mode, model_name, prompt_version)`), overwrite-in-place + failure model mirroring `DataProductAnalysis`. Migration `dff64aa9d87f`. `report_json` (validated plan-§7 report + stamped `model_notes`) + `input_summary_json` (exact payload sent).
- `app/services/ai/` — sync `AiProvider` protocol (`base.py`) + `OllamaProvider` over the openai SDK against Ollama's `/v1` endpoint (`local.py`) + `get_ai_provider` factory. Versioned prompts (`prompts/image_summary_v1.py`, `spectrum_summary_v1.py`) + tolerant `parse_ai_report` JSON validation (`schemas.py`). The unused Phase 0 `clients/ai` cloud stub stays put; Phase 6 reshapes it onto this protocol.
- `app/services/ai_job.py` — orchestration mirroring `analysis_job`; the model narrates over the latest `DataProductAnalysis.measurements_json` (never FITS). `analysis_job` chains `enqueue_ai_report` on success (AI runs second); `ingest` is unchanged. Worker shim `worker/jobs/ai_report.py`.
- `LOCAL_AI_ENABLE` env gate (default off) + `OLLAMA_BASE_URL` (`/v1`) + `LOCAL_AI_MODEL/MAX_TOKENS/TEMPERATURE/REQUEST_TIMEOUT_SECONDS`. Ollama is the user's responsibility to install + run; the worker no-ops if it's unreachable.
- API: `GET /api/products/{id}/ai-reports` (latest per mode+model), `POST /api/products/{id}/ai-reports/regenerate` (force). Frontend: product detail page "AI summary" section (AI-generated badge, summary, measured facts, confidence/severity-badged features + quality flags, next steps, tags, human-validation caveat) + regenerate button.
- Tests (51 new, 173 total, all pass without Ollama via a fake provider / injected openai client). Cloud AI is Phase 6.

**Phase 5.5 — local AI vision (Ollama, on-demand)** ✓ shipped
- Opt-in multimodal pass: a vision model also looks at the full preview PNG and writes a second report with `mode="local_vision"` alongside the text `mode="local"` one. **No migration** — `mode` reuses the existing `ai_reports` column.
- On-demand only (plan §6 one-model-at-a-time): the "Generate vision summary" button → `POST /api/products/{id}/ai-reports/regenerate?vision=true`. Text still auto-runs; no preview/analysis job coupling.
- `PreviewStorage.read(key)` (both backends) + `preview_storage_key` feed the preview to `OllamaProvider.complete(image=)` as a base64 data URI. Vision prompts (`VISION_SYSTEM_PROMPT`/`VISION_PROMPT_VERSION`) keep measurements authoritative. Config: `LOCAL_AI_VISION_ENABLE` (default off) + `LOCAL_AI_VISION_MODEL` (`llava:7b`).
- `ai_job._run(vision=)` adds `vision_disabled` + `no_preview` skips; helpers gained a `mode` param so text + vision rows are keyed independently. Frontend: a second regenerate button + a "vision" chip on `local_vision` cards.
- Tests (18 new, 191 total, all pass without Ollama via a fake provider + injected storage). Web typecheck + build clean. Cloud AI (incl. cloud vision) is Phase 6.

**Phases 6–8** see [plan §11](webbwatch_ai_project_plan.md).

## Phase 2 directions — new-data detection + alerts (shipped, retained for reference)

### Decisions locked in

- **Cadence**: MAST 30 min, S3 6 h (lighter than the plan default; user-selected).
- **Delivery**: Discord + in-app feed + RSS. No email — Azure Communication Services deferred.
- **Auth**: hardcoded `user_id="default"` until Phase 8.
- **Code sharing**: worker `pip install -e ../api`, no `packages/shared` extraction yet.

### Architectural calls already made (don't re-litigate)

- **RQ over Celery** — keep it unless scheduling needs explicitly outgrow `rq-scheduler`.
- **SQLite locally, Postgres in prod** — both share the same SQLAlchemy code; no per-dialect branches in models.
- **JWST SNS → HTTPS endpoint on Azure** rather than AWS SQS — avoids AWS account requirement (plan §3, Azure amendment).
- **Watchlist criteria as a JSON column**, not a separate criteria table. SQLite + Postgres both support JSON well enough for Phase 2 cardinality.

### Things deliberately deferred out of Phase 2

- Real per-watchlist RSS tokens (anyone can hit `/api/feed.rss` today).
- Acting on SNS `Notification` payloads — the endpoint logs them but doesn't enqueue a targeted MAST poll yet. Will land alongside the registered AWS SNS subscription.
- Email delivery via Azure Communication Services.
- The S3 listing job only *detects* unknown keys — it doesn't drive a re-poll yet.
