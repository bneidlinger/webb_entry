# Local AI (Ollama) — setup & runbook

How to run the Phase 5 (text) and Phase 5.5 (vision) **local** AI passes on your own
machine. The model narrates over already-computed deterministic measurements — it
never sees raw FITS; the vision pass additionally looks at the rendered preview PNG.
Everything here is **opt-in and off by default**.

## How it fits — the data flow

```
MAST ingest ──▶ (watchlist-matched products only) ──▶ preview-gen + deterministic analysis
                                                              │ analysis succeeds
                                                              ▼
                                              text AI report  (mode="local")  ← auto
                                                              │ you click "Generate vision summary"
                                                              ▼
                                          vision AI report  (mode="local_vision")  ← on-demand
```

- AI runs **only for watchlist-matched products** (by design — bounds egress + cost).
  No watchlist match → no analysis → nothing for the AI to narrate.
- The **text** pass auto-runs once deterministic analysis succeeds.
- The **vision** pass is **on-demand** (a button) and needs the preview PNG to already
  exist. It loads a heavier model, so it never runs automatically (one GPU model at a time).
- Reports appear on the product detail page and at `GET /api/products/{id}/ai-reports`.

## Prerequisites

1. **Ollama** installed and running — <https://ollama.com>. On Windows it runs as a
   service (`Get-Service Ollama`) and serves on `http://localhost:11434`. Our
   OpenAI-compatible client **adds `/v1`** → `http://localhost:11434/v1`.
2. **Redis** reachable (the worker and the enqueue path need it; default
   `redis://localhost:6379/0`). No Docker? Use Memurai (native Windows), WSL
   (`apt install redis-server`), or `docker run -p 6379:6379 redis`.
3. **API + worker venvs** set up — see [`CLAUDE.md`](../CLAUDE.md) and
   [`services/worker/README.md`](../services/worker/README.md) — and the DB migrated
   (`python -m alembic upgrade head` in `services/api`).

## 1. Pull the models

```powershell
ollama pull llama3.1:8b-instruct-q4_K_M   # text (Phase 5)   — fits 8 GB
ollama pull llava:7b                       # vision (Phase 5.5) — fits 8 GB
```

We never auto-pull (a job would block on a multi-GB download), so a missing model is
recorded as a **permanent** `model_not_found`. On a ≥12 GB GPU you can swap in
`llama3.2-vision:11b` for better vision — just set `LOCAL_AI_VISION_MODEL` to match.

## 2. Configure (repo-root `.env`)

Both the API and the worker read the repo-root `.env` (via `../../.env`), so put the
flags there:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434/v1    # MUST end in /v1
LOCAL_AI_ENABLE=true                          # text pass auto-runs after analysis
LOCAL_AI_VISION_ENABLE=true                   # enables the on-demand vision button
LOCAL_AI_MODEL=llama3.1:8b-instruct-q4_K_M
LOCAL_AI_VISION_MODEL=llava:7b
# optional tuning (defaults shown):
LOCAL_AI_MAX_TOKENS=1024
LOCAL_AI_TEMPERATURE=0.2
LOCAL_AI_REQUEST_TIMEOUT_SECONDS=120
REDIS_URL=redis://localhost:6379/0
```

If you run the **worker in Docker** but Ollama on the host, use
`OLLAMA_BASE_URL=http://host.docker.internal:11434/v1` instead.

## 3. Start the worker

```powershell
cd services\worker
.\.venv\Scripts\Activate.ps1
python -m worker.run     # registers the schedule + drains the default/ingest/analyze queues
```

AI jobs run on the `analyze` queue. (To drain just that queue without the scheduler:
`rq worker -u $env:REDIS_URL analyze`.) The worker treats Ollama like Redis — if it's
unreachable the job records `ollama_unreachable` and stays retry-eligible.

## 4. Give the AI something to narrate (watchlist + ingest)

With the API running (`uvicorn app.main:app --port 8000`), create a watchlist that will
match incoming data, then ingest some public JWST metadata. Easiest via the Swagger UI
at <http://localhost:8000/docs>, or:

```powershell
# a) a watchlist that matches incoming products
curl.exe -X POST http://localhost:8000/api/watchlists -H "Content-Type: application/json" `
  -d '{"name":"NIRCam imaging","criteria_json":{"instruments":["NIRCAM"],"product_types":["i2d"]},"enabled":true}'

# b) ingest (or wait for the 30-min MAST poll / POST /api/admin/ingest/mast-sync)
$env:PYTHONIOENCODING = "utf-8"
cd services\api; python -m app ingest mast --instrument NIRCAM --limit 10
```

A matched product → preview + analysis enqueued → analysis success auto-enqueues the
**text** report.

## 5. See it

- Open `http://localhost:3000/products/<id>` (or `GET /api/products/<id>/ai-reports`).
  The **AI summary** card appears once the worker finishes — the **first** call is slow
  (cold-start weight load, 30 s+).
- For **vision**, click **Generate vision summary** on that page (the preview must have
  rendered). A second card tagged **vision** appears.
- **Regenerate AI summary** re-runs the text pass (force).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "No AI summary yet" never fills in | `LOCAL_AI_ENABLE` isn't `true`; or the product isn't watchlist-matched (so no analysis ran); or the worker / Redis isn't up. |
| Report row shows `ollama_unreachable` | Ollama isn't running, or `OLLAMA_BASE_URL` is missing `/v1`. Check `Get-Service Ollama` and port 11434. Transient — re-runs when it's back. |
| `model_not_found` (permanent) | The exact tag in `LOCAL_AI_MODEL` / `LOCAL_AI_VISION_MODEL` wasn't pulled. `ollama pull` it, then **Regenerate**. |
| Vision button → `vision_disabled` | `LOCAL_AI_VISION_ENABLE` isn't `true`. |
| Vision skips with `no_preview` | The preview hasn't rendered yet (or failed). Wait for preview-gen — vision needs the full PNG. |
| First request times out | Cold-start weight load. The job timeout is 300 s; raise `LOCAL_AI_REQUEST_TIMEOUT_SECONDS` on slow hardware. |
| Vision slow / OOM on 8 GB | Text and vision are different models and Ollama swaps them (one at a time). `llava:7b` fits 8 GB; `llama3.2-vision:11b` wants ≥12 GB. |

## Notes

- AI output is **interpretation, not measurement** — every report carries
  `human_validation_required`, and the deterministic measurements stay authoritative
  (plan §6 / §13). The vision prompt is told to corroborate visually but never read
  numbers off the image.
- Text and vision reports **coexist** (`mode` `local` vs `local_vision`); bumping a
  prompt's `PROMPT_VERSION` forks a new row. The API returns the latest per
  `(mode, model_name)`.
- **Cloud AI** (OpenAI / Azure OpenAI) is Phase 6 — see [`docs/HANDOFF.md`](HANDOFF.md) §7d.
