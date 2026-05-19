import Link from "next/link";

import { AlertFeed } from "@/components/alert-feed";
import { HealthBadge } from "@/components/health-badge";

export const metadata = {
  title: "Alerts — WebbWatch AI",
};

export default function AlertsPage() {
  return (
    <main className="mx-auto max-w-7xl px-6 py-16">
      <header className="mb-12 flex items-start justify-between gap-6">
        <div>
          <Link
            href="/"
            className="text-xs uppercase tracking-wider text-webb-star/50 hover:text-webb-star"
          >
            ← WebbWatch AI
          </Link>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight text-webb-star">
            Alerts
          </h1>
          <p className="mt-3 max-w-2xl text-webb-star/70">
            New JWST products matching your watchlists. Polled every 30 min; Discord webhook fires
            on each match when configured. Subscribe via RSS at{" "}
            <code className="rounded bg-webb-deep px-1.5 py-0.5 text-xs">/api/feed.rss</code>.
          </p>
        </div>
        <HealthBadge />
      </header>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-medium text-webb-star/90">Recent matches</h2>
          <span className="text-xs text-webb-star/40">cache refreshes every 10s</span>
        </div>
        <AlertFeed />
      </section>
    </main>
  );
}
