# webbwatch-api

FastAPI service. Owns metadata APIs, search, watchlists, and analysis-run endpoints. Background work is delegated to `services/worker`.

## Run locally (without Docker)

```powershell
cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Then: <http://localhost:8000/health>

## Run via Docker

`docker compose -f infra/docker-compose.yml up api` from the repo root.
