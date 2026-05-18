import { HealthBadge } from "@/components/health-badge";
import { ProductFeed } from "@/components/product-feed";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-16">
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
