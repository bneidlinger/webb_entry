import "server-only";

import { latestPortraitQuery, type PortraitPreview } from "@/lib/portrait-previews";

const API_BASE = (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function getPortraitPreviews(planetIds: string[]) {
  if (!planetIds.length) return { items: [] as PortraitPreview[], unavailable: false };
  try {
    const response = await fetch(`${API_BASE}/api/planet-portraits${latestPortraitQuery(planetIds)}`, {
      cache: "no-store", signal: AbortSignal.timeout(4_000),
    });
    if (!response.ok) throw new Error("Portrait previews unavailable");
    const data = await response.json() as { items: PortraitPreview[] };
    return { items: data.items, unavailable: false };
  } catch {
    // The frozen catalog must remain usable without the portrait database.
    return { items: [] as PortraitPreview[], unavailable: true };
  }
}
