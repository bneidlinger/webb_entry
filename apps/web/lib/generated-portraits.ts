import type { PlanetDetail } from "@/lib/exoplanets";
import type { EvidenceGroup } from "@/lib/portraits";

export const portraitApiBase = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const portraitAsset = (path: string) => `${portraitApiBase}${path}`;

export interface SavedPortrait {
  id: string;
  planet_id: string;
  planet_name: string;
  status: "queued" | "generating" | "completed" | "failed" | "interrupted";
  created_at: string;
  model: string;
  settings: { size: string; quality: string };
  error: string | null;
  image_url: string | null;
  prompt_url: string;
  evidence_url: string;
  prompt_sha256: string;
  prompt?: string;
  evidence?: { schema_version: string; catalog_detail: PlanetDetail; groups: EvidenceGroup[] };
  output: { image_sha256: string; revised_prompt: string | null; completed_at: string } | null;
}
export interface GenerationConfig {
  ready: boolean;
  reason: string | null;
  provider: string;
  model: string;
  settings: { size: string; quality: string };
  billing_note: string;
  pricing_url: string;
}
export const isGenerating = (row: SavedPortrait) => ["queued", "generating"].includes(row.status);
export const generationDate = (date: string) => new Date(date).toLocaleString();

export async function portraitRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${portraitApiBase}/api/planet-portraits${path}`, {
    ...init, cache: "no-store", signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail === "string" ? error.detail : "Portrait service is unavailable. Try again.");
  }
  return response.json() as Promise<T>;
}

export async function promptHash(prompt: string) {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(prompt));
  return Array.from(new Uint8Array(bytes), (value) => value.toString(16).padStart(2, "0")).join("");
}
