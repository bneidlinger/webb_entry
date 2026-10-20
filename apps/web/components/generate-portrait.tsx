"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { CatalogPortraitPreview } from "@/components/catalog-portrait";
import { generationDate, isGenerating, portraitRequest, promptHash, type GenerationConfig, type SavedPortrait } from "@/lib/generated-portraits";
import { latestPortraitQuery, type PortraitPreview } from "@/lib/portrait-previews";

const button = "inline-flex min-h-11 items-center justify-center rounded-lg bg-webb-accent px-5 py-3 text-sm font-semibold text-webb-deep disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent";

export function GeneratePortrait({ planetId, name, prompt, insufficient }: { planetId: string; name: string; prompt: string; insufficient: boolean }) {
  const [config, setConfig] = useState<GenerationConfig | null>(null);
  const [history, setHistory] = useState<SavedPortrait[]>([]);
  const [latest, setLatest] = useState<PortraitPreview | null>(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [accepted, setAccepted] = useState<string | null>(null);
  const requestId = useRef<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      const [settings, saved, previews] = await Promise.allSettled([
        portraitRequest<GenerationConfig>("/config"),
        portraitRequest<{ items: SavedPortrait[] }>(`?planet_id=${encodeURIComponent(planetId)}&limit=5`),
        portraitRequest<{ items: PortraitPreview[] }>(latestPortraitQuery([planetId])),
      ]);
      if (settings.status === "fulfilled") setConfig(settings.value);
      if (saved.status === "fulfilled") setHistory(saved.value.items);
      if (previews.status === "fulfilled") setLatest(previews.value.items[0] ?? null);
      const failed = [settings, saved, previews].find((result) => result.status === "rejected");
      if (failed?.status === "rejected") throw failed.reason;
      setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to load generation status."); }
    finally { setLoading(false); }
  }, [planetId]);
  useEffect(() => { void refresh(); }, [refresh]);
  const active = history.some(isGenerating);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => { void refresh(); }, 4000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);

  async function generate() {
    if (sending) return;
    setSending(true); setError("");
    try {
      const hash = await promptHash(prompt);
      // Retain an ambiguous request across reloads so retrying cannot charge twice.
      const key = `portrait-request:${planetId}:${hash}`;
      requestId.current ??= window.sessionStorage.getItem(key) ?? crypto.randomUUID();
      window.sessionStorage.setItem(key, requestId.current);
      const row = await portraitRequest<SavedPortrait>("", {
        method: "POST", headers: { "Content-Type": "application/json", "X-WebbWatch-Action": "generate-portrait" },
        body: JSON.stringify({ request_id: requestId.current, planet_id: planetId, prompt_sha256: hash }),
      });
      setHistory((previous) => [row, ...previous.filter((item) => item.id !== row.id)].slice(0, 5));
      setAccepted(row.id); requestId.current = null; window.sessionStorage.removeItem(key);
    } catch (err) { setError(err instanceof Error ? err.message : "The request could not be confirmed. Retry to check the same request."); }
    finally { setSending(false); }
  }

  return <section aria-labelledby="generate-heading" className="mb-8 rounded-2xl border border-webb-accent/30 bg-webb-accent/5 p-5 sm:p-6">
    <CatalogPortraitPreview name={name} saved={latest} />
    <div className="flex flex-wrap items-start justify-between gap-6">
      <div className="max-w-2xl"><p className="text-xs uppercase tracking-widest text-webb-accent">From evidence to illustration</p><h2 id="generate-heading" className="mt-2 text-2xl font-semibold">Generate {name} in WebbWatch</h2>
        <p className="mt-3 text-sm leading-relaxed text-webb-star/70">Use the exact image prompt below. Each version saves its image, prompt, sources and Measured / Inferred / Illustrative evidence together. The image remains hypothetical.</p>
        {config && <p className="mt-3 text-xs leading-relaxed text-webb-star/55">{config.provider} · {config.model} · {config.settings.size} · {config.settings.quality} quality<br />{config.billing_note} <a href={config.pricing_url} target="_blank" rel="noreferrer" className="text-webb-accent underline">API pricing ↗</a></p>}
      </div>
      <div className="flex flex-col gap-3"><button className={button} disabled={loading || sending || active || insufficient || !config?.ready} onClick={() => void generate()}>{sending ? "Saving request…" : active ? "Image generating…" : history.length ? "Generate another version" : "Generate image"}</button><Link href={`/exoplanets/generated?planet=${encodeURIComponent(planetId)}`} className="text-center text-sm text-webb-accent underline underline-offset-4">View saved versions →</Link></div>
    </div>
    {insufficient && <p className="mt-4 text-sm text-amber-200">A suitable radius is missing. Choose another planet to generate a scaled portrait.</p>}
    {config && !config.ready && <div className="mt-4 rounded-xl border border-amber-200/20 p-4"><p className="font-medium text-amber-100">Image generation needs server setup</p><p className="mt-2 text-sm text-webb-star/65">{config.reason}</p><details className="mt-3 text-sm text-webb-star/60"><summary className="cursor-pointer text-webb-accent">Setup instructions</summary><p className="mt-2">In the project’s server .env, set OPENAI_API_KEY and PORTRAIT_GENERATION_ENABLE=true, then restart the API. Keep the key on the server. This local prototype uses the OpenAI API; the earlier built-in imagegen examples remain available.</p></details><button className="mt-3 min-h-11 text-sm text-webb-accent underline" onClick={() => void refresh()}>Recheck setup</button></div>}
    {error && <div role="alert" className="mt-4 text-sm text-amber-200">{error}<button className="ml-3 min-h-11 underline" onClick={() => void refresh()}>Refresh status</button></div>}
    <p role="status" className="mt-3 text-sm text-webb-star/65">{loading ? "Checking generation service…" : active ? "Your brief is saved. Generation may take a few minutes; you can leave and return to Saved portraits." : accepted ? "Request saved. Open the saved version to follow its progress and view the result." : ""}</p>
    {history.length > 0 && <ul className="mt-4 divide-y divide-webb-star/10 border-t border-webb-star/10">{history.map((row) => <li key={row.id}><Link href={`/exoplanets/generated/${row.id}`} className="flex min-h-12 flex-wrap items-center justify-between gap-2 py-3 text-sm hover:text-webb-accent"><span>{generationDate(row.created_at)}</span><span className={row.status === "completed" ? "text-emerald-300" : "text-webb-accent"}>{row.status === "completed" ? "View image & evidence" : row.status} →</span></Link></li>)}</ul>}
  </section>;
}
