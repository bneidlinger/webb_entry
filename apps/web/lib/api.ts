const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface HealthPayload {
  status: string;
  service: string;
  version: string;
  time: string;
}

export type HealthResult =
  | { ok: true; data: HealthPayload }
  | { ok: false; error: string };

export async function getApiHealth(): Promise<HealthResult> {
  try {
    const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const data = (await res.json()) as HealthPayload;
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

// ---------------------------------------------------------------------------
// Phase 1: JWST data products feed

export interface ProductRow {
  id: number;
  filename: string;
  product_type: string | null;
  file_size: number | null;
  cloud_uri: string | null;
  mast_download_uri: string | null;
  observation_id: number;
  mast_obs_id: string;
  target_name: string | null;
  instrument: string | null;
  filters: string | null;
  program_id: string | null;
  observation_date: string | null;
  public_release_date: string | null;
  thumbnail_url: string | null;
  preview_url: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProductListQuery {
  productType?: string;
  instrument?: string;
  programId?: string;
  targetName?: string;
  limit?: number;
  offset?: number;
}

export type Result<T> = { ok: true; data: T } | { ok: false; error: string };

export async function getProducts(
  q: ProductListQuery = {},
): Promise<Result<Page<ProductRow>>> {
  const params = new URLSearchParams();
  if (q.productType) params.set("product_type", q.productType);
  if (q.instrument) params.set("instrument", q.instrument);
  if (q.programId) params.set("program_id", q.programId);
  if (q.targetName) params.set("target_name", q.targetName);
  params.set("limit", String(q.limit ?? 50));
  params.set("offset", String(q.offset ?? 0));

  try {
    const res = await fetch(`${API_BASE}/api/products?${params.toString()}`, {
      // The feed updates from background ingestion; 10s is a reasonable freshness target.
      next: { revalidate: 10 },
    });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const data = (await res.json()) as Page<ProductRow>;
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

// ---------------------------------------------------------------------------
// Phase 2: alerts feed

export interface AlertRow {
  id: number;
  watchlist_id: number;
  watchlist_name: string;
  data_product_id: number;
  filename: string;
  product_type: string | null;
  target_name: string | null;
  instrument: string | null;
  program_id: string | null;
  cloud_uri: string | null;
  mast_download_uri: string | null;
  reason: string;
  delivery_status: Record<string, unknown>;
  created_at: string;
  read_at: string | null;
  thumbnail_url: string | null;
  preview_url: string | null;
}

export interface AlertListQuery {
  watchlistId?: number;
  unread?: boolean;
  limit?: number;
  offset?: number;
}

export async function getAlerts(
  q: AlertListQuery = {},
): Promise<Result<Page<AlertRow>>> {
  const params = new URLSearchParams();
  if (q.watchlistId != null) params.set("watchlist_id", String(q.watchlistId));
  if (q.unread != null) params.set("unread", String(q.unread));
  params.set("limit", String(q.limit ?? 50));
  params.set("offset", String(q.offset ?? 0));

  try {
    const res = await fetch(`${API_BASE}/api/alerts?${params.toString()}`, {
      next: { revalidate: 10 },
    });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const data = (await res.json()) as Page<AlertRow>;
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}
