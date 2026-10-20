import Image from "next/image";
import Link from "next/link";

import { HealthBadge } from "@/components/health-badge";
import { ProductFeed } from "@/components/product-feed";
import { firstPortrait } from "@/lib/portraits";
import { secondPortrait } from "@/lib/portrait-gallery";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-16">
      <header className="mb-10 flex flex-wrap items-start justify-between gap-6">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight text-webb-star">
            WebbWatch <span className="text-webb-accent">AI</span>
          </h1>
          <p className="mt-3 max-w-2xl text-webb-star/70">
            Live discovery and analysis for newly public James Webb Space Telescope data
            products. Deterministic tools first. AI commentary second. Sources cited.
          </p>
          <nav aria-label="Explore WebbWatch" className="mt-4 flex flex-wrap gap-3">
            <Link
              href="/alerts"
              className="inline-flex min-h-10 items-center gap-2 rounded-full border border-webb-star/20 bg-webb-ink/60 px-3 py-1 text-xs text-webb-star/80 hover:border-webb-accent/40 hover:text-webb-star"
            >
              <span className="size-1.5 rounded-full bg-webb-accent" />
              Watchlist alerts →
            </Link>
            <Link href="/exoplanets" className="inline-flex min-h-10 items-center gap-2 rounded-full border border-webb-accent/30 bg-webb-accent/10 px-3 py-1 text-xs text-webb-accent hover:border-webb-accent/60">
              Portrait Atlas →
            </Link>
            <Link href="/exoplanets/catalog" className="inline-flex min-h-10 items-center gap-2 rounded-full border border-webb-accent/30 bg-webb-accent/10 px-3 py-1 text-xs text-webb-accent hover:border-webb-accent/60">Ranked exoplanet catalog →</Link>
          </nav>
        </div>
        <HealthBadge />
      </header>

      <Link href="/exoplanets" className="mb-10 flex flex-col gap-5 rounded-2xl border border-webb-accent/20 bg-webb-ink p-5 transition hover:border-webb-accent/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent sm:flex-row sm:items-center">
        <Image src={firstPortrait.image} alt="Blue HD 189733 b illustration, the first Portrait Atlas example" width={112} height={112} unoptimized className="size-28 shrink-0 rounded-lg border border-webb-star/10 bg-black" />
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-webb-accent">New · Exoplanet Portrait Atlas</p>
          <h2 className="mt-2 text-xl font-semibold">HD 189733 b, with the evidence in view</h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-webb-star/65">Explore the first portrait and follow its Measured, Inferred and Illustrative features back to their sources.</p>
        </div>
        <span aria-hidden="true" className="ml-auto text-2xl text-webb-accent">↗</span>
      </Link>

      <Link href="/exoplanets/portraits/ltt-9779-b" className="mb-10 flex flex-col gap-5 rounded-2xl border border-webb-accent/20 bg-webb-ink p-5 transition hover:border-webb-accent/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent sm:flex-row sm:items-center">
        <Image src={secondPortrait.image} alt="Hypothetical bright, cloudy LTT 9779 b, the second Portrait Atlas example" width={112} height={112} unoptimized className="size-28 shrink-0 rounded-lg border border-webb-star/10 bg-black" />
        <div><p className="text-xs font-medium uppercase tracking-wider text-webb-accent">New · Portrait 002</p><h2 className="mt-2 text-xl font-semibold">LTT 9779 b: a world of reflective clouds</h2><p className="mt-2 max-w-2xl text-sm leading-relaxed text-webb-star/65">See the generated second portrait and follow CHEOPS, JWST, Hubble and ESPRESSO evidence, with measured limits and model assumptions kept in view.</p></div>
        <span aria-hidden="true" className="ml-auto text-2xl text-webb-accent">↗</span>
      </Link>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-medium text-webb-star/90">Latest JWST products</h2>
          <span className="text-xs text-webb-star/40">
            metadata via MAST · cache refreshes every 10s
          </span>
        </div>
        <ProductFeed />
      </section>
    </main>
  );
}
