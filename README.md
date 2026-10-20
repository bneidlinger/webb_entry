# WebbWatch AI

A public-data discovery and analysis platform for the **James Webb Space Telescope (JWST)**. WebbWatch AI watches MAST and the AWS Open Data mirror for newly public data products, generates previews, runs a deterministic-first analysis pipeline with optional local and cloud AI review, and surfaces the results in a shareable feed.

See [`webbwatch_ai_project_plan.md`](./webbwatch_ai_project_plan.md) for the full design plan, schema, and roadmap.

## Stack

Primary cloud is **Azure** for our own infrastructure. JWST public data is read anonymously from AWS (`s3://stpubdata/jwst`) because that's where STScI hosts it — no AWS credentials needed.

| Layer | Local dev | Production (Azure) |
|---|---|---|
| Frontend | Next.js + TS + Tailwind | Azure Static Web Apps |
| API | FastAPI + Python 3.12+ | Azure Container Apps |
| Workers | RQ + Redis | Azure Container Apps + Azure Cache for Redis |
| Database | Postgres (Docker) | Azure Database for PostgreSQL Flexible Server |
| Object storage | **Azurite** (Azure Blob emulator, Docker) | Azure Blob Storage |
| Secrets | `.env` | Azure Key Vault (via managed identity) |
| Cloud AI | OpenAI **or** Azure OpenAI behind a provider interface (`AI_PROVIDER` env var) | Same — switchable |
| Local AI | Ollama / llama.cpp (RTX 3070, 8 GB VRAM target) | Optional self-hosted |
| Observability | structlog | Azure Monitor + Application Insights |

## Layout

```
webb_entry/
  apps/web/             # Next.js frontend
  services/api/         # FastAPI service
  services/worker/      # Background processors / analyzers
  packages/shared/      # Cross-language schemas / types
  infra/                # docker-compose, terraform, service configs
  notebooks/            # Exploratory notebooks (MAST, FITS)
  docs/                 # Architecture, runbook, data-products
```

## Quick start (local dev)

```powershell
# 1. Copy environment template
Copy-Item .env.example .env

# 2. Start infra + services
docker compose -f infra/docker-compose.yml up --build

# 3. Open
# Frontend:        http://localhost:3000
# API:             http://localhost:8000/health
# Azurite (Blob):  http://localhost:10000   (account: devstoreaccount1)
```

Inspect Azurite with **Azure Storage Explorer** (free Microsoft desktop app) — point it at `Local & Attached → Storage Accounts → Emulator (Azurite)`.

Without Docker (until Docker Desktop is installed), see [`docs/local-dev-without-docker.md`](./docs/local-dev-without-docker.md).

## Status

Metadata ingestion, watchlists, previews, deterministic analysis, and optional local/cloud
AI are implemented. Local sample testing is available without Docker or Redis:

```powershell
# From services/api, after installing the venv and applying migrations:
.\.venv\Scripts\python.exe -m app ingest mast --instrument NIRCAM --limit 1 --json
.\.venv\Scripts\python.exe -m app sample run --limit 3 --max-file-mib 16 --max-total-mib 32
.\.venv\Scripts\python.exe -m app sample benchmark --observations 100 --products-per-observation 10
# From the repository root:
.\scripts\start-local.ps1
```

