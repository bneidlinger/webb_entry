import type { EvidenceGroup } from "@/lib/portraits";

export type SpectrumKind = "transmission" | "eclipse" | "direct_imaging";
export type SpectrumFilter = "all" | "any" | SpectrumKind;
export interface CatalogQuery {
  q: string;
  spectrum: SpectrumFilter;
  facility: string;
  min_score: number;
  offset: number;
}
export interface RankedPlanet {
  id: string;
  planet: string;
  host: string | null;
  discovery_facility: string | null;
  score: number;
  rank: number;
  tied_count: number;
  tier: string;
  components: Record<string, number>;
  spectra_counts: Record<SpectrumKind, number | null>;
  jwst_approved_observation_counts: Record<string, number | null>;
  has_curated_appearance: boolean;
}
export interface CatalogSnapshot {
  retrieved_at_utc: string | null;
  catalog_sha256: string;
  coverage: string;
  source: string;
  score_version: string;
  record_count: number;
  with_spectra: number;
  top_score: number;
  top_tied_count: number;
  limitation: string;
  facilities: string[];
}
export interface CatalogPage {
  items: RankedPlanet[];
  total: number;
  limit: number;
  offset: number;
  snapshot: CatalogSnapshot;
}
export interface CatalogParameter {
  field: string;
  label: string;
  value: number | null;
  unit: string;
  uncertainty_plus: number | null;
  uncertainty_minus: number | null;
  limit_flag: number | null;
  reference: string;
  source_urls: string[];
  basis: string;
  points: number;
  max_points: number;
}
export interface PortraitBrief {
  planet: string;
  prompt: string;
  prompt_version: string;
  status: string;
  catalog_sha256: string;
  archive_url: string;
  parameters: CatalogParameter[];
  assumptions: string[];
  unknowns: string[];
  appearance_evidence: {
    scope: string;
    claims: { kind: string; text: string; title?: string; value?: string; source_url?: string; source_label?: string }[];
  } | null;
  geometry: { angular_diameter_degrees: number | null; distance_from_center_km: number };
}
export interface PlanetDetail {
  ranking: RankedPlanet;
  brief: PortraitBrief;
  snapshot: CatalogSnapshot;
}

const API_BASE = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
export const spectrumLabels: Record<SpectrumKind, string> = {
  transmission: "Transmission", eclipse: "Eclipse", direct_imaging: "Direct imaging",
};
export const scoreComponents = [
  { key: "bulk_parameters", label: "Reported parameters", max: 40 },
  { key: "published_spectral_data", label: "At least one spectrum type", max: 40 },
  { key: "complementary_spectrum_types", label: "Two or more spectrum types", max: 10 },
  { key: "thermal_spectrum_available", label: "Eclipse or direct-imaging spectrum", max: 10 },
];
export const basisLabels: Record<string, string> = {
  reported_with_uncertainty: "Reported with two-sided uncertainty",
  reported_without_two_sided_uncertainty: "Reported; two-sided uncertainty incomplete",
  archive_calculated: "Calculated by the archive; no measurement credit",
  minimum_or_model_mass: "Minimum or model mass; not an independent true-mass measurement",
  limit_only: "Reported bound; no measurement credit",
  unverified_reference: "Reference unavailable; no measurement credit",
  missing_or_invalid: "Missing or invalid; no measurement credit",
};

export function snapshotDate(snapshot: CatalogSnapshot) {
  return snapshot.retrieved_at_utc
    ? new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(snapshot.retrieved_at_utc)) + " UTC"
    : "Retrieval date not recorded";
}

export function catalogHref(query: Partial<CatalogQuery> = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== "" && value !== "all" && value !== 0) params.set(key, String(value));
  }
  return `/exoplanets/catalog${params.size ? `?${params}` : ""}`;
}

