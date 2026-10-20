# Project Plan: WebbWatch AI

**Working name:** WebbWatch AI  
**Date:** 2026-05-17  
**Goal:** Build a web app that watches for newly public James Webb Space Telescope (JWST) data, alerts users when interesting data lands, previews the data, and runs a two-tier analysis system: local AI/science tools on consumer hardware plus optional cloud AI review.

> **Amendment 2026-05-17 — Azure pivot.**
> The cloud target is now **Microsoft Azure** for our own infrastructure (object storage, compute, database, cache, cloud AI). The JWST public data itself remains on AWS (`s3://stpubdata/jwst`) because STScI hosts it there — we read it anonymously and store only derived artifacts (previews, FITS cache, analysis outputs) in Azure. Cloud AI supports both **OpenAI** and **Azure OpenAI** behind a provider interface (`AI_PROVIDER=openai|azure_openai`). Affected sections: §2 (stack), §3 (sources), §6 (AI), §11 (phases).

> **Amendment 2026-10-18 — Exoplanet Portrait Atlas.** Expand the discovery workflow
> to combine TESS and other exoplanet observations, rank confirmed planets by usable
> evidence, and produce sourced prompts for hypothetical close-range views. Section 20
> defines the track and distinguishes the runnable catalog prototype from future
> atmosphere modeling and image generation.

---

## 1. Product Vision

WebbWatch AI is a public-data discovery and analysis platform for JWST.

The app should make JWST data feel less like “buried academic archive” and more like a live exploration feed:

- “New Webb data just dropped.”
- “Here is what instrument/filter/product type this is.”
- “Here is a preview image or spectrum.”
- “Here is a first-pass AI + deterministic science-tool analysis.”
- “Here is why it might be interesting.”
- “Here is the exact file, metadata, source archive, calibration version, and citation path.”

The app should not pretend that an AI summary equals a scientific discovery. The app should instead make it easier for curious humans to inspect, compare, validate, and share observations. Translation: give the meatbags sharp tools, not fake Nobel Prizes.

---

## 2. Best Stack Choice

### Recommended architecture

Use a **TypeScript frontend** and a **Python science backend**.

