# Local dev without Docker

Use this until Docker Desktop is installed. Each service runs in its own terminal.
For the shortest path to the Exoplanet Portrait Atlas, follow
[Try it on your computer](../README.md#try-it-on-your-computer) in the README; this page
adds developer tooling, the bounded JWST sample pipeline, the worker and cloud models.

Commands are PowerShell. On macOS/Linux use `python3 -m venv .venv`,
`source .venv/bin/activate`, and `.venv/bin/python` wherever this page says
`.\.venv\Scripts\python.exe`.

## 1. API (FastAPI): install, configure, migrate, launch

```powershell
cd services\api
# Install
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
# Configure: nothing required for native dev (see below)
# Migrate: creates or updates services/api/webbwatch.db
python -m alembic upgrade head
# Launch
uvicorn app.main:app --reload --port 8000
```

Then: <http://localhost:8000/health> and <http://localhost:8000/docs>.

**Configuration.** Settings come from environment variables first, then `.env` files:
the API reads `services/api/.env` and the repo-root `.env`, and the repo-root file wins
when both set the same key. The defaults suit native development: SQLite at
`services/api/webbwatch.db`, previews under `services/api/preview_cache/`, and Redis at
`redis://localhost:6379/0` (only the worker and enqueue paths need Redis).

The repo-root `.env.example` is the **Docker** template. Its `DATABASE_URL` and
`REDIS_URL` use the Compose hostnames `postgres` and `redis`, so copying it unchanged
makes native migrations fail with `failed to resolve host 'postgres'`. For native dev,
leave the root `.env` absent, create it with only the keys you need, or override:

```dotenv
DATABASE_URL=sqlite+pysqlite:///./webbwatch.db
REDIS_URL=redis://localhost:6379/0
```

The relative SQLite path resolves against the working directory, so run the API, CLI
and migrations from `services/api`.

## 2. Frontend (Next.js)

```powershell
cd apps\web
npm install
npm run dev
```

Then: <http://localhost:3000>. The health badge calls `NEXT_PUBLIC_API_BASE_URL/health`
(default `http://localhost:8000`). Set `NEXT_PUBLIC_API_BASE_URL` before `npm run dev`
if the API runs elsewhere, and add the web origin to the API's `CORS_ALLOWED_ORIGINS`.

## 3. Bounded JWST sample workflow (verified 2026-10-01)

With the API installed and migrated (section 1), no Redis, Azure, Ollama, or API key
is needed:

```powershell
cd services/api
# Optional: fetch a small metadata page if the catalog is empty.
.\.venv\Scripts\python.exe -m app ingest mast --instrument NIRCAM --limit 1 --json
# At most 3 eligible files, <=16 MiB each, <=32 MiB total download allowance.
.\.venv\Scripts\python.exe -m app sample run --limit 3 --max-file-mib 16 --max-total-mib 32
# Offline synthetic metadata: initial ingest and idempotent replay, no persistent DB writes.
.\.venv\Scripts\python.exe -m app sample benchmark --observations 1000 --products-per-observation 10
cd ../..
.\scripts\start-local.ps1
```

Open <http://localhost:3000> and <http://localhost:8000/docs>. The launcher applies
migrations, then starts hidden processes bound to loopback and records process IDs and
logs under `logs/`. It refuses to start if ports 3000 or 8000 are occupied. `-Sample`
processes the bounded sample before launching. It uses the existing venv and
node_modules and does not install dependencies.
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

## 4. Worker (RQ)

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

## 5. Postgres + Azurite

Native sample testing does not require Postgres or Azurite.

When Docker is ready, run `docker compose --env-file .env -f infra/docker-compose.yml up --build`
from the root. The API applies migrations before serving; the worker waits for it.
A separate `rqscheduler` process dispatches recurring jobs (RQ's built-in scheduler
does not consume rq-scheduler registrations). The default preview backend is a shared
local volume. Azurite is available for explicit Blob testing: configure a full connection
string using its published emulator credentials. Also configure browser-accessible Blob
URLs/access before using that backend; the native sample uses API-served PNGs.

To browse the emulated Blob storage, install **Azure Storage Explorer** (free Microsoft desktop app) and connect to `Local & Attached → Storage Accounts → Emulator (Azurite)`.

## 6. Cloud model choices

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
