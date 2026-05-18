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

```powershell
cd services/worker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m worker.run
```
