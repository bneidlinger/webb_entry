import type { EvidenceGroup } from "@/lib/portraits";
import evidence from "@/public/portraits/ltt-9779-b/evidence.json";

const assets = "/portraits/ltt-9779-b";
export const secondPortrait = {
  name: evidence.brief.planet,
  image: `${assets}/original.png`,
  prompt: `${assets}/prompt.txt`,
  refinement: `${assets}/refinement-prompt.txt`,
  evidence: `${assets}/evidence.json`,
  width: evidence.image_provenance.width,
  height: evidence.image_provenance.height,
  selection: evidence.brief.appearance_evidence.selection,
  geometry: evidence.brief.geometry,
  reviewDate: evidence.brief.appearance_evidence.source_checked_on,
  supportingData: evidence.brief.appearance_evidence.supporting_data,
  provenance: evidence.image_provenance,
  catalogId: evidence.ranking.id,
};

export const portraitExamples = [
  { slug: "hd-189733-b", name: "HD 189733 b", href: "/exoplanets", image: "/portraits/hd-189733-b/original.png", number: "001", description: "A blue world · Hubble reflectance" },
  { slug: "ltt-9779-b", name: "LTT 9779 b", href: "/exoplanets/portraits/ltt-9779-b", image: secondPortrait.image, number: "002", description: "Reflective clouds · CHEOPS + JWST" },
] as const;

export function portraitForPlanet(name: string) {
  return portraitExamples.find((portrait) => portrait.name === name);
}

export const secondPortraitEvidence: EvidenceGroup[] = [
  { id: "measured", title: "Measured", description: "Published observations and fitted constraints, with detections kept separate from limits.", claims: [] },
  { id: "inferred", title: "Inferred", description: "Atmospheric interpretations from models. Cloud composition and exact color remain uncertain.", claims: [] },
  { id: "illustrative", title: "Illustrative", description: "Texture, display color and framing choices made for this portrait.", claims: [] },
];

for (const claim of evidence.brief.appearance_evidence.claims) {
  if (claim.kind === "rendering_assumption") continue;
  const group = secondPortraitEvidence[claim.kind === "reported_constraint" ? 0 : 1];
  group.claims.push({
    title: claim.title,
    value: "value" in claim ? claim.value : undefined,
    explanation: claim.text,
    sources: "source_url" in claim && claim.source_url ? [{ href: claim.source_url, label: claim.source_label ?? "Supporting paper" }] : [],
  });
}
const radius = evidence.brief.parameters.find((entry) => entry.field === "pl_rade")!;
secondPortraitEvidence[0].claims.push({
  title: "Size used for the viewpoint",
  value: `${radius.value} ± ${radius.uncertainty_plus} Earth radii`,
  explanation: "The pinned NASA catalog radius, fitted from observations and stellar parameters. At 384,400 km from center it gives an angular diameter of about 8.97°. This calculation does not validate the generated disk geometry.",
  sources: [{ label: radius.reference, href: radius.source_urls[0] }, { label: "Saved parameters & uncertainties", href: secondPortrait.evidence }],
});
secondPortraitEvidence[2].claims.push(
  { title: "Color and cloud texture", explanation: "Pearl-white and pale-gray clouds depict a highly reflective atmosphere. Exact RGB, fine cloud shapes, haze and the screen placement of the brighter region are artistic choices. The image is not a recovered longitude or weather map.", sources: [{ label: "Initial generation prompt", href: secondPortrait.prompt }] },
  { title: "A closer framing at the same distance", value: "384,400 km from center · 15° field of view", explanation: "The virtual viewpoint keeps the atlas distance and 60° phase angle. Its labeled 15° field of view is narrower than the 45° default, making this smaller planet easier to see. One image edit reduced the oversized first-render disk; scale, illumination and photometry remain unvalidated.", sources: [{ label: "Framing refinement prompt", href: secondPortrait.refinement }, { label: "Generation history & image hashes", href: secondPortrait.evidence }] },
);
