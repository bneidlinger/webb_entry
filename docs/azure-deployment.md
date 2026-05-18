# Azure deployment overlay

WebbWatch AI deploys to Azure. This doc captures the *target* production topology; provisioning happens in Phase 8 (see plan §11). Local dev still uses Docker Compose + Azurite — no Azure account needed to develop.

## Topology

```
                       ┌──────────────────────────────┐
                       │  Azure Static Web Apps       │
  Users ──────────────►│  apps/web  (Next.js)         │
                       └──────────────┬───────────────┘
                                      │  /api/* (rewrite)
                                      ▼
                       ┌──────────────────────────────┐
                       │  Azure Container Apps        │
                       │  ┌────────────┐ ┌──────────┐ │
                       │  │  api       │ │ worker   │ │
                       │  │ FastAPI    │ │  RQ      │ │
                       │  └─────┬──────┘ └────┬─────┘ │
                       └────────┼─────────────┼───────┘
                                │             │
       ┌────────────────────────┼─────────────┼──────────────┐
       ▼                        ▼             ▼              ▼
┌─────────────┐         ┌──────────────┐  ┌────────┐  ┌──────────────┐
│ Azure DB    │         │ Azure Cache  │  │ Blob   │  │ Azure OpenAI │
│ for         │         │ for Redis    │  │ Storage│  │ (optional)   │
│ PostgreSQL  │         │              │  │        │  │              │
└─────────────┘         └──────────────┘  └────────┘  └──────────────┘
       ▲                                                     ▲
       │                                                     │
       └─────────────── Azure Key Vault ─────────────────────┘
                       (secrets, connection strings)

                       Azure Monitor + Application Insights
                       (logs, metrics, traces for all of the above)

                                      ▲
                                      │  HTTPS notification
       AWS SNS (stpubdata/jwst) ──────┘   (cross-cloud, no AWS account needed)
```

## Resource list (minimum viable Azure)

| Resource | SKU suggestion | Purpose |
|---|---|---|
| Resource group | `rg-webbwatch-<env>` | Container for everything |
| Container Apps Environment | Consumption | Hosts api + worker |
| Container App: `api` | min 1 replica, scale on HTTP concurrency | FastAPI |
| Container App: `worker` | min 0 replicas, scale on Redis queue depth (KEDA) | RQ |
| Static Web App | Standard | Next.js frontend |
| PostgreSQL Flexible Server | Burstable B1ms (dev) → GP D2s (prod) | App DB |
| Cache for Redis | Basic C0 (dev) → Standard C1 (prod) | RQ broker + cache |
| Storage Account (general v2) | LRS dev, ZRS prod | Blob containers |
| Container: `webbwatch-fits` | Private | Cached FITS downloads |
| Container: `webbwatch-previews` | Public read | Shareable preview PNGs |
| Key Vault | Standard | API keys, DB password |
| Log Analytics workspace | Pay-as-you-go | Container Apps logs |
| Application Insights | Workspace-based | API + worker telemetry |
| (Optional) Azure OpenAI | S0 | If `AI_PROVIDER=azure_openai` |

## Identity model

- All Container Apps get a **system-assigned managed identity**.
- The identity is granted:
  - `Storage Blob Data Contributor` on the storage account → Blob read/write without keys.
  - `Key Vault Secrets User` on the vault → DB password, OpenAI key.
  - `Cognitive Services OpenAI User` on the Azure OpenAI resource → if used.
- Postgres uses **Azure AD authentication** (no password in env) where feasible.
- The frontend Static Web App talks to the API over public HTTPS; no managed identity needed unless we add server actions that call Azure directly.

## Deployment automation

Phase 8 lands `infra/azure/` with **Bicep** modules:

```
infra/azure/
  main.bicep
  modules/
    container-apps.bicep
    postgres.bicep
    redis.bicep
    storage.bicep
    keyvault.bicep
    monitor.bicep
    openai.bicep        (conditional)
  parameters.dev.json
  parameters.prod.json
```

CI/CD via GitHub Actions uses **OIDC federated identity** (no Azure service principal secret in GitHub) to:

1. Build container images, push to ACR (or Container Apps' built-in registry).
2. `az deployment group create` to apply Bicep.
3. `az containerapp update --image ...` to roll out new revisions.

## JWST → Azure cross-cloud notifications

AWS SNS (`arn:aws:sns:us-east-1:879230861493:stpubdata/jwst`) supports HTTPS subscribers. Flow:

1. STScI publishes a new-data event to the SNS topic.
2. SNS POSTs the event to our Container Apps endpoint: `https://api.webbwatch.example/api/webhooks/aws/jwst`.
3. The API validates the SNS signature, enqueues an ingest job into Redis.
4. Worker pulls the FITS file from `s3://stpubdata/...` anonymously and writes it to our `webbwatch-fits` Blob container.

If SNS-to-HTTPS proves fragile, fall back to a CRON-style polling job inside the worker (same Container Apps replica). No AWS account is required for either mode.

## Cost guardrails

- Container Apps `worker` scales to **zero** when the Redis queue is empty (KEDA scaler).
- Blob lifecycle policy: auto-delete `webbwatch-fits` blobs older than 30 days; keep `webbwatch-previews` indefinitely.
- Static Web Apps Standard tier has a generous bandwidth allowance — fine for share-link traffic.
- Cloud AI calls always emit an estimate-before-spend confirmation in the UI (per plan §6).
