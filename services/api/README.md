# webbwatch-api

FastAPI service. Owns metadata APIs, search, watchlists, and analysis-run endpoints. Background work is delegated to `services/worker`.

## Run locally (without Docker)

```powershell
cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Then: <http://localhost:8000/health>

No `.env` is needed: the database defaults to `services/api/webbwatch.db` (SQLite).
Don't copy the repo-root `.env.example` for native runs; it targets Docker's Postgres.
See [`docs/local-dev-without-docker.md`](../../docs/local-dev-without-docker.md).

## Run via Docker

`docker compose -f infra/docker-compose.yml up api` from the repo root.
