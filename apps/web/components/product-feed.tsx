import { getProducts, type ProductRow } from "@/lib/api";

function formatSize(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return iso;
  }
}

function PreviewThumb({
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
      <div className="flex h-12 w-12 items-center justify-center rounded border border-dashed border-webb-star/15 text-[9px] text-webb-star/30">
        —
      </div>
    );
  }
  const src = thumbnail ?? full ?? "";
  const cls = "h-12 w-12 rounded border border-webb-star/10 bg-black object-cover";
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

function ProductTypeBadge({ type }: { type: string | null }) {
  if (!type) return <span className="text-webb-star/40">—</span>;
  const tones: Record<string, string> = {
    i2d: "bg-sky-500/15 text-sky-200 border-sky-500/30",
    x1d: "bg-violet-500/15 text-violet-200 border-violet-500/30",
    c1d: "bg-violet-500/15 text-violet-200 border-violet-500/30",
    s2d: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
    s3d: "bg-emerald-500/15 text-emerald-200 border-emerald-500/30",
    cat: "bg-amber-500/15 text-amber-200 border-amber-500/30",
  };
  const tone = tones[type] ?? "bg-webb-star/10 text-webb-star/70 border-webb-star/20";
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${tone}`}>
      {type}
    </span>
  );
}

function EmptyState() {
  return (
    <div className="mt-6 rounded-lg border border-dashed border-webb-star/20 bg-webb-ink/40 p-6 text-sm text-webb-star/60">
      <p className="font-medium text-webb-star/80">No products ingested yet.</p>
      <p className="mt-2">
        Run the ingest CLI from <code className="rounded bg-webb-deep px-1.5 py-0.5 text-xs">services/api</code>:
      </p>
      <pre className="mt-3 overflow-x-auto rounded bg-webb-deep p-3 text-xs text-webb-accent">
        python -m app ingest mast --instrument NIRCAM --limit 50
      </pre>
    </div>
  );
}

export async function ProductFeed() {
  const result = await getProducts({ limit: 50 });

  if (!result.ok) {
    return (
      <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-200">
        Couldn&apos;t reach the API ({result.error}). Is the FastAPI server running on{" "}
        <code className="rounded bg-webb-deep px-1.5 py-0.5 text-xs">localhost:8000</code>?
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
          <span className="text-webb-star">{result.data.total}</span> products
        </span>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="bg-webb-deep/60 text-xs uppercase tracking-wider text-webb-star/50">
          <tr>
            <th className="px-4 py-2">Preview</th>
            <th className="px-4 py-2">Type</th>
            <th className="px-4 py-2">Target</th>
            <th className="px-4 py-2">Instrument</th>
            <th className="px-4 py-2">Filter / grating</th>
            <th className="px-4 py-2">Program</th>
            <th className="px-4 py-2">Observed</th>
            <th className="px-4 py-2">Size</th>
            <th className="px-4 py-2">Filename</th>
          </tr>
        </thead>
        <tbody>
          {result.data.items.map((p: ProductRow) => (
            <tr key={p.id} className="border-t border-webb-star/5 hover:bg-webb-deep/40">
              <td className="px-4 py-2">
                <PreviewThumb
                  thumbnail={p.thumbnail_url}
                  full={p.preview_url}
                  alt={p.filename}
                />
              </td>
              <td className="px-4 py-2"><ProductTypeBadge type={p.product_type} /></td>
              <td className="px-4 py-2 text-webb-star">{p.target_name ?? "—"}</td>
              <td className="px-4 py-2 text-webb-star/70">{p.instrument ?? "—"}</td>
              <td className="px-4 py-2 text-webb-star/70">{p.filters ?? "—"}</td>
              <td className="px-4 py-2 font-mono text-xs text-webb-star/60">{p.program_id ?? "—"}</td>
              <td className="px-4 py-2 text-webb-star/60">{formatDate(p.observation_date)}</td>
              <td className="px-4 py-2 text-webb-star/60">{formatSize(p.file_size)}</td>
              <td className="px-4 py-2 font-mono text-xs text-webb-star/40">{p.filename}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
