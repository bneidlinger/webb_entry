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

## State (2026-05-18)

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

**Phase 3 — preview + spectrum chart generation** ← *next*
- Workers fetch FITS from S3 (anonymous), generate PNG previews + spectrum charts via astropy + matplotlib, upload to Azure Blob (Azurite locally).
- Surface previews in the product feed + per-alert cards.
- See [plan §6](webbwatch_ai_project_plan.md).

**Phases 4–8** see [plan §11](webbwatch_ai_project_plan.md).

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
