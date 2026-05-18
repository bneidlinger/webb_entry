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