The sample command downloads each selected FITS file once for previews and analysis,
skips completed products on rerun, and makes no AI calls. The benchmark uses synthetic
metadata in an isolated in-memory database. See [local development](docs/local-dev-without-docker.md)
and the [scale review and measured results](docs/HANDOFF.md#13-scale-review-and-local-validation-2026-10-01).
Exabyte-scale operation is a future architecture target, not a tested capability.

## Exoplanet Portrait Atlas prototype

Open `/exoplanets` in the web app, or follow **Portrait Atlas** from the homepage.
The first example preserves the user's HD 189733 b image and adds a keyboard-accessible
Measured / Inferred / Illustrative evidence panel, linked publications, the rendering
prompt, and downloadable image/provenance. This curated page works without the API.

The second portrait, **LTT 9779 b**, is at `/exoplanets/portraits/ltt-9779-b` and linked
from the homepage, example selector and planet catalog detail. It combines sourced
CHEOPS, JWST, Hubble and ESPRESSO constraints with a clearly hypothetical cloud
illustration. The evidence bundle retains the initial generation, framing refinement,
both prompts and image hashes. The 15° field of view is an explicit narrower framing
at the same 384,400 km distance; generated geometry and photometry remain unvalidated.

Open `/exoplanets/catalog` (or **Ranked exoplanet catalog** on the homepage) to browse
the full saved ranking. Search planets/hosts, filter by discovery facility, spectrum
type and minimum score, then open a planet for its score breakdown, evidence tabs,
copyable image prompt and evidence download. Run both the frontend and API for this
catalog; it does not need a database, Redis, a live archive connection or AI credentials.
The bundled snapshot contains 6,451 confirmed planets, retrieved October 19, 2026 UTC
(October 18 Pacific). It is explicitly a saved snapshot, not a live literature review.

The new exoplanet track combines public mission evidence to prioritize planets for
hypothetical portraits. A runnable CLI snapshots all confirmed planets from NASA's
Exoplanet Archive, exports an explainable catalog-availability ranking, and builds a
sourced image prompt. The score is a triage proxy, not image accuracy; atmospheric
modeling and detailed appearance ranking are later milestones.

```powershell
# From services/api; each output directory must be new:
.\.venv\Scripts\python.exe -m app exoplanets rank --live --output-dir ../../data/exoplanets/my-snapshot
.\.venv\Scripts\python.exe -m app exoplanets prompt --catalog ../../data/exoplanets/my-snapshot/catalog.json --planet "HD 189733 b" --evidence ../../packages/shared/examples/hd189733b-appearance.json --output-dir ../../data/exoplanets/my-portrait
.\.venv\Scripts\python.exe -m app exoplanets bundle --snapshot-dir ../../data/exoplanets/my-snapshot --evidence ../../packages/shared/examples/hd189733b-appearance.json --output-dir ../../data/exoplanets/my-web-bundle
```

Use `rank --catalog <catalog.json> --output-dir <new-directory>` for offline replay.
To refresh the web catalog, review the new bundle, then replace the three files under
`services/api/app/catalog_snapshots/exoplanets/` and restart the API. The bundle command
checks the source checksum and count, validates optional appearance evidence, strips
local paths and refuses to overwrite an existing directory.
`bundle --evidence` accepts either one appearance object or a list for multiple planets;
`prompt --evidence` takes the selected planet's single object. API endpoints are
`GET /api/exoplanets` and `GET /api/exoplanets/{id}`; IDs come from the list response.
Current prompts preserve parameter citations and numerical precision; most targets
default to neutral gray until appearance evidence is curated. The original portrait
and its original prompt are retained unchanged.
See [the design, scoring rubric and research roadmap](webbwatch_ai_project_plan.md#20-exoplanet-portrait-atlas-2026-10-18).

### Generate and save a portrait in WebbWatch

Open a planet in `/exoplanets/catalog`, review its prompt and evidence, then select
**Generate image**. `/exoplanets/generated` holds the version history. Every request
freezes the exact prompt, catalog snapshot, citations, uncertainties and evidence
categories before the model runs. A new generation creates a separate version.
Saved pages include image/prompt/evidence downloads and source-linked evidence tabs.
Catalog detail pages show a compact preview of the latest completed image, and the
ranked table includes clickable thumbnails. Both open that version's saved prompt
and evidence. A curated example is shown when there is no completed saved version.
Planets without a suitable radius are excluded from scaled generation; unreviewed
appearance remains neutral gray. No new literature review happens automatically.

For this local, single-user prototype, add `OPENAI_API_KEY` to the root `.env` and set
`PORTRAIT_GENERATION_ENABLE=true`. Keep the existing local SQLite `DATABASE_URL`
(`sqlite+pysqlite:///./webbwatch.db`) when running without Docker. From `services/api`,
run `.\.venv\Scripts\python.exe -m alembic upgrade head`, then restart the API.
The browser only receives configuration status, never the API key.

Generation uses the [OpenAI Images API](https://developers.openai.com/api/docs/guides/image-generation),
one 1024×1024 medium-quality PNG per request. The configured model is shown before
generation; override it with `PORTRAIT_IMAGE_MODEL`. API usage is billed separately.
This website flow is separate from the built-in imagegen tool used for curated example 002.
Requests execute in the API background process without Redis. A database lock admits
one active generation; request IDs prevent duplicate paid calls. Requests are never
automatically retried. A process interruption becomes visible after the request deadline
(timeout plus 120 seconds); its saved brief remains available. Production/remote writes
are disabled pending authentication and a durable worker deployment.

Back up both the database and image storage: by default files are under
`services/api/preview_cache/planet-portraits/<generation-id>/` with `image.png`, `prompt.txt`
and `evidence.json`. The existing Azure storage adapter is used when configured.
The generated image's scale, illumination and photometry are not independently validated.
