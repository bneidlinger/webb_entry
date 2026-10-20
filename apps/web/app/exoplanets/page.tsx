import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { PortraitEvidence } from "@/components/portrait-evidence";
import { ExoplanetNav } from "@/components/exoplanet-nav";
import { PortraitExamples } from "@/components/portrait-examples";
import { firstPortrait as portrait, portraitEvidence } from "@/lib/portraits";

export const metadata: Metadata = {
  title: "HD 189733 b · Portrait Atlas — WebbWatch AI",
  description: "Explore an evidence-informed portrait of HD 189733 b, with measured, inferred and illustrative features linked to their sources.",
};

const actionClass = "inline-flex min-h-11 items-center justify-center rounded-lg border border-webb-star/20 px-4 py-2 text-sm text-webb-star/85 transition hover:border-webb-accent/60 hover:bg-webb-accent/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent";

export default function ExoplanetsPage() {
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12">
      <ExoplanetNav active="portrait" />

      <header className="mb-8 mt-10 sm:mb-10">
        <div className="flex flex-wrap items-center gap-3 text-xs font-medium uppercase tracking-[0.18em]">
          <span className="text-webb-accent">Exoplanet Portrait Atlas</span>
          <span aria-hidden="true" className="text-webb-star/25">/</span>
          <span className="text-webb-star/55">First portrait · 001</span>
        </div>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">{portrait.name}</h1>
        <p className="mt-4 max-w-2xl text-base leading-relaxed text-webb-star/70">
          A distant blue world, interpreted through the evidence. Explore the observations,
          the physical interpretations, and the choices that bring this portrait to life.
        </p>
        <Link href="/exoplanets/catalog" className={`${actionClass} mt-5`}>Choose the next planet from the ranked catalog →</Link>
      </header>

      <PortraitExamples active="hd-189733-b" />
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(340px,1fr)] lg:gap-10">
        <div className="min-w-0 lg:sticky lg:top-6">
          <figure className="overflow-hidden rounded-2xl border border-webb-star/15 bg-black">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-webb-star/10 bg-webb-ink px-5 py-3 text-xs">
              <span className="flex items-center gap-2 text-webb-accent"><span aria-hidden="true" className="size-1.5 rounded-full bg-webb-accent" />Evidence-informed illustration</span>
              <span className="text-webb-star/50">User-generated in ChatGPT</span>
            </div>
            <a href={portrait.image} target="_blank" rel="noreferrer noopener" aria-label="Open the original HD 189733 b illustration at full resolution (opens in a new tab)" className="block focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-webb-accent">
              <Image
                src={portrait.image}
                alt="Hypothetical blue globe of HD 189733 b, illuminated from the upper left, with soft cloud texture. The original poster labels its camera assumptions and states that detailed appearance is not observed."
                width={portrait.imageWidth}
                height={portrait.imageHeight}
                sizes="(min-width: 1024px) 710px, 100vw"
                unoptimized
                priority
                className="h-auto w-full"
              />
            </a>
            <figcaption className="border-t border-webb-star/10 bg-webb-ink px-5 py-4 text-sm leading-relaxed text-webb-star/65">
              The original image is preserved in full. Cloud patterns and detailed appearance
              are illustrative. Numbers printed on the image describe the prompt; its geometry
              has not been independently validated.
            </figcaption>
          </figure>

          <div className="mt-4 flex flex-wrap gap-3">
            <a href={portrait.image} download="hd-189733-b-original.png" className={actionClass}>Download original image ↓</a>
            <a href={portrait.prompt} className={actionClass}>Read the prompt ↗</a>
          </div>

          <section aria-labelledby="provenance-heading" className="mt-7 rounded-2xl border border-webb-star/10 bg-webb-ink/50 p-5">
            <h2 id="provenance-heading" className="text-sm font-medium">About this example</h2>
            <p className="mt-2 text-sm leading-relaxed text-webb-star/65">
              Created by the user in ChatGPT using the WebbWatch portrait prompt. The generation
              model was not recorded. Catalog values were saved on {portrait.snapshotDate};
              this is a curated example, not a live literature review.
            </p>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-3 text-xs text-webb-accent">
              <a href={portrait.evidence} className="underline decoration-webb-accent/30 underline-offset-4 hover:decoration-webb-accent">View evidence & provenance JSON</a>
              <a href="https://exoplanetarchive.ipac.caltech.edu/docs/pscp_about.html" target="_blank" rel="noreferrer noopener" className="underline decoration-webb-accent/30 underline-offset-4 hover:decoration-webb-accent">About the NASA catalog ↗<span className="sr-only"> (opens in a new tab)</span></a>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-webb-star/50">
              Composite catalog values may come from different studies. Each parameter retains its own reference.
            </p>
          </section>
        </div>

        <PortraitEvidence groups={portraitEvidence} />
      </div>

      <footer className="mt-12 border-t border-webb-star/10 pt-6 text-xs leading-relaxed text-webb-star/50">
        WebbWatch AI · Portrait Atlas · Observations, interpretations and illustration, with their sources attached.
      </footer>
    </main>
  );
}
