import type { Metadata, Route } from "next";
import Link from "next/link";

import { CatalogPortraitThumbnail } from "@/components/catalog-portrait";
import { ExoplanetNav } from "@/components/exoplanet-nav";
import { catalogHref, getCatalog, scoreComponents, snapshotDate, spectrumLabels, type CatalogPage as CatalogPageData, type CatalogQuery, type SpectrumFilter } from "@/lib/exoplanets";
import { getPortraitPreviews } from "@/lib/portrait-previews-server";

export const metadata: Metadata = { title: "Ranked exoplanet catalog — WebbWatch AI", description: "Compare exoplanet data coverage and choose a sourced image prompt." };

type QueryParams = Record<string, string | string[] | undefined>;
function parseQuery(params: QueryParams): CatalogQuery {
  const one = (key: string) => typeof params[key] === "string" ? params[key] as string : "";
  const spectrum = one("spectrum");
  return {
    q: one("q").slice(0, 120), facility: one("facility").slice(0, 200),
    spectrum: ["all", "any", "transmission", "eclipse", "direct_imaging"].includes(spectrum) ? spectrum as SpectrumFilter : "all",
    min_score: Math.max(0, Math.min(100, Number(one("min_score")) || 0)),
    offset: Math.max(0, Math.min(100_000, Math.floor(Number(one("offset")) || 0))),
  };
}
const inputClass = "mt-2 min-h-11 w-full rounded-lg border border-webb-star/20 bg-webb-deep px-3 py-2 text-sm text-webb-star focus:outline focus:outline-2 focus:outline-webb-accent";
const actionClass = "inline-flex min-h-11 items-center justify-center rounded-lg border border-webb-accent/30 px-4 py-2 text-sm text-webb-accent hover:bg-webb-accent/10";

export default async function CatalogPage({ searchParams }: { searchParams: Promise<QueryParams> }) {
  const query = parseQuery(await searchParams);
  const result = await getCatalog(query);
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12">
      <ExoplanetNav active="catalog" />
      <header className="mb-8 mt-10">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-webb-accent">Exoplanet Portrait Atlas</p>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">Choose the next world.</h1>
        <p className="mt-4 max-w-3xl leading-relaxed text-webb-star/70">Start with the planets that have the most supporting data. Compare coverage, follow the evidence, and take a sourced image prompt into your next illustration.</p>
      </header>
      {!result.ok ? (
        <section role="alert" className="rounded-2xl border border-amber-200/25 bg-webb-ink p-6">
          <h2 className="text-lg font-medium">The catalog is temporarily unavailable</h2>
          <p className="mt-2 text-sm text-webb-star/65">WebbWatch could not load its saved catalog. Try again when the API is available; the first portrait remains accessible.</p>
          <div className="mt-4 flex flex-wrap gap-4"><a href={catalogHref(query)} className={actionClass}>Retry catalog</a><Link href="/exoplanets" className={actionClass}>View first portrait</Link></div>
        </section>
      ) : <CatalogResults data={result.data} query={query} />}
    </main>
  );
}

