# webbwatch-worker

Background job runner. Handles:

- MAST + S3 ingestion polling
- FITS download and cache
- Preview/spectrum chart generation
- Deterministic analysis
- Local AI calls (Ollama / llama.cpp)
- Cloud AI calls (OpenAI)

Currently uses **RQ** (`redis-queue`) for simplicity. Plan reserves the option to swap to Celery if scheduling/routing needs grow.

## Run locally

The worker imports `app.*` from the API package (MAST client, ingest service, models, settings). Install the API editable first, then the worker:

```powershell
cd services/worker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ../api      # provides app.clients.mast, app.services.ingest, etc.
pip install -e ".[dev]"
python -m worker.run       # connects to Redis and registers the schedule
```

The first time the worker process starts it registers the periodic jobs (`worker/schedule.py`). MAST polling defaults to 30 min, S3 listing to 6 h — both tunable via env (`MAST_POLL_INTERVAL_SECONDS`, `S3_POLL_INTERVAL_SECONDS`).
