import Link from "next/link";
import { notFound } from "next/navigation";

import { HealthBadge } from "@/components/health-badge";
import { RegenerateAiButton } from "@/components/regenerate-ai-button";
import {
  getProduct,
  getProductAiReports,
  getProductAnalyses,
  type AiReportRead,
  type AnalysisRead,
} from "@/lib/api";

interface PageProps {
  params: Promise<{ id: string }>;
}

export const metadata = {
  title: "Product — WebbWatch AI",
};

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
    return new Date(iso).toISOString().slice(0, 16).replace("T", " ");
  } catch {
    return iso;
  }
}

function formatNumber(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value ?? "—");
  if (Number.isInteger(value)) return value.toLocaleString();
  if (Math.abs(value) >= 1000 || (value !== 0 && Math.abs(value) < 0.01)) {
    return value.toExponential(3);
  }
  return value.toFixed(4);
}

function StatRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-webb-star/5 py-1.5 last:border-b-0">
      <dt className="text-xs uppercase tracking-wider text-webb-star/50">{label}</dt>
      <dd className="font-mono text-sm text-webb-star/90">{value}</dd>
    </div>
  );
}

function ImageMeasurements({ m }: { m: Record<string, unknown> }) {
  const dims = Array.isArray(m.dimensions) ? (m.dimensions as number[]).join(" × ") : "—";
  return (
    <div className="grid gap-6 md:grid-cols-3">
      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
          Pixel statistics
        </h3>
        <dl>
          <StatRow label="Dimensions" value={dims} />
          <StatRow label="Total pixels" value={formatNumber(m.total_pixel_count)} />
          <StatRow label="Finite pixels" value={formatNumber(m.finite_pixel_count)} />
          <StatRow label="NaN pixels" value={formatNumber(m.nan_pixel_count)} />
          <StatRow label="Min" value={formatNumber(m.min)} />
          <StatRow label="Max" value={formatNumber(m.max)} />
          <StatRow label="Mean" value={formatNumber(m.mean)} />
          <StatRow label="Median" value={formatNumber(m.median)} />
          <StatRow label="Std dev" value={formatNumber(m.std)} />
        </dl>
      </section>
      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
          Background (σ-clipped, σ=3)
        </h3>
        <dl>
          <StatRow label="Mean" value={formatNumber(m.background_mean)} />
          <StatRow label="Median" value={formatNumber(m.background_median)} />
          <StatRow label="Std dev" value={formatNumber(m.background_std)} />
        </dl>
      </section>
      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
          Source detection
        </h3>
        <dl>
          <StatRow label="Sources (bg+3σ)" value={formatNumber(m.source_count)} />
          <StatRow label="Near-saturated pixels" value={formatNumber(m.saturated_pixel_count)} />
        </dl>
        <p className="mt-3 text-xs text-webb-star/40">
          Source count is a coarse connected-components estimate, not photometry.
        </p>
      </section>
    </div>
  );
}

function SpectrumMeasurements({ m }: { m: Record<string, unknown> }) {
  return (
    <div className="grid gap-6 md:grid-cols-3">
      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
          Wavelength
        </h3>
        <dl>
          <StatRow label="Samples" value={formatNumber(m.sample_count)} />
          <StatRow label="Min" value={`${formatNumber(m.wavelength_min)} ${m.wavelength_unit ?? ""}`} />
          <StatRow label="Max" value={`${formatNumber(m.wavelength_max)} ${m.wavelength_unit ?? ""}`} />
        </dl>
      </section>
      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
          Flux ({String(m.flux_unit ?? "—")})
        </h3>
        <dl>
          <StatRow label="Min" value={formatNumber(m.flux_min)} />
          <StatRow label="Max" value={formatNumber(m.flux_max)} />
          <StatRow label="Mean" value={formatNumber(m.flux_mean)} />
          <StatRow label="Median" value={formatNumber(m.flux_median)} />
        </dl>
      </section>
      <section>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
          Features
        </h3>
        <dl>
          <StatRow label="Peaks" value={formatNumber(m.peak_count)} />
          <StatRow label="Troughs" value={formatNumber(m.trough_count)} />
          <StatRow label="S/N proxy" value={formatNumber(m.snr_proxy)} />
        </dl>
        <p className="mt-3 text-xs text-webb-star/40">
          Peaks detected via scipy.signal.find_peaks with prominence ≥ 3 × MAD.
        </p>
      </section>
    </div>
  );
}

