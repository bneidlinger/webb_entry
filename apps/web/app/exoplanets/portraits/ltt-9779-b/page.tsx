import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { ExoplanetNav } from "@/components/exoplanet-nav";
import { PortraitEvidence } from "@/components/portrait-evidence";
import { PortraitExamples } from "@/components/portrait-examples";
import { secondPortrait as portrait, secondPortraitEvidence } from "@/lib/portrait-gallery";

export const metadata: Metadata = {
  title: "LTT 9779 b · Portrait 002 — WebbWatch AI",
  description: "An evidence-informed illustration of LTT 9779 b, with CHEOPS, JWST, Hubble and ESPRESSO sources, uncertainties and the complete generation history.",
};
const action = "inline-flex min-h-11 items-center justify-center rounded-lg border border-webb-star/20 px-4 py-2 text-sm text-webb-star/85 hover:border-webb-accent/60 hover:bg-webb-accent/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent";

export default function SecondPortraitPage() {
  return <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12">
    <ExoplanetNav active="portrait" />
    <header className="mb-8 mt-10">
      <p className="text-xs font-medium uppercase tracking-[0.18em] text-webb-accent">Exoplanet Portrait Atlas / Portrait 002</p>
      <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">LTT 9779 b</h1>
      <p className="mt-4 max-w-2xl leading-relaxed text-webb-star/70">A bright cloud world, interpreted from reflected light. Our second example brings together TESS discovery data, CHEOPS eclipses, JWST phase curves and independent follow-up.</p>
    </header>
    <PortraitExamples active="ltt-9779-b" />
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(340px,1fr)] lg:gap-10">
      <div className="min-w-0 lg:sticky lg:top-6">
        <figure className="overflow-hidden rounded-2xl border border-webb-star/15 bg-black">
          <div className="flex flex-wrap justify-between gap-2 border-b border-webb-star/10 bg-webb-ink px-5 py-3 text-xs"><span className="text-webb-accent">Evidence-informed illustration</span><span className="text-webb-star/50">Generated with built-in imagegen</span></div>
          <a href={portrait.image} target="_blank" rel="noreferrer noopener" aria-label="Open the LTT 9779 b illustration at full resolution (opens in a new tab)"><Image src={portrait.image} alt="Hypothetical pearl-white LTT 9779 b globe with fine illustrative cloud texture, lit from the upper left against black. The poster labels its 384,400 km distance, narrower 15-degree framing and hypothetical status." width={portrait.width} height={portrait.height} sizes="(min-width: 1024px) 710px, 100vw" unoptimized priority className="h-auto w-full" /></a>
          <figcaption className="border-t border-webb-star/10 bg-webb-ink px-5 py-4 text-sm leading-relaxed text-webb-star/65">Reflective clouds are supported by atmospheric interpretations. The exact shade, fine texture and cloud geography are illustrative. Printed camera settings are requested values; the generated geometry and photometry have not been validated.</figcaption>
        </figure>
        <div className="mt-4 flex flex-wrap gap-3"><a href={portrait.image} download="ltt-9779-b-portrait.png" className={action}>Download image ↓</a><a href={portrait.prompt} className={action}>Read image prompt ↗</a><a href={portrait.refinement} className={action}>Read framing refinement ↗</a></div>
        <section aria-labelledby="selection-heading" className="mt-7 rounded-2xl border border-webb-accent/20 bg-webb-accent/5 p-5">
          <h2 id="selection-heading" className="font-medium">Why this planet next?</h2>
          <p className="mt-3 text-sm leading-relaxed text-webb-star/65">{portrait.selection.reason}</p>
          <Link href={`/exoplanets/catalog/${portrait.catalogId}`} className="mt-4 inline-flex min-h-10 items-center text-sm text-webb-accent underline underline-offset-4">Inspect its score, parameters and current prompt →</Link>
        </section>
        <section aria-labelledby="provenance-heading" className="mt-6 rounded-2xl border border-webb-star/10 bg-webb-ink/50 p-5">
          <h2 id="provenance-heading" className="text-sm font-medium">Sources and generation history</h2>
          <p className="mt-3 text-sm leading-relaxed text-webb-star/65">Literature checked {portrait.reviewDate}. The radius and other bulk values retain the October 19, 2026 UTC catalog snapshot. Published results were reviewed, not independently reprocessed. The September 2026 study is a preprint in review.</p>
          <p className="mt-3 text-sm leading-relaxed text-webb-star/65">Created with the built-in imagegen tool, then refined once to reduce the disk size. The tool did not expose a model identifier. Both prompts, the first render and file hashes are retained with the evidence.</p>
          <div className="mt-4 flex flex-col items-start gap-3 text-xs text-webb-accent"><a href={portrait.evidence} className="underline underline-offset-4">Evidence, uncertainty & generation history JSON</a>{portrait.supportingData.map((source) => <a key={source.url} href={source.url} target="_blank" rel="noreferrer noopener" className="underline underline-offset-4">{source.label} ↗</a>)}</div>
          <p className="mt-3 text-xs leading-relaxed text-webb-star/45">Different instruments, wavelength bands and models produce different albedo estimates. They are retained separately, not averaged or converted into an exact RGB color.</p>
        </section>
      </div>
      <PortraitEvidence groups={secondPortraitEvidence} />
    </div>
  </main>;
}
