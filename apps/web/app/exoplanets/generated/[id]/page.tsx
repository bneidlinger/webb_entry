import type { Metadata } from "next";
import Link from "next/link";
import { ExoplanetNav } from "@/components/exoplanet-nav";
import { SavedPortraitView } from "@/components/saved-portraits";

export const metadata: Metadata = { title: "Saved image & evidence — WebbWatch AI" };
export default async function SavedPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-12"><ExoplanetNav active="saved" /><Link href="/exoplanets/generated" className="mt-7 inline-flex min-h-11 items-center text-sm text-webb-accent">← Saved portraits</Link><SavedPortraitView id={id} /></main>;
}
