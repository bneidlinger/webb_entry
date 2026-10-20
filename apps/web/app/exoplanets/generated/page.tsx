import type { Metadata } from "next";
import Link from "next/link";
import { ExoplanetNav } from "@/components/exoplanet-nav";
import { SavedPortraitList } from "@/components/saved-portraits";

export const metadata: Metadata = { title: "Saved planet portraits — WebbWatch AI" };
export default async function SavedPage({ searchParams }: { searchParams: Promise<{ planet?: string }> }) {
  const { planet } = await searchParams;
  return <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12"><ExoplanetNav active="saved" /><header className="mt-10"><p className="text-xs uppercase tracking-widest text-webb-accent">Your portrait archive</p><h1 className="mt-3 text-4xl font-semibold">Saved portraits</h1><p className="mt-4 max-w-2xl text-webb-star/65">Every version keeps its image, original prompt and evidence together. Failed or interrupted requests retain their brief too.</p>{planet && <Link href="/exoplanets/generated" className="mt-4 inline-block text-webb-accent underline">Show all planets</Link>}</header><SavedPortraitList planetId={planet} /></main>;
}
