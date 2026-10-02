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
