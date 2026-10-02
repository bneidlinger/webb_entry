# Local dev without Docker

Use this until Docker Desktop is installed. Each service can run in its own terminal.

## Bounded sample workflow (verified 2026-10-01)

After installing dependencies below, leave the root Docker-oriented `.env` absent for
native development, or override its database/Redis endpoints with localhost settings.
SQLite and local preview storage are the defaults; no Redis, Azure, Ollama, or API key
is needed for the sample workflow.

```powershell
cd services/api
.\.venv\Scripts\python.exe -m alembic upgrade head
# Optional: fetch a small metadata page if the catalog is empty.
.\.venv\Scripts\python.exe -m app ingest mast --instrument NIRCAM --limit 1 --json
# At most 3 eligible files, <=16 MiB each, <=32 MiB total download allowance.
.\.venv\Scripts\python.exe -m app sample run --limit 3 --max-file-mib 16 --max-total-mib 32
# Offline synthetic metadata: initial ingest and idempotent replay, no persistent DB writes.
.\.venv\Scripts\python.exe -m app sample benchmark --observations 1000 --products-per-observation 10
cd ../..
.\scripts\start-local.ps1
```

Open <http://localhost:3000> and <http://localhost:8000/docs>. The launcher uses hidden
processes bound to loopback and records process IDs and logs under `logs/`. It refuses
to start if ports 3000 or 8000 are occupied. `-Sample` processes the bounded sample before
launching. It uses the existing venv and node_modules and does not install dependencies.
To stop a launched service, use its recorded PID with `taskkill /PID <pid> /T` so its
child process also stops; do not terminate every Python/Node process on the machine.

`sample run` selects the smallest eligible public products with known positive sizes.
It stores previews and analysis in the configured database/storage, reuses a single
download for both jobs, and performs no AI or alert delivery. Repeating a completed run
downloads zero bytes. A failed transfer conservatively consumes its full allowance.
The global `FITS_MAX_DOWNLOAD_BYTES` cap also applies (default 256 MiB). Decoded arrays
may use more RAM than the file size; the limit is a download guard, not a RAM bound.
An observation limit bounds the metadata page, not the number of products associated
with each observation. See HANDOFF section 13 for remaining archive-scale work.

## 1. API (FastAPI)

```powershell
cd services\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DATABASE_URL = "sqlite+pysqlite:///./dev.db"   # temporary, until Postgres is up
$env:REDIS_URL = "redis://localhost:6379/0"
uvicorn app.main:app --reload --port 8000
```

Then: <http://localhost:8000/health>

Note: the Phase-0 API does not yet talk to Postgres or Redis, so the env vars above only matter once Phase 1 ingestion lands.

## 2. Frontend (Next.js)

```powershell
cd apps\web
npm install
npm run dev
```

Then: <http://localhost:3000> — the health badge calls `NEXT_PUBLIC_API_BASE_URL/health` (default `http://localhost:8000`).

## 3. Worker (RQ)

Needs Redis. On Windows the easiest options are:

- Run Redis via WSL2: `wsl --install` then `sudo apt install redis-server && redis-server`
- Use Memurai (Windows-native Redis-compatible build)
- Wait for Docker

Once Redis is reachable:

```powershell
cd services\worker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m worker.run
```

## 4. Postgres + Azurite

Native sample testing does not require Postgres or Azurite.

When Docker is ready, run `docker compose --env-file .env -f infra/docker-compose.yml up --build`
from the root. The API applies migrations before serving; the worker waits for it.
A separate `rqscheduler` process dispatches recurring jobs (RQ's built-in scheduler
does not consume rq-scheduler registrations). The default preview backend is a shared
local volume. Azurite is available for explicit Blob testing: configure a full connection
string using its published emulator credentials. Also configure browser-accessible Blob
URLs/access before using that backend; the native sample uses API-served PNGs.

To browse the emulated Blob storage, install **Azure Storage Explorer** (free Microsoft desktop app) and connect to `Local & Attached → Storage Accounts → Emulator (Azurite)`.

## 5. Cloud model choices

The product page's Cloud model selector offers **GPT-6.1 Sol** (`gpt-6.1-sol`),
**Claude Opus 5.5** (`claude-opus-5-5`), and the configured default. Summary and
review actions both use that selection; each model's reports remain available
separately. Reviews require an existing local summary.

Set these in a local, uncommitted `.env` loaded by **both API and worker**:

```dotenv
CLOUD_AI_ENABLE=true
OPENAI_API_KEY=<your OpenAI API key>
ANTHROPIC_API_KEY=<your Anthropic API key>
CLOUD_AI_REASONING_MAX_TOKENS=8192
CLOUD_AI_REASONING_EFFORT=medium
```

Only the chosen provider's key is required. The explicit choices use direct
OpenAI and Anthropic APIs. `AI_PROVIDER`, `OPENAI_MODEL`, `ANTHROPIC_MODEL`, and
the Azure deployment settings control the separate configured-default option.
The existing default stays `openai` / `gpt-4.1-mini`.

Install the updated API package in the environment running each service
(`pip install -e services/api` from the repo root), then restart the API and RQ
worker with Redis reachable. Compose users should rebuild the API and worker.
Keep the API and worker on the same database and settings. Native Windows
workers need a Windows-compatible RQ worker class; the provided Docker/WSL
Linux worker avoids that platform restriction.

The new models' 8,192-token output allowance includes reasoning and final JSON.
The UI estimates cost for the selected model before enabling generation. Costs
use standard uncached token rates; input token counts are approximate and billed
usage may differ. No paid cloud call is needed to display options or estimates.
Cloud generation remains off until `CLOUD_AI_ENABLE=true` is explicitly configured.

Provider references: [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/overview), and
[Opus migration guide](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide).
