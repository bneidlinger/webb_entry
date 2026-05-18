import { HealthBadge } from "@/components/health-badge";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-16">
      <header className="mb-12 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-4xl font-semibold tracking-tight text-webb-star">
            WebbWatch <span className="text-webb-accent">AI</span>
          </h1>
          <p className="mt-3 max-w-2xl text-webb-star/70">
            Live discovery and analysis for newly public James Webb Space Telescope data
            products. Deterministic tools first. AI commentary second. Sources cited.
          </p>
        </div>
        <HealthBadge />
      </header>

      <section className="rounded-xl border border-webb-star/10 bg-webb-ink/60 p-8">
        <h2 className="text-lg font-medium text-webb-star/90">Latest JWST products</h2>
        <p className="mt-2 text-sm text-webb-star/60">
          The ingestion pipeline is not online yet. Phase 1 will populate this feed from MAST.
        </p>
        <ul className="mt-6 grid gap-3 text-sm text-webb-star/60">
          <li>— Phase 0: project scaffold (you are here)</li>
          <li>— Phase 1: MAST metadata discovery</li>
          <li>— Phase 2: new-data detection &amp; alerts</li>
          <li>— Phase 3: FITS download + preview generation</li>
        </ul>
      </section>
    </main>
  );
}
