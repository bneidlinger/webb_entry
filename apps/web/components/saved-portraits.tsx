"use client";

import Link from "next/link";
import Image from "next/image";
import { useCallback, useEffect, useState } from "react";

import { PortraitEvidence } from "@/components/portrait-evidence";
import { PortraitPrompt } from "@/components/portrait-prompt";
import { generationDate, isGenerating, portraitAsset, portraitRequest, type SavedPortrait } from "@/lib/generated-portraits";

export function SavedPortraitList({ planetId }: { planetId?: string }) {
  const [page, setPage] = useState<{ items: SavedPortrait[]; has_more: boolean } | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try {
      setPage(await portraitRequest(`?limit=12&offset=${offset}${planetId ? `&planet_id=${encodeURIComponent(planetId)}` : ""}`));
      setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to load saved portraits."); }
  }, [planetId, offset]);
  useEffect(() => { void refresh(); }, [refresh]);
  const active = page?.items.some(isGenerating);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => { void refresh(); }, 4000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  return <div className="mt-8">
    {error && <p role="alert" className="text-amber-200">{error} <button className="min-h-11 underline" onClick={() => void refresh()}>Retry</button></p>}
    {!page && !error && <p role="status">Loading saved portraits…</p>}
    {page?.items.length === 0 && <section className="rounded-2xl border border-webb-star/15 p-8"><h2 className="text-xl font-medium">Your next world starts in the catalog</h2><p className="mt-3 text-webb-star/60">No generated versions saved{planetId ? " for this planet" : ""} yet. Pick a planet, review its evidence and select Generate image.</p><Link href="/exoplanets/catalog" className="mt-5 inline-flex min-h-11 items-center text-webb-accent underline">Pick a planet →</Link></section>}
    <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">{page?.items.map((row) => <Link key={row.id} href={`/exoplanets/generated/${row.id}`} className="overflow-hidden rounded-2xl border border-webb-star/15 bg-webb-ink hover:border-webb-accent/60">
      {row.image_url ? <Image unoptimized src={portraitAsset(row.image_url)} alt={`Hypothetical illustration of ${row.planet_name}`} width={1024} height={1024} className="aspect-square w-full object-contain bg-black" /> : <div className="flex aspect-[2/1] items-center justify-center bg-webb-accent/5 text-sm text-webb-accent">{row.status === "failed" || row.status === "interrupted" ? "Image unavailable · brief saved" : "Generation in progress"}</div>}
      <div className="p-5"><p className="text-xs uppercase tracking-widest text-webb-accent">{row.status}</p><h2 className="mt-2 text-xl font-semibold">{row.planet_name}</h2><p className="mt-2 text-xs text-webb-star/55">{generationDate(row.created_at)}</p><p className="mt-3 text-sm text-webb-star/65">Image, prompt & evidence →</p></div>
    </Link>)}</div>
    {page && <div className="mt-6 flex justify-between gap-4"><button disabled={!offset} onClick={() => { setPage(null); setOffset(Math.max(0, offset - 12)); }} className="min-h-11 text-webb-accent disabled:opacity-30">← Newer</button><button disabled={!page.has_more} onClick={() => { setPage(null); setOffset(offset + 12); }} className="min-h-11 text-webb-accent disabled:opacity-30">Older →</button></div>}
  </div>;
}

export function SavedPortraitView({ id }: { id: string }) {
  const [row, setRow] = useState<SavedPortrait | null>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try { setRow(await portraitRequest(`/${encodeURIComponent(id)}`)); setError(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Unable to load portrait."); }
  }, [id]);
  useEffect(() => { void refresh(); }, [refresh]);
  const active = row && isGenerating(row);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => { void refresh(); }, 3000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);
  return <>
    {error && <p role="alert" className="mt-8 text-amber-200">{error} <button className="min-h-11 underline" onClick={() => void refresh()}>Retry</button></p>}
    {!row && !error && <p role="status" className="mt-8">Loading saved portrait…</p>}
    {row && <>
      <header className="my-8"><p className="text-xs uppercase tracking-widest text-webb-accent">Saved portrait · {row.status}</p><h1 className="mt-3 text-4xl font-semibold">{row.planet_name}</h1><p className="mt-3 text-sm text-webb-star/60">{generationDate(row.created_at)} · {row.model} · {row.settings.size} · {row.settings.quality} quality</p><Link href={`/exoplanets/catalog/${row.planet_id}`} className="mt-4 inline-flex min-h-11 items-center text-sm text-webb-accent underline">Open planet & generate another version →</Link></header>
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(340px,1fr)]"><div className="min-w-0 space-y-6">
        {row.image_url ? <figure className="overflow-hidden rounded-2xl border border-webb-star/15 bg-black">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={portraitAsset(row.image_url)} alt={`AI-generated hypothetical illustration of ${row.planet_name}`} width={1024} height={1024} className="h-auto w-full" />
          <figcaption className="bg-webb-ink p-5 text-sm leading-relaxed text-webb-star/65"><strong className="text-webb-star">Hypothetical illustration.</strong> Detailed appearance is not observed. Requested camera settings, exact color and photometry have not been validated. Evidence below was saved before generation.</figcaption>
        </figure> : <div role="status" className="rounded-2xl border border-webb-accent/25 bg-webb-accent/5 p-8"><h2 className="text-xl">{active ? "Creating your planet portrait…" : "Generation did not complete"}</h2><p className="mt-3 text-sm leading-relaxed text-webb-star/65">{row.error ?? "Your exact prompt and evidence are saved. This may take a few minutes; it is safe to leave this page and return."}</p></div>}
        <div className="flex flex-wrap gap-4 text-sm text-webb-accent">{row.image_url && <a href={`${portraitAsset(row.image_url)}?download=true`} className="min-h-11 underline">Download image</a>}<a href={portraitAsset(row.prompt_url)} className="min-h-11 underline">Saved prompt</a><a href={portraitAsset(row.evidence_url)} className="min-h-11 underline">Saved evidence JSON</a></div>
        {row.prompt && <PortraitPrompt name={row.planet_name} prompt={row.prompt} evidence={JSON.stringify({ ...row.evidence, generation: { ...row, evidence: undefined, prompt: undefined }, submitted_prompt: row.prompt, geometry_validated: false }, null, 2)} />}
        {row.output?.revised_prompt && <details className="rounded-xl border border-webb-star/15 p-5 text-sm"><summary className="cursor-pointer text-webb-accent">Provider-revised prompt</summary><p className="mt-3 whitespace-pre-wrap text-webb-star/65">{row.output.revised_prompt}</p></details>}
        <section className="text-xs leading-relaxed text-webb-star/55"><p>This version retains its original catalog snapshot and evidence categories. New catalog data does not rewrite this record.</p><details className="mt-3"><summary className="cursor-pointer text-webb-accent">Provenance & checksums</summary><p className="mt-2 break-all">Prompt SHA-256: {row.prompt_sha256}</p>{row.output && <p className="mt-2 break-all">Image SHA-256: {row.output.image_sha256}</p>}<p className="mt-2 break-all">Catalog SHA-256: {row.evidence?.catalog_detail.snapshot.catalog_sha256}</p><p className="mt-2">Generation ID: {row.id}</p></details></section>
      </div>{row.evidence && <PortraitEvidence groups={row.evidence.groups} title="Evidence saved with this image" />}</div>
    </>}
  </>;
}