async function CatalogResults({ data, query }: { data: CatalogPageData; query: CatalogQuery }) {
  const { snapshot, items, total, limit, offset } = data;
  const previews = await getPortraitPreviews(items.map((planet) => planet.id));
  const portraits = new Map(previews.items.map((portrait) => [portrait.planet_id, portrait]));
  return <>
    <div className="mb-7 grid gap-3 sm:grid-cols-3">
      {[
        [snapshot.record_count.toLocaleString("en-US"), "Confirmed planets in this snapshot"],
        [snapshot.with_spectra.toLocaleString("en-US"), "With at least one listed spectrum"],
        [snapshot.top_tied_count.toLocaleString("en-US"), `Tied at the top score of ${snapshot.top_score}`],
      ].map(([value, label]) => <div key={label} className="rounded-xl border border-webb-star/10 bg-webb-ink p-5"><p className="text-3xl font-semibold tabular-nums">{value}</p><p className="mt-2 text-xs text-webb-star/60">{label}</p></div>)}
    </div>
    <div className="mb-7 rounded-xl border border-webb-accent/20 bg-webb-accent/5 p-5">
      <p className="text-sm leading-relaxed text-webb-star/80"><strong className="text-webb-star">Data availability / 100.</strong> This score is a starting point for research, not an appearance-confidence score. Spectral quality, visible color and phase curves are not assessed. Equal scores share a rank; names only break the display order.</p>
      <details className="mt-3 text-sm">
        <summary className="min-h-7 cursor-pointer text-webb-accent">How the ranking works</summary>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">{scoreComponents.map((part) => <li key={part.key} className="text-webb-star/65">{part.label}: up to {part.max} points</li>)}</ul>
        <p className="mt-3 text-xs leading-relaxed text-webb-star/60">Reported parameter weights: radius 10, mass 8, period 4, semi-major axis 4, equilibrium temperature 4, stellar temperature 6, stellar radius 4. Missing two-sided errors earn half credit. Limits, archive-calculated values, minimum/model masses and missing references earn no parameter credit. More spectra of the same type earn no extra points. Approved JWST observations earn no points. {snapshot.score_version}.</p>
      </details>
      <p className="mt-3 text-xs text-webb-star/50">Saved {snapshotDate(snapshot)} · NASA Exoplanet Archive · {snapshot.coverage === "all_confirmed_in_archive_at_retrieval" ? "All confirmed planets at retrieval" : "Local snapshot; live completeness unverified"} · <a href={snapshot.source} target="_blank" rel="noreferrer noopener" className="text-webb-accent underline underline-offset-4">Catalog documentation ↗</a></p>
    </div>
    <form key={JSON.stringify(query)} action="/exoplanets/catalog" method="get" aria-label="Filter the exoplanet catalog" className="rounded-2xl border border-webb-star/15 bg-webb-ink p-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1.2fr_0.7fr]">
        <label className="text-xs text-webb-star/65">Planet or host star<input name="q" type="search" maxLength={120} defaultValue={query.q} placeholder="Try WASP-39 or TRAPPIST-1" className={inputClass} /></label>
        <label className="text-xs text-webb-star/65">Spectral evidence<select name="spectrum" defaultValue={query.spectrum} className={inputClass}><option value="all">All planets</option><option value="any">Any listed spectra</option>{Object.entries(spectrumLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
        <label className="text-xs text-webb-star/65">Discovery facility<select name="facility" defaultValue={query.facility} className={inputClass}><option value="">All facilities</option>{snapshot.facilities.map((facility) => <option key={facility}>{facility}</option>)}</select></label>
        <label className="text-xs text-webb-star/65">Minimum score<input name="min_score" type="number" min={0} max={100} step="any" defaultValue={query.min_score} className={inputClass} /></label>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-4"><button type="submit" className={`${actionClass} bg-webb-accent/10`}>Apply filters</button><Link href="/exoplanets/catalog" className="text-sm text-webb-star/60 underline underline-offset-4">Reset</Link><p className="text-xs text-webb-star/45 sm:ml-auto">Discovery facility is not a complete observing-mission inventory.</p></div>
    </form>
    <div className="mb-3 mt-7 flex flex-wrap items-center justify-between gap-3 text-sm"><h2 className="font-medium">{total.toLocaleString("en-US")} matching {total === 1 ? "planet" : "planets"}</h2><span className="text-xs text-webb-star/50">Highest availability first · ranks remain global</span></div>
    <p className="mb-3 text-xs text-webb-star/50">Image thumbnails link to the illustration, prompt and evidence. Detailed appearance is hypothetical.{previews.unavailable && " Saved image previews are temporarily unavailable; curated examples are still shown."}</p>
    {items.length === 0 ? <div className="rounded-xl border border-webb-star/15 p-8 text-center"><h3 className="font-medium">{total === 0 ? "No planets match these filters" : "No planets on this page"}</h3><p className="mt-2 text-sm text-webb-star/65">{total === 0 ? "Try a shorter name, another facility, or a lower minimum score." : "Return to the first page of these results."}</p><Link className={`${actionClass} mt-5`} href={catalogHref(total === 0 ? {} : { ...query, offset: 0 }) as Route}>Return to results</Link></div> :
      <div className="overflow-x-auto rounded-xl border border-webb-star/15">
        <table className="w-full min-w-[700px] text-left text-sm">
          <caption className="sr-only">Exoplanets ranked by catalog data availability. Equal scores share the same rank.</caption>
          <thead className="bg-webb-ink text-xs text-webb-star/50"><tr>{["Rank", "Image", "Planet", "Availability", "Listed spectra", "Discovery facility", ""].map((label, i) => <th scope="col" key={i} className="px-4 py-4 font-medium">{label || <span className="sr-only">Open planet</span>}</th>)}</tr></thead>
          <tbody>{items.map((planet) => <tr key={planet.id} className="border-t border-webb-star/10 hover:bg-webb-star/[0.025]">
            <td className="px-4 py-4 align-top tabular-nums text-webb-star/65">{planet.rank}<span className="mt-1 block text-[10px] text-webb-star/40">{planet.tied_count > 1 ? "tied" : ""}</span></td>
            <td className="w-24 px-4 py-4"><CatalogPortraitThumbnail name={planet.planet} saved={portraits.get(planet.id)} unavailable={previews.unavailable} /></td>
            <th scope="row" className="px-4 py-4 font-normal"><Link prefetch={false} href={`/exoplanets/catalog/${planet.id}` as Route} className="font-medium text-webb-star hover:text-webb-accent">{planet.planet}</Link><span className="mt-1 block text-xs text-webb-star/45">{planet.host || "Host unrecorded"}</span>{planet.has_curated_appearance && <span className="mt-1 block text-xs text-emerald-300">Sourced appearance example</span>}</th>
            <td className="px-4 py-4"><span className="font-semibold tabular-nums text-webb-accent">{planet.score}</span><span className="text-xs text-webb-star/35"> / 100</span><div aria-hidden="true" className="mt-2 h-1 w-20 rounded bg-webb-star/10"><div className="h-1 rounded bg-webb-accent/65" style={{ width: `${planet.score}%` }} /></div></td>
            <td className="px-4 py-4 text-xs text-webb-star/65">{Object.entries(planet.spectra_counts).filter(([, n]) => n !== null && n > 0).map(([kind, n]) => <span className="block leading-6" key={kind}>{spectrumLabels[kind as keyof typeof spectrumLabels]} · {n}</span>)}{!Object.values(planet.spectra_counts).some((n) => n !== null && n > 0) && <span>{Object.values(planet.spectra_counts).some((n) => n === null) ? "None listed; counts incomplete" : "None listed"}</span>}</td>
            <td className="max-w-48 px-4 py-4 text-xs leading-relaxed text-webb-star/60">{planet.discovery_facility || "Not recorded"}</td>
            <td className="px-4 py-4"><Link prefetch={false} href={`/exoplanets/catalog/${planet.id}` as Route} className="inline-flex min-h-11 items-center whitespace-nowrap text-xs text-webb-accent underline underline-offset-4" aria-label={`View evidence and prompt for ${planet.planet}`}>Evidence & prompt →</Link></td>
          </tr>)}</tbody>
        </table>
      </div>}
    <nav aria-label="Catalog pagination" className="mt-5 flex flex-wrap items-center justify-between gap-4">
      <p className="text-xs text-webb-star/50">{items.length ? `${offset + 1}–${offset + items.length} of ${total.toLocaleString("en-US")}` : "No rows displayed"}</p>
      <div className="flex gap-3">{offset > 0 && <Link className={actionClass} href={catalogHref({ ...query, offset: Math.max(0, offset - limit) }) as Route}>Previous</Link>}{offset + limit < total && <Link className={actionClass} href={catalogHref({ ...query, offset: offset + limit }) as Route}>Next 25 →</Link>}</div>
    </nav>
    <footer className="mt-10 border-t border-webb-star/10 pt-6 text-xs leading-relaxed text-webb-star/45">This is a saved catalog, not a live literature search. Spectrum counts show archive listings, not observing time or independent measurements. Planets without sourced appearance evidence receive a conservative, neutral-gray prompt.</footer>
  </>;
}
