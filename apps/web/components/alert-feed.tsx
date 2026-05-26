import Link from "next/link";

import { getAlerts, type AlertRow } from "@/lib/api";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().slice(0, 16).replace("T", " ");
  } catch {
    return iso;
  }
}

function AlertThumb({
  thumbnail,
  full,
  alt,
}: {
  thumbnail: string | null;
  full: string | null;
  alt: string;
}) {
  if (!thumbnail && !full) {
    return (
      <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded border border-dashed border-webb-star/15 text-[9px] text-webb-star/30">
        no preview
      </div>
    );
  }
  const src = thumbnail ?? full ?? "";
  const cls = "h-14 w-14 shrink-0 rounded border border-webb-star/10 bg-black object-cover";
  // eslint-disable-next-line @next/next/no-img-element
  const img = <img src={src} alt={alt} className={cls} loading="lazy" />;
  if (full) {
    return (
      <a href={full} target="_blank" rel="noreferrer" title="Open full preview">
        {img}
      </a>
    );
  }
  return img;
}

function StatusBadge({ status }: { status: AlertRow["delivery_status"] }) {
  const discord = (status?.discord as { status?: string } | undefined)?.status;
  if (!discord) {
    return (
      <span className="inline-block rounded border border-webb-star/20 bg-webb-star/5 px-2 py-0.5 text-[10px] uppercase tracking-wider text-webb-star/60">
        pending
      </span>
    );
  }
  const tones: Record<string, string> = {
    sent: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
    skipped: "bg-webb-star/10 text-webb-star/60 border-webb-star/20",
    error: "bg-red-500/15 text-red-200 border-red-500/30",
  };
  const tone = tones[discord] ?? "bg-webb-star/10 text-webb-star/60 border-webb-star/20";
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${tone}`}>
      discord:{discord}
    </span>
  );
}

function EmptyState() {
  return (
    <div className="mt-6 rounded-lg border border-dashed border-webb-star/20 bg-webb-ink/40 p-6 text-sm text-webb-star/60">
      <p className="font-medium text-webb-star/80">No alerts yet.</p>
      <p className="mt-2">
        Create a watchlist with criteria you care about, then run an ingest. Alerts fire when newly
        public products match.
      </p>
      <pre className="mt-3 overflow-x-auto rounded bg-webb-deep p-3 text-xs text-webb-accent">
{`curl -X POST http://localhost:8000/api/watchlists \\
  -H "content-type: application/json" \\
  -d '{"name":"NIRCam imaging","criteria":{"instruments":["NIRCAM"],"product_types":["i2d"]}}'`}
      </pre>
    </div>
  );
}

export async function AlertFeed() {
  const result = await getAlerts({ limit: 50 });

  if (!result.ok) {
    return (
      <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-200">
        Couldn&apos;t reach the API ({result.error}).
      </div>
    );
  }

  if (result.data.items.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="mt-6 overflow-hidden rounded-lg border border-webb-star/10 bg-webb-ink/40">
      <div className="flex items-baseline justify-between border-b border-webb-star/10 px-4 py-3">
        <span className="text-sm text-webb-star/70">
          Showing <span className="text-webb-star">{result.data.items.length}</span> of{" "}
          <span className="text-webb-star">{result.data.total}</span> alerts
        </span>
      </div>
      <ul className="divide-y divide-webb-star/5">
        {result.data.items.map((a: AlertRow) => (
          <li key={a.id} className="px-4 py-3 hover:bg-webb-deep/40">
            <div className="flex items-start justify-between gap-4">
              <div className="flex min-w-0 items-start gap-3">
                <AlertThumb
                  thumbnail={a.thumbnail_url}
                  full={a.preview_url}
                  alt={a.filename}
                />
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium text-webb-star">{a.watchlist_name}</span>
                    <span className="text-xs text-webb-star/40">→</span>
                    <Link
                      href={`/products/${a.data_product_id}`}
                      className="truncate font-mono text-xs text-webb-star/70 hover:text-webb-accent"
                    >
                      {a.filename}
                    </Link>
                  </div>
                  <div className="mt-1 text-xs text-webb-star/60">
                    <span className="text-webb-star/80">{a.target_name ?? "?"}</span>
                    <span className="text-webb-star/30"> · </span>
                    {a.instrument ?? "?"}
                    <span className="text-webb-star/30"> · </span>
                    program {a.program_id ?? "?"}
                    <span className="text-webb-star/30"> · </span>
                    type {a.product_type ?? "?"}
                  </div>
                  <div className="mt-1 text-xs text-webb-accent">matched: {a.reason}</div>
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <StatusBadge status={a.delivery_status} />
                <span className="text-xs text-webb-star/40">{formatDate(a.created_at)}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
