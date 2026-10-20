import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ExoplanetNav } from "@/components/exoplanet-nav";
import { GeneratePortrait } from "@/components/generate-portrait";
import { PortraitEvidence } from "@/components/portrait-evidence";
import { PortraitPrompt } from "@/components/portrait-prompt";
import { portraitForPlanet } from "@/lib/portrait-gallery";
import { basisLabels, getPlanet, promptEvidence, scoreComponents, snapshotDate, spectrumLabels } from "@/lib/exoplanets";

export const metadata: Metadata = { title: "Planet evidence & image prompt — WebbWatch AI" };

export default async function PlanetPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const result = await getPlanet(id);
  if (!result.ok && result.status === 404) notFound();
  if (!result.ok) return <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6"><ExoplanetNav active="catalog" /><section role="alert" className="mt-10 rounded-xl border border-amber-200/20 p-6"><h1 className="text-2xl">Planet evidence is temporarily unavailable</h1><p className="mt-3 text-webb-star/65">Try again when the catalog API is available.</p><a href={`/exoplanets/catalog/${encodeURIComponent(id)}`} className="mt-4 inline-block text-webb-accent underline">Retry this planet</a></section></main>;
  const { ranking, brief, snapshot } = result.data;
  const portrait = portraitForPlanet(ranking.planet);
  const missing = brief.parameters.filter((p) => p.points < p.max_points);
  const insufficient = brief.status === "insufficient_for_scaled_portrait";
  return <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12">
    <ExoplanetNav active="catalog" />
    <Link href="/exoplanets/catalog" className="mt-8 inline-flex min-h-11 items-center text-sm text-webb-accent">← Browse ranked catalog</Link>
    <header className="mb-8 mt-4">
      <div className="flex flex-wrap gap-3 text-xs uppercase tracking-widest text-webb-star/55"><span className="text-webb-accent">Selected world</span><span>Rank {ranking.rank}{ranking.tied_count > 1 ? ` · tied with ${ranking.tied_count - 1} others` : ""}</span></div>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-5xl">{ranking.planet}</h1>
      <p className="mt-3 text-sm text-webb-star/65">Host: {ranking.host || "not recorded"} · Discovery facility: {ranking.discovery_facility || "not recorded"}</p>
      <div className="mt-5 flex flex-wrap gap-x-5 gap-y-3 text-sm"><a href={brief.archive_url} target="_blank" rel="noreferrer noopener" className="text-webb-accent underline underline-offset-4">NASA planet record & spectra ↗</a>{portrait && <Link href={portrait.href} className="text-webb-accent underline underline-offset-4">See generated portrait {portrait.number} →</Link>}</div>
    </header>
    <GeneratePortrait planetId={ranking.id} name={ranking.planet} prompt={brief.prompt} insufficient={insufficient} />
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(340px,1fr)]">
      <div className="min-w-0 space-y-6">
        <section className="rounded-2xl border border-webb-star/15 bg-webb-ink p-5 sm:p-6" aria-labelledby="score-heading">
          <div className="flex items-start justify-between gap-5"><div><h2 id="score-heading" className="text-lg font-medium">Data availability</h2><p className="mt-2 text-xs leading-relaxed text-webb-star/55">Coverage of catalog parameters and spectra.<br />Appearance accuracy is not scored.</p></div><p className="text-4xl font-semibold tabular-nums text-webb-accent">{ranking.score}<span className="text-sm font-normal text-webb-star/45"> / 100</span></p></div>
          <dl className="mt-5 space-y-3">{scoreComponents.map((part) => <div key={part.key} className="flex justify-between gap-4 text-sm"><dt className="text-webb-star/65">{part.label}</dt><dd className="shrink-0 tabular-nums">{ranking.components[part.key]} <span className="text-webb-star/40">/ {part.max}</span></dd></div>)}</dl>
          <div className="mt-5 grid grid-cols-3 gap-2 border-t border-webb-star/10 pt-5">{Object.entries(spectrumLabels).map(([kind, label]) => <div key={kind}><p className="text-xs text-webb-star/50">{label}</p><p className="mt-1 text-lg tabular-nums">{ranking.spectra_counts[kind as keyof typeof spectrumLabels] ?? "Unknown"}</p></div>)}</div>
          <p className="mt-3 text-xs leading-relaxed text-webb-star/50">Archive spectrum listings; quality and wavelength coverage have not been reviewed. A listing alone does not establish an atmosphere, molecule or visible color. Approved JWST observation counts are retained in the evidence download and earn no points.</p>
          {missing.length > 0 && <details className="mt-4"><summary className="cursor-pointer text-sm text-webb-accent">Why some parameter points are missing</summary><ul className="mt-3 space-y-2 text-xs leading-relaxed text-webb-star/60">{missing.map((p) => <li key={p.field}><strong>{p.label} ({p.points}/{p.max_points}):</strong> {basisLabels[p.basis]}.</li>)}</ul></details>}
        </section>
        <div className={`rounded-xl border p-5 text-sm leading-relaxed ${insufficient ? "border-amber-200/30 bg-amber-200/5 text-amber-100" : "border-webb-accent/20 bg-webb-accent/5 text-webb-star/75"}`}>
          <strong>{insufficient ? "Not ready for a scaled portrait." : brief.appearance_evidence ? "Sourced appearance example." : "Catalog-only illustration."}</strong>{" "}{insufficient ? "A suitable radius is missing or is only a bound. The prompt explicitly prohibits a physically scaled view." : brief.appearance_evidence ? "This target has curated appearance evidence. Follow its sources and keep texture labeled as illustrative." : "Visible appearance has not been assessed. This prompt uses neutral gray and does not invent oceans, clouds or terrain as observations."}
        </div>
        <PortraitPrompt name={ranking.planet} prompt={brief.prompt} evidence={JSON.stringify(result.data, null, 2)} />
        <section className="rounded-xl border border-webb-star/10 p-5" aria-labelledby="unknowns-heading"><h2 id="unknowns-heading" className="font-medium">What the data does not tell us</h2><ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-relaxed text-webb-star/60">{brief.unknowns.map((unknown) => <li key={unknown}>{unknown}</li>)}</ul></section>
        <section className="text-xs leading-relaxed text-webb-star/50" aria-label="Snapshot provenance"><p>Saved {snapshotDate(snapshot)} · {snapshot.score_version} · {brief.prompt_version}</p><p className="mt-2">Composite values can mix studies and calculated estimates. Parameter links retain their original references. This catalog is a saved snapshot; the archive links may show newer data.</p><a href={snapshot.source} target="_blank" rel="noreferrer noopener" className="mt-2 inline-block text-webb-accent underline underline-offset-4">How NASA builds this catalog ↗</a><details className="mt-3"><summary className="cursor-pointer">Catalog SHA-256</summary><code className="mt-2 block break-all">{snapshot.catalog_sha256}</code></details></section>
      </div>
      <PortraitEvidence groups={promptEvidence(result.data)} title="Evidence for this prompt" />
    </div>
  </main>;
}
