import brief from "@/public/portraits/hd-189733-b/evidence.json";

export interface EvidenceLink {
  label: string;
  href: string;
}

export interface EvidenceClaim {
  title: string;
  value?: string;
  explanation: string;
  sources: EvidenceLink[];
}

export interface EvidenceGroup {
  id: "measured" | "inferred" | "illustrative";
  title: string;
  description: string;
  claims: EvidenceClaim[];
}

const assets = "/portraits/hd-189733-b";
const paper: EvidenceLink = {
  label: "Evans et al. 2013 · Hubble/STIS",
  href: "https://arxiv.org/abs/1307.3239",
};
const snapshot: EvidenceLink = { label: "Saved evidence & uncertainties", href: `${assets}/evidence.json` };
const rendering: EvidenceLink = { label: "Read the rendering prompt", href: `${assets}/prompt.txt` };

function parameter(field: string) {
  const value = brief.parameters.find((entry) => entry.field === field);
  if (!value) throw new Error(`Missing portrait parameter: ${field}`);
  return value;
}

function parameterSource(field: string): EvidenceLink {
  const entry = parameter(field);
  if (!entry.source_urls[0]) throw new Error(`Missing source for portrait parameter: ${field}`);
  return { label: `${entry.reference} · catalog reference`, href: entry.source_urls[0] };
}

const radius = parameter("pl_rade");
const period = parameter("pl_orbper");
const temperature = parameter("pl_eqt");

export const firstPortrait = {
  name: brief.planet,
  image: `${assets}/original.png`,
  imageWidth: 1254,
  imageHeight: 1254,
  prompt: `${assets}/prompt.txt`,
  evidence: `${assets}/evidence.json`,
  snapshotDate: "October 18, 2026",
  geometry: brief.geometry,
  provenance: brief.image_provenance,
};

export const portraitEvidence: EvidenceGroup[] = [
  {
    id: "measured",
    title: "Measured",
    description: "Published observations and parameters fitted from data.",
    claims: [
      {
        title: "Reflected light",
        value: "0.40 ± 0.12 · 290–450 nm",
        explanation: "Hubble measured geometric albedo, a measure of reflectivity. At 450–570 nm, the reported 1σ upper limit is 0.12. These broad bands constrain brightness, not exact RGB color.",
        sources: [paper],
      },
      {
        title: "Planet size",
        value: `${radius.value.toFixed(2)} ± ${radius.uncertainty_plus.toFixed(2)} Earth radii`,
        explanation: "A published estimate derived from observations and stellar parameters. This sets the size used in the portrait brief; it does not resolve the planet’s surface.",
        sources: [parameterSource("pl_rade"), snapshot],
      },
      {
        title: "Orbital period",
        value: `${period.value.toFixed(4)} days`,
        explanation: "The catalog’s published orbital period. The saved evidence includes the full precision and uncertainty.",
        sources: [parameterSource("pl_orbper")],
      },
    ],
  },
  {
    id: "inferred",
    title: "Inferred",
    description: "Physical interpretations supported by those observations.",
    claims: [
      {
        title: "Why blue?",
        explanation: "The best-fit reflectance suggests a deep-blue visible appearance. The precise shade in this image is a rendering choice.",
        sources: [paper],
      },
      {
        title: "Reflective clouds",
        explanation: "Dayside clouds with absorption at longer wavelengths are one interpretation of the reflectance. Their shapes and locations are unresolved.",
        sources: [paper],
      },
      {
        title: "Equilibrium temperature",
        value: `${temperature.value.toLocaleString("en-US")} ± ${temperature.uncertainty_plus} K`,
        explanation: "A published energy-balance estimate with model assumptions, not a measured surface temperature or a map of the weather.",
        sources: [parameterSource("pl_eqt"), snapshot],
      },
    ],
  },
  {
    id: "illustrative",
    title: "Illustrative",
    description: "Visual choices documented in the rendering brief.",
    claims: [
      {
        title: "Cloud texture & limb haze",
        explanation: "The mottling, soft atmospheric edge and exact colors were generated for this illustration. They are not observed cloud patterns or verified storms.",
        sources: [rendering],
      },
      {
        title: "A virtual camera",
        value: "384,400 km from the planet’s center",
        explanation: "The prompt requests a 60° phase angle and 45° horizontal field of view. This is a chosen viewpoint; it does not imply a moon or stable orbit.",
        sources: [rendering, { label: "View original image", href: `${assets}/original.png` }],
      },
      {
        title: "Geometry is requested, not verified",
        explanation: `The brief calculates a ${brief.geometry.angular_diameter_degrees.toFixed(2)}° angular diameter. The generated image has not been checked against that scale or illumination geometry.`,
        sources: [snapshot],
      },
    ],
  },
];