function AnalysisCard({ a }: { a: AnalysisRead }) {
  const m = a.measurements_json;
  const meta = (m?.meta ?? null) as Record<string, unknown> | null;
  const kind = m?.kind as string | undefined;

  return (
    <div className="rounded-lg border border-webb-star/10 bg-webb-ink/40 p-5">
      <div className="mb-4 flex items-baseline justify-between gap-4">
        <div>
          <h2 className="text-lg font-medium text-webb-star">
            {a.analyzer_name}
            <span className="ml-2 text-xs font-mono text-webb-star/40">v{a.analyzer_version}</span>
          </h2>
          <p className="text-xs text-webb-star/50">
            Generated {formatDate(a.generated_at)}
          </p>
        </div>
      </div>

      {a.is_permanent_failure && (
        <div className="rounded border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-200">
          Permanent failure: {a.last_error ?? "unknown"}
        </div>
      )}

      {!a.is_permanent_failure && m == null && a.last_error && (
        <div className="rounded border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-200">
          Pending retry: {a.last_error}
        </div>
      )}

      {m && kind === "image" && <ImageMeasurements m={m} />}
      {m && kind === "spectrum" && <SpectrumMeasurements m={m} />}

      {meta && (
        <details className="mt-5 text-xs text-webb-star/60">
          <summary className="cursor-pointer text-webb-star/70 hover:text-webb-star">
            Reproducibility metadata
          </summary>
          <dl className="mt-2 rounded border border-webb-star/10 bg-webb-deep/40 p-3">
            {Object.entries(meta).map(([k, v]) => (
              <StatRow key={k} label={k} value={String(v ?? "—")} />
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}

function confidenceClass(c: string): string {
  if (c === "high") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-200";
  if (c === "medium") return "border-amber-500/30 bg-amber-500/10 text-amber-200";
  return "border-webb-star/20 bg-webb-deep/40 text-webb-star/70";
}

function severityClass(s: string): string {
  if (s === "critical") return "border-red-500/30 bg-red-500/5 text-red-200";
  if (s === "warning") return "border-amber-500/30 bg-amber-500/5 text-amber-200";
  return "border-sky-500/30 bg-sky-500/5 text-sky-200";
}

function AiReportCard({ r }: { r: AiReportRead }) {
  const report = r.report_json;
  return (
    <div className="rounded-lg border border-webb-accent/20 bg-webb-ink/40 p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded border border-webb-accent/40 bg-webb-accent/10 px-2 py-0.5 text-xs uppercase tracking-wider text-webb-accent">
            AI-generated
          </span>
          {r.mode === "local_vision" && (
            <span className="rounded border border-violet-400/40 bg-violet-400/10 px-2 py-0.5 text-xs uppercase tracking-wider text-violet-200">
              vision
            </span>
          )}
          <span className="font-mono text-xs text-webb-star/50">
            {r.model_name} · {r.prompt_version}
          </span>
        </div>
        <span className="text-xs text-webb-star/40">{formatDate(r.generated_at)}</span>
      </div>

      {r.is_permanent_failure ? (
        <div className="rounded border border-red-500/30 bg-red-500/5 p-3 text-sm text-red-200">
          Generation failed: {r.last_error ?? "unknown"}
        </div>
      ) : !report ? (
        <div className="rounded border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-200">
          Pending or retrying{r.last_error ? `: ${r.last_error}` : ""}.
        </div>
      ) : (
        <div className="space-y-5">
          <p className="text-sm leading-relaxed text-webb-star/90">{report.summary}</p>

          {report.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {report.tags.map((t) => (
                <span
                  key={t}
                  className="rounded-full border border-webb-star/15 bg-webb-deep/50 px-2 py-0.5 text-xs text-webb-star/70"
                >
                  #{t}
                </span>
              ))}
            </div>
          )}

          {report.measured_facts.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
                Measured facts
              </h3>
              <dl>
                {report.measured_facts.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-baseline justify-between gap-4 border-b border-webb-star/5 py-1.5 last:border-b-0"
                  >
                    <dt className="text-xs text-webb-star/60">
                      {f.name} <span className="text-webb-star/30">({f.source})</span>
                    </dt>
                    <dd className="font-mono text-sm text-webb-star/90">{f.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}

          {report.interesting_features.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
                Interesting features
              </h3>
              <ul className="space-y-2">
                {report.interesting_features.map((f, i) => (
                  <li key={i} className="rounded border border-webb-star/10 bg-webb-deep/30 p-3 text-sm">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="text-webb-star/90">{f.feature}</span>
                      <span
                        className={`shrink-0 rounded border px-1.5 py-0.5 text-xs uppercase ${confidenceClass(f.confidence)}`}
                      >
                        {f.confidence}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-webb-star/50">{f.evidence}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {report.quality_flags.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
                Quality flags
              </h3>
              <ul className="space-y-2">
                {report.quality_flags.map((f, i) => (
                  <li key={i} className={`rounded border p-3 text-sm ${severityClass(f.severity)}`}>
                    <div className="flex items-baseline justify-between gap-3">
                      <span>{f.flag}</span>
                      <span className="shrink-0 text-xs uppercase opacity-70">{f.severity}</span>
                    </div>
                    {f.details && <p className="mt-1 text-xs opacity-80">{f.details}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {report.recommended_next_steps.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-webb-accent">
                Recommended next steps
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-webb-star/80">
                {report.recommended_next_steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="rounded border border-webb-star/15 bg-webb-deep/40 p-3 text-xs text-webb-star/50">
            AI interpretation — hypothesis-generating, not confirmation.
            {report.human_validation_required ? " Human validation required." : ""}
          </p>
        </div>
      )}
    </div>
  );
}

export default async function ProductDetailPage({ params }: PageProps) {
  const { id } = await params;
  const productId = Number.parseInt(id, 10);
  if (!Number.isFinite(productId)) notFound();

  const [productResult, analysisResult, aiReportsResult] = await Promise.all([
    getProduct(productId),
    getProductAnalyses(productId),
    getProductAiReports(productId),
  ]);

  if (!productResult.ok) {
    if (productResult.error.includes("404")) notFound();
    return (
      <main className="mx-auto max-w-5xl px-6 py-16">
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-200">
          Couldn&apos;t load product ({productResult.error}).
        </div>
      </main>
    );
  }

  const product = productResult.data;
  const analyses = analysisResult.ok ? analysisResult.data : [];
  const aiReports = aiReportsResult.ok ? aiReportsResult.data : [];

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-8 flex items-start justify-between gap-6">
        <div className="min-w-0">
          <Link
            href="/"
            className="text-xs uppercase tracking-wider text-webb-star/50 hover:text-webb-star"
          >
            ← WebbWatch AI
          </Link>
          <h1 className="mt-2 truncate font-mono text-xl text-webb-star">{product.filename}</h1>
          <p className="mt-1 text-xs text-webb-star/50">
            Product #{product.id}
            {product.product_type && (
              <>
                {" · "}
                <span className="rounded border border-webb-star/20 bg-webb-deep/60 px-1.5 py-0.5 uppercase tracking-wider">
                  {product.product_type}
                </span>
              </>
            )}
          </p>
        </div>
        <HealthBadge />
      </header>

      {product.preview_url && (
        <section className="mb-8 overflow-hidden rounded-lg border border-webb-star/10 bg-black">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={product.preview_url}
            alt={product.filename}
            className="mx-auto block max-h-[640px] w-auto"
          />
        </section>
      )}

      <section className="mb-8 rounded-lg border border-webb-star/10 bg-webb-ink/40 p-5">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-webb-accent">
          File
        </h2>
        <dl className="grid gap-x-8 gap-y-1 md:grid-cols-2">
          <StatRow label="Size" value={formatSize(product.file_size)} />
          <StatRow label="Extension" value={product.file_extension ?? "—"} />
          <StatRow label="MAST product id" value={product.mast_product_id ?? "—"} />
          <StatRow label="First seen" value={formatDate(product.first_seen_at)} />
          <StatRow label="Last seen" value={formatDate(product.last_seen_at)} />
        </dl>
        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          {product.cloud_uri && (
            <a
              href={product.cloud_uri}
              target="_blank"
              rel="noreferrer"
              className="rounded border border-webb-star/20 bg-webb-deep/60 px-3 py-1.5 font-mono text-webb-star/80 hover:border-webb-accent/40 hover:text-webb-star"
            >
              {product.cloud_uri}
            </a>
          )}
          {product.mast_download_uri && (
            <a
              href={product.mast_download_uri}
              target="_blank"
              rel="noreferrer"
              className="rounded border border-webb-star/20 bg-webb-deep/60 px-3 py-1.5 text-webb-star/80 hover:border-webb-accent/40 hover:text-webb-star"
            >
              MAST portal →
            </a>
          )}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-lg font-medium text-webb-star/90">Deterministic analysis</h2>
          <span className="text-xs text-webb-star/40">measured facts · no AI</span>
        </div>
        {analyses.length === 0 ? (
          <div className="rounded-lg border border-dashed border-webb-star/20 bg-webb-ink/40 p-6 text-sm text-webb-star/60">
            No analysis yet. Analyses are enqueued for watchlist-matched products and run on the
            background worker — start it with{" "}
            <code className="rounded bg-webb-deep px-1.5 py-0.5 text-xs">
              rq worker -u $REDIS_URL analyze
            </code>
            .
          </div>
        ) : (
          <div className="space-y-4">
            {analyses.map((a) => (
              <AnalysisCard key={a.id} a={a} />
            ))}
          </div>
        )}
      </section>

      <section className="mt-8">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-lg font-medium text-webb-star/90">AI summary</h2>
          <span className="text-xs text-webb-star/40">local model · interpretation</span>
        </div>
        {aiReports.length === 0 ? (
          <div className="rounded-lg border border-dashed border-webb-star/20 bg-webb-ink/40 p-6 text-sm text-webb-star/60">
            No AI summary yet. Reports are generated by a local Ollama model after deterministic
            analysis, for watchlist-matched products. Enable it by installing Ollama, pulling a
            model, and setting{" "}
            <code className="rounded bg-webb-deep px-1.5 py-0.5 text-xs">LOCAL_AI_ENABLE=true</code>.
          </div>
        ) : (
          <div className="space-y-4">
            {aiReports.map((r) => (
              <AiReportCard key={r.id} r={r} />
            ))}
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-3">
          <RegenerateAiButton productId={product.id} />
          <RegenerateAiButton productId={product.id} vision />
        </div>
      </section>
    </main>
  );
}