type Result<T> = { ok: true; data: T } | { ok: false; status: number };
async function readCatalog<T>(path: string): Promise<Result<T>> {
  try {
    const res = await fetch(`${API_BASE}/api/exoplanets${path}`, {
      next: { revalidate: 60 }, signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) return { ok: false, status: res.status };
    return { ok: true, data: await res.json() as T };
  } catch {
    return { ok: false, status: 503 };
  }
}
export function getCatalog(query: CatalogQuery) {
  return readCatalog<CatalogPage>(`?${new URLSearchParams(Object.entries(query).map(([k, v]) => [k, String(v)]))}`);
}
export function getPlanet(id: string) {
  return readCatalog<PlanetDetail>(`/${encodeURIComponent(id)}`);
}

function formatNumber(value: number) {
  return value.toLocaleString("en-US", { maximumSignificantDigits: 7 });
}
export function parameterValue(parameter: CatalogParameter) {
  if (parameter.value === null || parameter.basis === "missing_or_invalid") return "Unavailable";
  const limit = parameter.limit_flag === 1 ? "< " : parameter.limit_flag === -1 ? "> " : "";
  const plus = parameter.uncertainty_plus;
  const minus = parameter.uncertainty_minus;
  const errors = plus !== null && minus !== null && plus > 0 && minus < 0
    ? ` (+${formatNumber(plus)} / −${formatNumber(Math.abs(minus))})` : "";
  return `${limit}${formatNumber(parameter.value)}${errors} ${parameter.unit}`;
}

export function promptEvidence(detail: PlanetDetail): EvidenceGroup[] {
  const { brief } = detail;
  const groups: EvidenceGroup[] = [
    { id: "measured", title: "Measured", description: "Published constraints and parameters fitted from observations.", claims: [] },
    { id: "inferred", title: "Inferred", description: "Model estimates and physical interpretations; their assumptions still matter.", claims: [] },
    { id: "illustrative", title: "Illustrative", description: "Chosen camera geometry and visual assumptions, not observed details.", claims: [] },
  ];
  for (const p of brief.parameters) {
    if (p.basis === "missing_or_invalid") continue;
    const measured = p.field !== "pl_eqt" && (p.basis.startsWith("reported_") || p.basis === "limit_only");
    groups[measured ? 0 : 1].claims.push({
      title: p.label, value: parameterValue(p),
      explanation: `${basisLabels[p.basis] ?? p.basis}.${p.field === "pl_eqt" ? " An energy-balance estimate, not a measured surface temperature." : ""}`,
      sources: p.source_urls.map((href) => ({ href, label: p.reference || "Catalog reference" })),
    });
  }
  for (const claim of brief.appearance_evidence?.claims ?? []) {
    const index = claim.kind === "reported_constraint" ? 0 : claim.kind === "model_inference" ? 1 : 2;
    groups[index].claims.push({
      title: claim.title ?? (index === 0 ? "Appearance constraint" : index === 1 ? "Appearance interpretation" : "Texture scenario"),
      value: claim.value,
      explanation: claim.text,
      sources: claim.source_url ? [{ href: claim.source_url, label: claim.source_label ?? "Supporting publication" }] : [],
    });
  }
  if (!groups[0].claims.length) groups[0].claims.push({ title: "No credited constraints", explanation: "This snapshot has no usable published constraints for these parameters. Missing data is not filled in.", sources: [] });
  if (!brief.appearance_evidence) groups[1].claims.push({ title: "Appearance has not been assessed", explanation: "Listed spectra have not been reviewed for visible color, atmosphere detections or spatial detail. The prompt defaults to neutral gray until sourced appearance evidence is added.", sources: [] });
  groups[2].claims.push({ title: "Virtual viewpoint", explanation: brief.assumptions.join(" "), sources: [] });
  groups[2].claims.push({ title: "Scale and detail", explanation: brief.geometry.angular_diameter_degrees === null
    ? "A suitable radius is unavailable. This prompt must not be used for a physically scaled portrait."
    : `The catalog radius gives a ${brief.geometry.angular_diameter_degrees.toFixed(2)}° angular diameter. This is a requested scale; any generated image needs a separate geometry check. Cloud shapes and surface geography remain unknown.`, sources: [] });
  return groups;
}
