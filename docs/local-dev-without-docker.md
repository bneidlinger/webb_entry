# Local dev without Docker

Use this until Docker Desktop is installed. Each service runs in its own terminal.

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

Hold off until Docker is installed. The Phase-0 deliverable does not need them.

When Docker is ready, Azurite (Microsoft's Azure Blob emulator) comes up alongside Postgres via `docker compose up`. It uses the well-known dev account `devstoreaccount1` — the connection string in `.env.example` is safe to commit because that account only works against the emulator.

To browse the emulated Blob storage, install **Azure Storage Explorer** (free Microsoft desktop app) and connect to `Local & Attached → Storage Accounts → Emulator (Azurite)`.
