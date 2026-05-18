# CLAUDE.md

Orientation for Claude sessions in this repo. Keep this file tight — it loads on every session.

## What this is

**WebbWatch AI** — a public-data discovery and analysis platform for the James Webb Space Telescope. Watches MAST + the AWS Open Data mirror for newly public JWST data products, generates previews, runs deterministic-first analysis with optional local and cloud AI review, and surfaces results in a shareable feed.

Source of truth for design decisions: [`webbwatch_ai_project_plan.md`](webbwatch_ai_project_plan.md). Defer to it for the *why*; this file covers *how things are wired right now*.

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
services/worker/         RQ skeleton; not yet wired into anything
packages/shared/         JSON Schema + TS types for cross-language contracts
infra/docker-compose.yml Postgres + Redis + Azurite + api + worker + web
docs/                    azure-deployment.md, local-dev-without-docker.md
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

## State (2026-05-17)

**Phase 0 — scaffold** ✓ shipped (`commit 22223f3`)
- Monorepo, Next.js 15 + Tailwind, FastAPI with `/health`, RQ worker skeleton, Azurite/Postgres/Redis in compose, GitHub Actions CI, `CloudAIProvider` interface with OpenAI + Azure OpenAI adapters.

**Phase 1 — MAST metadata ingestion** ✓ shipped (`commit 08ff118`)
- SQLAlchemy ORM (Observation, DataProduct) + Alembic migration.
- `MastClient` (astroquery wrapper) + `ingest_observations()` (idempotent upsert).
- CLI: `python -m app ingest mast --instrument NIRCAM --limit 100`.
- API: `GET /api/observations`, `GET /api/observations/{id}`, `GET /api/products`, `GET /api/products/{id}`, `POST /api/admin/ingest/mast-sync`.
- Frontend home page shows real JWST products as a table.
- E2E verified locally: 10 obs / 42 products ingested from real MAST; re-ingest produced 0/0 (dedup works).
- 8 unit tests pass, ruff clean, frontend typechecks + builds.

**Phase 2 — new-data detection + alerts** ← *next*

**Phases 3–8** see [plan §11](webbwatch_ai_project_plan.md).

## Phase 2 directions — new-data detection + alerts

Goal: detect newly available public JWST products and notify users who care.

### What's already in place that helps

- Idempotent ingest (`ingest_observations`) tracks `first_seen_at` and `last_seen_at` on every product, so polling is safe to run repeatedly — new rows naturally surface.
- `MastClient.fetch_jwst()` is the same code path the CLI uses; reuse it from worker jobs.
- The worker skeleton (`services/worker/`) is wired with an RQ entry point but no jobs are scheduled yet.

### Tasks (in build order)

1. **Wire the API ↔ Redis ↔ worker contract.**
   - Move `services/api/app/services/ingest.py` into `packages/shared/` (or symlink/copy into worker) so both sides import the same code. Easiest first cut: have the worker `pip install -e ../api`.
   - Add a `webbwatch-api` dep on the worker's pyproject if going that route.

2. **Scheduled MAST polling job.**
   - Add `services/worker/worker/jobs/mast_poll.py` that calls `MastClient.fetch_jwst()` for a list of configured instruments and runs `ingest_observations()`. Schedule with `rq-scheduler` or a cron sidecar. Default cadence: every 15 min.
   - Emit one structured log line per run with the `IngestResult` summary so we can chart freshness later.

3. **Anonymous AWS S3 listing job.**
   - Add `services/worker/worker/jobs/s3_jwst_listing.py` using `boto3` with `botocore.UNSIGNED` config to list `s3://stpubdata/jwst/` prefixes. No AWS account/keys.
   - Compare results against `data_products.cloud_uri` to detect previously-unseen S3 objects (these can lead reprocessed-product detection ahead of MAST).
   - Schedule less often than MAST (hourly).

4. **AWS SNS → HTTPS subscription.**
   - Add `POST /api/webhooks/aws/jwst` to the API. Implement the SNS HTTP subscription handshake (`SubscriptionConfirmation` message type → fetch `SubscribeURL`) and signature verification per AWS docs.
   - On `Notification` messages, parse the S3 event payload and enqueue an ingestion job.
   - Initially this stays disabled in production until we have an Azure Container Apps URL to register with AWS SNS.

5. **Watchlists.**
   - New ORM model `Watchlist(id, user_id, name, criteria_json, enabled, created_at)`. For Phase 2, `user_id` can be a hardcoded "default" string until auth lands in Phase 8.
   - `criteria_json` schema (see plan §5.B): `{instruments: [], programs: [], targets: [], product_types: [], cone: {ra, dec, radius_arcsec}, keywords: []}`.
   - Alembic migration; CRUD endpoints under `/api/watchlists`.

6. **Watchlist matching engine.**
   - New service: `app/services/match.py`. Single function `matches(product, watchlist) -> bool` driven by the criteria JSON.
   - Hook into `ingest_observations()`: when a product is newly *created*, run all enabled watchlists and emit alerts for matches. Don't re-alert on `updated` rows.

7. **Alerts table + in-app surfacing.**
   - ORM model `Alert(id, watchlist_id, data_product_id, reason, delivery_status, created_at)`.
   - `GET /api/alerts?watchlist_id=&unread=true` + a frontend page at `/alerts`.

8. **Delivery adapters.**
   - Email (Azure Communication Services Email — bonus Azure practice) — gated behind env config so local dev works without it.
   - Discord webhook (simplest external integration; POST to a URL).
   - RSS feed: `GET /api/feed.rss` rendering recent alerts (per-watchlist token if we want privacy later).

### Architectural calls already made (don't re-litigate)

- **RQ over Celery** — keep it unless scheduling needs explicitly outgrow `rq-scheduler`.
- **SQLite locally, Postgres in prod** — both share the same SQLAlchemy code; no per-dialect branches in models.
- **JWST SNS → HTTPS endpoint on Azure** rather than AWS SQS — avoids AWS account requirement (plan §3, Azure amendment).
- **Watchlist criteria as a JSON column**, not a separate criteria table. SQLite + Postgres both support JSON well enough for Phase 2 cardinality.

### Open questions worth asking the user before starting

- Default poll cadence (15 min for MAST, hourly for S3 sound right?).
- Email delivery via Azure Communication Services (more Azure practice) or skip email for Phase 2 and only do in-app + Discord?
- Do we need a real auth user model in Phase 2, or stay with the hardcoded `user_id="default"` until Phase 8?
- Should the worker get its own copy of the ingest code, or should we extract it into a shared package now? (Pulls forward refactor cost; deferring is fine.)

### Phase 2 done when

- The worker is scheduled, running, and polling MAST without manual intervention.
- A user can `POST /api/watchlists` with a criteria payload and receive an in-app alert when matching data arrives.
- At least one delivery adapter (Discord or email) successfully posts on alert creation.
- New tests cover: watchlist matching logic, the SNS subscription handshake (mocked), and end-to-end "fresh product triggers alert".