| Layer | Recommendation | Why |
|---|---|---|
| Frontend | Next.js + TypeScript + Tailwind + shadcn/ui | Fast to build, easy to deploy, good for public feed/shareable pages |
| Backend API | FastAPI + Python | Python is the sane choice for FITS files, astronomy tooling, and AI glue |
| Background jobs | RQ + Redis (Celery if scheduling needs grow) | Ingestion, file checks, preview generation, AI jobs |
| Database | PostgreSQL — **Azure Database for PostgreSQL Flexible Server** in prod | Strong metadata querying, JSON fields, indexing; managed in prod |
| Cache / queue broker | Redis — **Azure Cache for Redis** in prod | Backs RQ, caches API responses |
| Object storage | **Azure Blob Storage** in prod; **Azurite** (Microsoft's official emulator) in local Docker | FITS cache, generated previews, analysis outputs |
| Local AI runtime | Ollama, llama.cpp, or vLLM depending on model | Practical local inference options |
| Cloud AI | **OpenAI Responses API and/or Azure OpenAI Service** behind a provider interface (`AI_PROVIDER`) | Optional premium/deeper reasoning and vision analysis; portable |
| Secrets | `.env` locally → **Azure Key Vault** in prod (via managed identity) | Avoid checked-in credentials |
| Observability | structlog locally → **Azure Monitor + Application Insights** in prod | Logs, metrics, traces |
| Local dev | Docker Compose | Reproducible setup |
| Deployment | **Azure Static Web Apps** (Next.js) + **Azure Container Apps** (API + worker) | Scales to zero, low ops overhead, native Next.js + container support |

### Opinionated call

Do **not** try to make Node.js do the astronomy-heavy work. Let Node/Next.js handle the pretty human-facing stuff. Let Python do the cosmic mud-wrestling with FITS files.

### Cross-cloud reality

JWST public data lives on **AWS S3** (`s3://stpubdata/jwst`) and the new-data notifications come from an **AWS SNS topic**. The app cannot move those — STScI hosts them on AWS, and that's that. The app *reads* JWST data from AWS anonymously (no AWS account/credentials needed for public files) and writes everything else (preview PNGs, FITS cache, analysis JSON, app database) to **Azure**. Whenever the worker touches an AWS S3 URI, treat it as a read-only external resource, not as part of our infrastructure.

---

## 3. Data Sources

### Primary source: MAST

JWST data products are stored in the **Mikulski Archive for Space Telescopes (MAST)**. The archive includes raw uncalibrated exposures, calibrated data products, engineering data, and guide-star data.

The app should use MAST as the authoritative source for:

- Observation metadata
- Program IDs
- Instrument/filter/exposure information
- Data product URIs
- File availability
- Calibration/version metadata
- Download links

### Programmatic access

MAST provides programmatic API access and Virtual Observatory-style services. For Python, `astroquery.mast` is a practical starting point for metadata search.

Candidate approaches:

1. **MAST API / MAST Portal services**
   - Best for archive metadata and product discovery.
2. **`astroquery.mast`**
   - Best for Python-first prototyping.
3. **MAST JWST Mission Search**
   - Best as a reference UI to understand filters and available columns.
4. **CADC / ESA mirrors**
   - Optional redundancy later.

### AWS Open Data path (read-only external source)

JWST public data is also listed through AWS Open Data with:

- Public S3 bucket: `s3://stpubdata/jwst` (us-east-1, anonymous read)
- AWS SNS topic for new-data notifications: `arn:aws:sns:us-east-1:879230861493:stpubdata/jwst`

This is potentially the best path for the “instant alert when data drops” part. The worker uses anonymous S3 access (`boto3` with `UNSIGNED` config, or `aioboto3`/`obstore`) — **no AWS credentials are required** because we only read public objects.

Use this in two modes:

1. **Event mode**
   - Subscribe an HTTPS endpoint hosted on Azure to the AWS SNS topic. SNS → HTTPS is cross-cloud-friendly; the subscription handshake is a single confirmation POST.
   - Endpoint: `POST /api/webhooks/aws/jwst` on the Container Apps-hosted API.
   - Parse the SNS message, dedupe against the `data_products` table, and enqueue an ingestion job.
   - If we ever want SQS instead, an AWS account is required; for now stick with HTTPS to keep the app Azure-only on the credentialed side.
2. **Fallback polling mode**
   - Periodically list S3 prefixes anonymously and compare against known products.
   - Poll MAST metadata for public/reprocessed products.

### Where our data goes (Azure)

Anything *we* produce or cache lives in Azure, never in an S3 bucket we own:

- **Downloaded FITS files** → `webbwatch-fits` Blob container.
- **Generated preview PNGs/charts** → `webbwatch-previews` Blob container (with public-read access for the share-friendly URLs).
- **Analysis JSON** → Postgres rows + blob copy for large reports.
- **Database** → Azure Database for PostgreSQL (Flexible Server).
- **Cache / queue** → Azure Cache for Redis.

### Important product reality

“New” can mean multiple things:

- A new observation became public after the exclusive access period.
- A product was reprocessed with a newer JWST calibration pipeline/reference context.
- A high-level science product was contributed.
- A mirror/archive updated its copy.

The app needs to track all of these separately.

---

## 4. JWST Data Product Cheat Sheet

Prioritize user-friendly science products first.

| Product type | Meaning | MVP priority |
|---|---|---|
| `i2d` | Resampled 2D image | Very high |
| `s2d` | 2D spectral image | High |
| `s3d` | 3D IFU spectral cube | Medium-high, but heavier |
| `x1d` | Extracted 1D spectrum | High |
| `c1d` | Combined 1D spectrum | High |
| `cal` / `calints` | Calibrated exposure data | Medium |
| `rate` / `rateints` | Countrate data | Lower for MVP |
| `uncal` | Raw uncalibrated data | Low for MVP |
| `cat` / `phot` | Catalog/photometry products | High if available |
| `segm` | Segmentation map | Medium |

### MVP product focus

Start with:

1. `i2d` images
2. `x1d` spectra
3. `c1d` spectra
4. `s2d` spectral images

Avoid making `s3d` cubes the MVP centerpiece. They are cool, but they are also bulky little gremlins.

---

## 5. Core User Experiences

### A. Live data feed

A feed of newly discovered or newly public JWST products.

Each feed card should show:

- Target name
- Program ID
- Instrument
- Filter/grating
- Product type
- Public release status
- Calibration version/context
- File size
- Archive source
- Preview thumbnail or spectrum chart
- “Analyze locally” button
- “Deep AI review” button
- “Share this” button

### B. Watchlists and alerts

Users can create alerts for:

- Target names
- Program IDs
- Instruments
- Filters/gratings
- Product types
- Sky region / RA-Dec cone search
- Keywords
- Reprocessed products
- High-level science products

Notification channels:

- In-app notification
- Email
- Discord webhook
- RSS feed
- Optional push notifications later

### C. Product detail page

Each JWST data product gets a detail page:

- Metadata table
- FITS header highlights
- Preview image/spectrum
- Download links
- Related products
- Analysis history
- Reprocessing history
- Citation/source notes
- Community discussion/comments if public social features are enabled

### D. AI analysis workspace

A workspace that runs:

1. Deterministic analysis
2. Local AI summary
3. Optional cloud AI review
4. Human-readable report
5. Structured machine-readable output

The app should clearly separate **measured facts** from **AI interpretation**.

---

## 6. AI Analysis Design

### Principle: deterministic tools first, AI second

The AI should not be the first thing touching the data. First run boring, reliable, repeatable tools. Then feed their results to AI.

Boring tools win. Boring tools are how civilization avoids hallucinated quasars.

### Local analysis pipeline

For an image-like product:

1. Load FITS file with `astropy.io.fits`.
2. Extract FITS headers and key metadata.
3. Inspect HDUs and data shape.
4. Generate normalized preview image.
5. Apply stretch options:
   - Linear
   - Log
   - Asinh
   - Percentile clipping
6. Run basic image statistics:
   - Min/max/mean/median
   - Standard deviation
   - NaN count
   - Saturated pixels
   - Background estimate
7. Run source detection:
   - Basic thresholding
   - Connected components
   - Optional `photutils`
8. Generate a compact metadata + measurements summary.
9. Send preview image + summary to local AI model.
10. Save report.

For a spectrum-like product:

1. Load FITS/table data.
2. Identify wavelength and flux columns.
3. Generate spectrum plot.
4. Detect basic peaks/troughs.
5. Estimate signal/noise proxies.
6. Save plot and extracted features.
7. Send plot + metadata + measurements to local AI model.
8. Save report.

### Local AI role

The local model should provide:

- Plain-English explanation
- Metadata summary
- “Why this may be interesting”
- Suggested next checks
- Potential quality issues
- Tags for the feed

The local model should **not** make strong scientific claims by itself.

### Running on an RTX 3070

Assume many RTX 3070 cards have 8 GB VRAM. Design accordingly:

- Use quantized 4-bit/5-bit 7B–8B models for local text reasoning.
- For local vision, analyze generated PNG/WebP previews rather than raw FITS arrays.
- Keep one GPU model loaded at a time.
- Make local AI optional in worker settings.
- Use CPU/scientific libraries for first-pass FITS work.
- Save intermediate outputs so failed AI runs do not require re-downloading files.

### Cloud AI role

Use the cloud AI provider for:

- Deeper reasoning
- Vision over generated previews/charts
- Comparing multiple products
- Producing structured JSON analysis
- “Reviewer mode” that critiques the local model
- Explaining astrophysics concepts to non-experts
- Generating shareable summaries

Cloud AI should receive:

- Preview image or chart
- Product metadata
- Deterministic measurements
- FITS header highlights
- Archive links
- Known caveats
- Desired output schema

Cloud AI should not receive enormous raw FITS files unless a future workflow specifically supports chunking/attachments.

### Provider interface: OpenAI vs Azure OpenAI

Cloud AI is dual-provider. Both **OpenAI** (`api.openai.com`) and **Azure OpenAI Service** are supported behind a single `CloudAIProvider` interface, selected at runtime via the `AI_PROVIDER` env var (`openai` | `azure_openai`).

The official `openai` Python SDK natively supports both backends — the difference is configuration, not call sites:

| Setting | OpenAI direct | Azure OpenAI |
|---|---|---|
| Endpoint | `https://api.openai.com/v1` | `https://<resource>.openai.azure.com` |
| Auth | `OPENAI_API_KEY` | `AZURE_OPENAI_API_KEY` or managed identity + `azure-identity` |
| Model identifier | Model ID (e.g. `gpt-4.1-mini`) | **Deployment name** (set in Azure portal; can differ from model name) |
| API version | n/a | Required (`AZURE_OPENAI_API_VERSION`, e.g. `2025-01-01-preview`) |
| Regional availability | Most models global | Per-region; check before picking a model |

In prod on Azure, use **managed identity** via `azure-identity.DefaultAzureCredential` to call Azure OpenAI — no API key in Key Vault required.

The provider interface ships as part of Phase 6 (cloud AI). It exposes one method per analysis kind (e.g. `review_image_product`, `review_spectrum_product`, `critique_local_report`) and returns the structured `AnalysisReport` schema from §7.

---

## 7. Suggested Analysis Report Schema

```json
{
  "product_id": "string",
  "analysis_run_id": "string",
  "analysis_mode": "local | cloud | hybrid",
  "summary": "string",
  "measured_facts": [
    {
      "name": "string",
      "value": "string",
      "source": "metadata | header | computed"
    }
  ],
  "interesting_features": [
    {
      "feature": "string",
      "evidence": "string",
      "confidence": "low | medium | high"
    }
  ],
  "quality_flags": [
    {
      "flag": "string",
      "severity": "info | warning | critical",
      "details": "string"
    }
  ],
  "recommended_next_steps": [
    "string"
  ],
  "human_validation_required": true,
  "tags": [
    "nebula",
    "spectrum",
    "nircam"
  ],
  "model_notes": {
    "model": "string",
    "prompt_version": "string",
    "created_at": "datetime"
  }
}
```

---

## 8. Database Model

### Tables

#### `observations`

Stores the high-level observation.

Fields:

- `id`
- `mast_obs_id`
- `program_id`
- `target_name`
- `ra`
- `dec`
- `instrument`
- `proposal_type`
- `observation_date`
- `public_release_date`
- `created_at`
- `updated_at`

#### `data_products`

Stores individual downloadable products.

Fields:

- `id`
- `observation_id`
- `mast_product_id`
- `data_uri`
- `filename`
- `product_type`
- `file_extension`
- `file_size`
- `calibration_version`
- `crds_context`
- `cloud_uri`
- `mast_download_uri`
- `is_public`
- `first_seen_at`
- `last_seen_at`
- `content_hash`
- `status`

#### `product_previews`

Stores generated images/charts.

Fields:

- `id`
- `data_product_id`
- `preview_type`
- `storage_uri`
- `width`
- `height`
- `generation_params`
- `created_at`

#### `analysis_runs`

Stores deterministic/local/cloud analysis outputs.

Fields:

- `id`
- `data_product_id`
- `mode`
- `status`
- `model_name`
- `prompt_version`
- `input_summary_json`
- `output_report_json`
- `cost_estimate`
- `started_at`
- `completed_at`

#### `watchlists`

Stores user alert preferences.

Fields:

- `id`
- `user_id`
- `name`
- `criteria_json`
- `enabled`
- `created_at`

#### `alerts`

Stores matched alert events.

Fields:

- `id`
- `watchlist_id`
- `data_product_id`
- `reason`
- `delivery_status`
- `created_at`

#### `feed_posts`

Stores public/shareable posts.

Fields:

- `id`
- `data_product_id`
- `analysis_run_id`
- `title`
- `slug`
- `summary`
- `visibility`
- `created_by`
- `created_at`

---

## 9. API Endpoints

### Public/feed endpoints

```http
GET /api/feed
GET /api/feed/:slug
GET /api/products/:id
GET /api/observations/:id
GET /api/search
```

### Watchlist endpoints

```http
GET /api/watchlists
POST /api/watchlists
PATCH /api/watchlists/:id
DELETE /api/watchlists/:id
GET /api/alerts
```

### Analysis endpoints

```http
POST /api/products/:id/analyze/local
POST /api/products/:id/analyze/cloud
POST /api/products/:id/analyze/hybrid
GET /api/analysis-runs/:id
```

### Ingestion/admin endpoints

```http
POST /api/admin/ingest/mast-sync
POST /api/admin/ingest/s3-sync
POST /api/webhooks/aws/jwst
GET /api/admin/jobs
GET /api/admin/health
```

---

## 10. Repo Layout

```text
webbwatch-ai/
  apps/
    web/
      app/
      components/
      lib/
      package.json
  services/
    api/
      app/
        main.py
        routes/
        models/
        schemas/
        services/
        clients/
        workers/
      pyproject.toml
    worker/
      jobs/
      processors/
      analyzers/
      pyproject.toml
  packages/
    shared/
      schemas/
      types/
  infra/
    docker-compose.yml
    postgres/
    redis/
    minio/
    terraform/
  notebooks/
    mast_api_exploration.ipynb
    fits_preview_exploration.ipynb
  docs/
    architecture.md
    data-products.md
    ai-analysis.md
    runbook.md
```

---

## 11. MVP Roadmap

### Phase 0: Project setup

**Goal:** Create a working local development environment.

Tasks:

- Create monorepo.
- Add Next.js frontend.
- Add FastAPI backend.
- Add worker service.
- Add PostgreSQL, Redis, and **Azurite** (Azure Blob emulator) with Docker Compose.
- Add shared environment config.
- Add basic health checks.
- Add CI for lint/test.

Deliverable:

- `docker compose up` starts the whole app.
- Frontend can call backend `/health`.
- Worker can connect to Redis/Postgres.
- Azurite is reachable on `http://azurite:10000` from inside the compose network.

---

### Phase 1: MAST metadata discovery

**Goal:** Search and store public JWST metadata.

Tasks:

- Create MAST client module.
- Test query by:
  - Program ID
  - Target name
  - Instrument
  - Product type
  - Date/release status if available
- Store observations and data products in Postgres.
- Add deduplication by product URI/filename.
- Add admin sync endpoint.
- Add CLI command:
  - `python -m app ingest mast --instrument NIRCAM --limit 100`
- Build basic search UI.

Deliverable:

- App displays real JWST observations/products from MAST.

---

### Phase 2: New-data detection and alerts

**Goal:** Detect newly available public JWST products.

Tasks:

- Add scheduled MAST polling job.
- Add **anonymous** AWS S3 listing job for `stpubdata/jwst` (no AWS credentials).
- Investigate AWS SNS → HTTPS subscription to the JWST topic, with the HTTPS endpoint hosted on Azure Container Apps (`POST /api/webhooks/aws/jwst`).
- If SNS subscription works:
  - Confirm the subscription handshake.
  - Parse object notification events.
  - Convert new object into ingestion event.
- Add watchlist matching engine.
- Add in-app alerts.
- Add email/Discord alert adapter.

Deliverable:

- User can create a watchlist and receive an alert when matching data is detected.

---

### Phase 3: FITS download, cache, and preview generation

**Goal:** Turn scary FITS files into useful previews.

Tasks:

- Download selected FITS products on demand.
- Cache files in object storage.
- Extract FITS headers.
- Generate image previews for `i2d`.
- Generate spectrum charts for `x1d`/`c1d`.
- Store preview metadata.
- Add product detail page.
- Add “download original” link.
- Add file-size limits and queue safety.

Deliverable:

- Product page shows metadata plus usable preview image/chart.

---

### Phase 4: Deterministic analysis engine

**Goal:** Produce basic measured facts before using AI.

Tasks:

- Add analyzer interface:
  - `ImageAnalyzer`
  - `SpectrumAnalyzer`
  - `CubeAnalyzer` placeholder
- Image analysis:
  - Pixel stats
  - NaN/saturation flags
  - Background estimate
  - Basic source detection
- Spectrum analysis:
  - Flux/wavelength parsing
  - Peak/trough detection
  - Simple signal/noise proxy
- Save computed measurements as JSON.
- Display measurements on product page.

Deliverable:

- Every analyzed product has a reproducible measurement summary.

---

### Phase 5: Local AI analysis

**Goal:** Generate cheap local explanations and tags.

Tasks:

- Add local AI provider interface.
- Add support for local runtime:
  - Ollama, llama.cpp server, or vLLM
- Build prompt templates:
  - Image product summary
  - Spectrum product summary
  - Quality/caveat review
- Send deterministic measurements + preview image/chart + metadata.
- Save structured analysis report.
- Add local AI settings page:
  - Model name
  - GPU enabled
  - Max tokens
  - Temperature
- Add retry/failure handling.

Deliverable:

- User can click “Analyze locally” and get a useful report without cloud cost.

---

### Phase 6: OpenAI cloud review

**Goal:** Add premium/deeper review.

Tasks:

- Add OpenAI provider interface.
- Use structured output schema for reports.
- Add cloud analysis job.
- Add side-by-side local vs cloud comparison.
- Add cost estimate before running.
- Add user-level usage tracking.
- Add safety/caveat language:
  - “AI interpretation”
  - “Human validation required”
- Add “Reviewer Mode”:
  - Cloud model critiques local model’s report.
  - Flags unsupported claims.
  - Suggests follow-up checks.

Deliverable:

- User can run a cloud review and receive a structured, explainable report.

---

### Phase 7: Shareable discovery feed

**Goal:** Make it fun enough to spread online.

Tasks:

- Create public feed cards.
- Add shareable pages with clean slugs.
- Add generated social preview image.
- Add tags:
  - `NIRCam`
  - `MIRI`
  - `spectrum`
  - `galaxy`
  - `nebula`
  - `exoplanet`
  - `weird`
  - `needs-review`
- Add “interestingness score” based on:
  - Newness
  - Product type
  - Analysis flags
  - Source count/anomalies
  - User votes
- Add comments or lightweight reactions.
- Add RSS feed.

Deliverable:

- Someone can share a product page online and others can understand why it is interesting.

---

### Phase 8: Hardening, Azure deployment, and launch

**Goal:** Make the app stable, safe, deployed on Azure, and not bankrupting.

Tasks:

- Add authentication (Azure AD B2C or Auth.js with Microsoft provider).
- Add rate limiting.
- Move secrets to **Azure Key Vault**; use managed identity from Container Apps.
- Add job timeouts.
- Add file-size limits.
- Add Blob lifecycle policies (auto-delete old FITS cache, retain previews).
- Add admin dashboard.
- Add observability via **Azure Monitor + Application Insights** (logs, metrics, job-queue health, cost tracking).
- Add citation/acknowledgment guidance.
- Add Terms/Disclaimer page.
- Add backup/restore plan (Postgres point-in-time restore, Blob soft-delete).
- Provision Azure resources with **Bicep** (or Terraform) in `infra/azure/`:
  - Container Apps environment + two apps (api, worker)
  - Static Web App (web)
  - PostgreSQL Flexible Server
  - Azure Cache for Redis
  - Storage Account + Blob containers
  - Key Vault
  - Application Insights
- Wire GitHub Actions deploy workflow (federated identity → Azure, no long-lived secrets).

Deliverable:

- Public beta launch on Azure.

---

## 12. “Cool Factor” Features

The **Exoplanet Portrait Atlas** in section 20 is an additional product track alongside
the feed and deployment phases. Its first milestone is catalog ranking and evidence
briefs; detailed scientific modeling and image generation follow separately.

These are not MVP, but they are what make the project popular.

### Discovery cards

Each analysis generates a card:

> “New NIRCam image product from Program ####. AI flags unusual dense source region. Human review recommended.”

Include:

- Preview image
- Instrument/filter
- Why it is interesting
- Link to source data
- Confidence/caveat badge

### AI scientist modes

Offer multiple personalities/modes:

- **Explain Like I’m New**
- **Astrophysics Nerd Mode**
- **Skeptical Reviewer**
- **Anomaly Hunter**
- **Compare Against Related Products**

### Public anomaly board

A leaderboard of data products that need eyes:

- Most anomalous
- Newly public
- Recently reprocessed
- Community flagged
- AI-disagreed-with-itself

### Reproducible mini-notebooks

Generate a small Python notebook for an analysis run:

- How the product was loaded
- How preview was generated
- What measurements were computed
- What files were used

This is huge for credibility.

### Discord bot

A bot that posts:

> “New Webb data matching your watchlist just landed. NIRCam / F444W / i2d / target X.”

Space nerds love feeds. The machine speaks; the humans gather.

---

## 13. Guardrails and Scientific Honesty

Every AI report should show:

- What data product was analyzed
- Whether it was image/spectrum/cube/catalog
- Which deterministic measurements were used
- Which model generated the text
- What the model could not verify
- Whether human validation is needed
- Links to source data
- Calibration/version details

Avoid wording like:

- “We discovered…”
- “This proves…”
- “This is definitely…”

Prefer wording like:

- “This product appears to show…”
- “The analysis flags…”
- “This may warrant follow-up…”
- “The result is hypothesis-generating, not confirmation.”

The universe is already trying to kill certainty. No need to help it.

---

## 14. Key Technical Risks

### Risk: Too much data

Some JWST programs can produce huge numbers of products.

Mitigation:

- Do not bulk-download everything.
- Ingest metadata first.
- Download on demand.
- Prioritize product types.
- Add per-job limits.

### Risk: FITS complexity

FITS files can have multiple HDUs, dimensions, units, WCS, and oddities.

Mitigation:

- Build product-type-specific parsers.
- Save parser errors.
- Display raw header fallback.
- Start with `i2d`, `x1d`, and `c1d`.

### Risk: AI hallucination

AI may over-interpret images.

Mitigation:

- Use deterministic measurements first.
- Force structured output.
- Separate facts from hypotheses.
- Add reviewer mode.
- Require human validation for strong claims.

### Risk: New vs reprocessed confusion

A product can be newly reprocessed, not newly observed.

Mitigation:

- Track `first_seen_at`, `last_seen_at`, calibration version, CRDS context, and file hash.
- Label events:
  - `new_public_product`
  - `reprocessed_product`
  - `metadata_update`
  - `new_high_level_product`

### Risk: Cost explosion

FITS files, storage, and AI calls can get expensive.

Mitigation:

- Cache previews.
- Analyze on demand.
- Add user quotas.
- Show cloud cost estimate.
- Use local AI for first pass.
- Store only selected products.

---

## 15. First 10 Code Tasks

1. Create Git repo and monorepo structure.
2. Build Docker Compose with Postgres, Redis, MinIO.
3. Create FastAPI `/health`.
4. Create Next.js homepage with “Latest JWST Products” placeholder.
5. Add SQLAlchemy or SQLModel database models.
6. Add MAST metadata client prototype.
7. Store first 100 JWST metadata records.
8. Add product list UI.
9. Add FITS download/cache job.
10. Generate first preview image from an `i2d` product.

After that, add local analysis. Do not start with AI. Start with the data pipeline, because if ingestion is trash, the AI becomes a very expensive trash narrator.

---

## 16. MVP Definition of Done

The MVP is done when:

- A user can search recent public JWST products.
- A user can create a watchlist.
- The app can detect new or changed products.
- The app can show metadata and source links.
- The app can generate a preview image or spectrum chart.
- The app can run deterministic measurements.
- The app can run a local AI summary.
- The app can optionally run cloud AI review.
- The app can produce a shareable public page.
- Every report includes caveats and source attribution.

---

## 17. Suggested Implementation Order

Build in this order:

1. Metadata ingestion
2. Product database
3. Product list UI
4. FITS cache
5. Preview generation
6. Deterministic analysis
7. Local AI
8. Cloud AI
9. Alerts
10. Public feed/social layer

The alert system is exciting, but preview/analysis makes the app useful. A notification saying “a confusing file exists” is less magical than a notification saying “new Webb image, preview ready, possible weirdness flagged.”

---

## 18. Source Notes

These were used to shape the plan:

- STScI JWST data access documentation explains that JWST products are stored in MAST and include raw, calibrated, engineering, and guide-star data. It also notes that public data can be retrieved anonymously after the exclusive access period.
- STScI MAST API documentation confirms programmatic interfaces for scripted JWST data discovery and retrieval.
- The MAST JWST mission page lists JWST search tools including MAST JWST Search, MAST Portal, and MAST API.
- JWST pipeline documentation lists common product types such as `uncal`, `rate`, `cal`, `i2d`, `s2d`, `s3d`, `x1d`, `c1d`, `cat`, `segm`, and `phot`.
- AWS Open Data lists JWST public data files in S3 and a notification SNS topic for new data.
- OpenAI API documentation describes vision/image input capabilities through the Responses API and current model support for text and image inputs.

---

## 19. One-Sentence Build Strategy

Build a Python-powered JWST ingestion and FITS-analysis backend, wrap it in a slick Next.js public feed, then add local AI for cheap first-pass interpretation and OpenAI for optional “skeptical cosmic reviewer” mode.

---

## 20. Exoplanet Portrait Atlas (2026-10-18)

### 20.1 Goal and scientific contract

Start with every confirmed planet in the NASA Exoplanet Archive, combine evidence
across missions, and identify which worlds support the most informative simulated
view from approximately the Earth-Moon distance. Every portrait should expose its
observations, physical interpretations, rendering assumptions, and remaining unknowns.
High pixel resolution must never be presented as high observational resolution.

A text-to-image output is an **evidence-informed illustration**. A **physical simulation**
requires an explicit atmosphere/radiative-transfer model, its parameters, and comparisons
to measured observables. Detailed continents, oceans, weather, or surface geography
cannot be recovered merely by writing a longer prompt. Produce multiple plausible
scenarios where the data allow competing interpretations; image-generation seeds alone
are not scientific uncertainty samples.

"All known" means all confirmed objects in the chosen archive at a recorded snapshot
time. Keep TESS/Kepler candidates separate with their confirmation status; preserve
disputed/removed entries in snapshot history. A missing catalog spectrum does not prove
that no observation exists elsewhere.

### 20.2 Source integration

| Source | Contribution | Handling |
|---|---|---|
| NASA Exoplanet Archive `pscomppars` | One row per confirmed planet, system parameters and references | Starting census and availability triage; retain errors, limits and calculated-value provenance |
| Archive `ps` | Parameter sets associated with individual publications | Reconcile consistent parameters for physical models instead of blindly mixing composite values |
| TESS and Kepler/K2 light curves | Transit/orbit constraints and, where measurable, phase/eclipsing signals | Match aliases and host components; discovery facility is not a complete observation history |
| Archive `spectra` | Published transmission, eclipse and direct-imaging spectra across facilities | Inspect wavelength coverage, uncertainty, calibration and reductions; count independent observations separately |
| Hubble, JWST, Spitzer and ground-based follow-up | Atmospheric, thermal, reflectance and mass constraints | Link the underlying products and papers; qualify planet-specific versus host-only evidence |
| NExoList / MAST | JWST atmospheric program metadata, dates and public-product availability | Approved/planned programs earn no existing-data credit; distinguish observed, public and usable |

The archive warns that composite rows can mix publications and calculated estimates.
Use those rows for discovery, then resolve provenance before modeling.
[Composite-table documentation](https://exoplanetarchive.ipac.caltech.edu/docs/pscp_about.html).

The current spectroscopy interface includes transmission, eclipse and direct-imaging
data; alternative reductions of one observation can appear separately.
[Atmospheric spectroscopy documentation](https://exoplanetarchive.ipac.caltech.edu/docs/atmospheres/atmospheres_home.html).
NExoList includes both archived and planned JWST programs.
[JWST archive holdings](https://exoplanetarchive.ipac.caltech.edu/docs/JWSTMission.html).

### 20.3 Runnable milestone: catalog readiness proxy

Implemented as `python -m app exoplanets rank` and `python -m app exoplanets prompt`.
The catalog milestone is a CLI prototype, with no database migration, scheduled job,
atmosphere retrieval, image-generation call, or automatic AI spend. A subsequent UI
milestone adds `/exoplanets`: the user's original HD 189733 b image, a Measured / Inferred /
Illustrative panel with linked evidence, and downloads for the original image, prompt
and provenance. This first curated example works independently of the API.

`catalog-readiness-v1` is a transparent prioritization heuristic, not a scientific
confidence percentage. Its components are:

| Component | Maximum points |
|---|---:|
| Radius / true mass | 10 / 8 |
| Period / semi-major axis / equilibrium-temperature estimate | 4 / 4 / 4 |
| Host effective temperature / radius | 6 / 4 |
| At least one published spectrum of any supported type | 40 |
| At least two different spectrum types | 10 |
| Eclipse or direct-imaging spectrum available | 10 |

Parameter credit requires a positive finite value, a publication reference, and no
limit-only or archive-calculated flag. The mass field must identify true mass, not
`Msini` or a model estimate. Parameters with valid two-sided nonzero errors receive
full points; those lacking them receive half. This checks uncertainty availability,
not its magnitude or a publication's reliability. Equilibrium temperature remains a
model estimate even when published with errors.

Spectra contribute presence/type credit, never points proportional to bins, files,
papers, or repeated reductions. This does not assess S/N, wavelength coverage, species,
visible color, spatial information, or independent replication. A spectrum may contain
an upper limit or no atmospheric detection. Unknown counts remain explicitly unknown.
Approved JWST observation counts are retained for future follow-up but score zero.
All rows retain `appearance_assessed=false`.

Sort by score descending, assign shared ranks to equal scores, and sort tied names
alphabetically for display. Do not imply that the first alphabetical entry is the best
scientific target. Preserve all planets, including those with insufficient evidence.

Live snapshots check archive counts before and after retrieval, validate unique planet
names, and fail on truncation/count changes. Requests have timeouts and a 32 MiB response
budget. The manifest records query, timestamp, hashes, coverage and scoring version;
count checks do not guarantee a transactionally frozen archive. Local replay does not
claim current archive completeness. A new output directory is required for each run.

From `services/api`:

```powershell
.\.venv\Scripts\python.exe -m app exoplanets rank --live --output-dir ../../data/exoplanets/my-snapshot
.\.venv\Scripts\python.exe -m app exoplanets rank --catalog ../../data/exoplanets/my-snapshot/catalog.json --output-dir ../../data/exoplanets/my-replay
.\.venv\Scripts\python.exe -m app exoplanets prompt --catalog ../../data/exoplanets/my-snapshot/catalog.json --planet "HD 189733 b" --evidence ../../packages/shared/examples/hd189733b-appearance.json --output-dir ../../data/exoplanets/my-portrait
```

Ranking exports: `catalog.json`, `manifest.json`, `ranking.json` (score explanations),
and `ranking.csv` (sortable summary). Prompt exports: `brief.json` and `prompt.txt`.
Omitting `--evidence` produces a conservative bulk-parameter brief. Optional evidence
requires the matching planet, explicit claim kinds, and source URLs for scientific
claims; the CLI validates structure, not the truth or currency of those claims.

The HD 189733 b example separates published albedo constraints, a model-supported blue
hue, and invented cloud texture. The source concerns broad wavelength reflectance,
not resolved weather or a precise RGB image.
[Evans et al. (2013)](https://arxiv.org/abs/1307.3239).

### 20.4 Next milestone: rank actual appearance constraints

Enrich the shortlist with spectrum metadata and published analyses before assigning an
appearance-readiness score. Store each constraint with its value/distribution, unit,
wavelength band, epoch, uncertainty or upper limit, paper/product identifier, reduction
version and relationship to other reductions of the same observation.

Maintain separate visible-light and thermal/infrared rankings. Infrared molecular
features and thermal maps do not directly determine visible colors. Evaluate:

1. Bulk geometry and illumination, with physically consistent parameter sets.
2. Atmospheric composition and cloud/haze constraints, including retrieval degeneracy.
3. Temperature structure, phase coverage and evidence for spatial brightness variation.
4. Visible reflectance/albedo constraints for visible portraits; emission constraints
   for explicitly labeled infrared maps.
5. Measurement quality, independent replication, conflicting results and source coverage.

Version scoring weights and calibrate them against a reviewed pilot set. Display
unsearched sources separately from searched-but-empty sources; incomplete enrichment
must not become a confident "no data" claim. Keep the scientific interest/follow-up
priority separate from appearance readiness so well-studied hot giants do not obscure
unusual or less-studied worlds. TSM/ESM can inform future observing opportunities, not
replace evidence already obtained.

Useful pilots, not an asserted complete ranking:

- **HD 189733 b:** visible reflectance and atmospheric work; the supplied prompt example.
- **WASP-43 b:** phase-curve temperature constraints and model-dependent cloud/weather
  interpretations. [NASA's Webb study summary](https://science.nasa.gov/missions/webb/nasas-webb-maps-weather-on-planet-280-light-years-away/).
- **WASP-39 b:** atmospheric spectroscopy and chemistry as a test of translating
  composition constraints without inventing geography.
  [NASA's atmospheric study summary](https://science.nasa.gov/missions/webb/nasas-webb-reveals-an-exoplanet-atmosphere-as-never-seen-before/).

### 20.5 Prompt and rendering contract

The structured brief is the source of truth; the prose prompt is an export. Separate
reported constraints, model inferences and rendering assumptions. Retain the source
snapshot hash, prompt/model versions, parameter provenance and unknowns beside the image.

Default camera: **384,400 km from the planet's center**, phase angle 60 degrees, horizontal
field of view 45 degrees, square frame. Compute angular diameter as `2 asin(R / d)`;
at this distance an Earth-radius object spans about 1.9 degrees. A close crop is allowed
only with its changed field of view labeled. This is a virtual viewpoint, not a claim
that a stable moon orbit exists there. Reject missing/limit-only radii for scaled views;
calculated radii, when used, remain explicit scenario inputs.

For detailed visualizations, render disk geometry and illumination deterministically,
then use physical models for permitted appearance ranges. AI can supply illustrative
texture within those ranges. Preserve the geometry reference and inspect the generated
result for violations; a prompt alone cannot guarantee numerical fidelity. Label
infrared false color, artistic crops and invented texture. Show alternative physical
scenarios side by side, without assigning probabilities unless a calibrated inference
model actually supplied them.

### 20.6 Discovery loop and WebbWatch integration

The research opportunity is in reconciling observations and testing models: inconsistent
parameters, residual spectral features, cross-epoch variability, or gaps where another
observation would distinguish competing explanations. Forward-model spectra, eclipse
depths and phase curves from physical scenarios, then compare to observations with
uncertainties, instrument response and nuisance parameters. Use independent epochs or
held-out data where possible. Check calibration and stellar contamination before
escalating a residual. A generated image is not evidence for a discovery.

Add planet identities/aliases and evidence links alongside the existing JWST product
model; do not force TESS light curves into JWST filename/S3 assumptions. Resolve host
components and multi-planet systems explicitly. Reuse bounded downloads, provenance,
storage, optional AI providers and watchlist concepts. Future alerts should say which
new usable observation changed a planet's evidence or ranking. Catalog refreshes,
enrichment and image generation must remain separate jobs with separate budgets.

Delivery order:

1. **Implemented:** full-catalog snapshot, explainable proxy ranking, offline replay,
   sourced prompt export and one appearance-evidence example. The first web portrait
   preserves the user's image and presents its evidence through accessible category tabs.
   A ranked web catalog now adds search, facility/spectrum/score filters, shared ranks,
   per-planet evidence and copy/download prompt controls. It uses a verified bundled
   archive snapshot and the same scorer/prompt generator as the CLI; appearance enrichment
   now includes curated HD 189733 b and LTT 9779 b evidence. The second portrait uses
   CHEOPS/JWST/Hubble/ESPRESSO literature, a labeled narrower field of view, and a saved
   generation/refinement history. Pixel-level geometry and photometry remain unvalidated.
   In-app generation now creates separately versioned images from the selected catalog
   brief, with immutable prompt/evidence snapshots, linked category tabs, downloads and
   a saved-portrait archive. Local on-demand OpenAI calls have explicit configuration,
   duplicate-request protection and no automatic retry; production access is deferred.
2. **Next:** spectrum/program enrichment and reviewed visible/thermal pilot rankings.
3. **Then:** deterministic rendering, physical constraints and a comparative scenario gallery.
4. **Research extension:** reproducible physical modeling, residual tests and follow-up
   prioritization, with human scientific review before any discovery claim.
