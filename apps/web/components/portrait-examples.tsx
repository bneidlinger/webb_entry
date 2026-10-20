import Image from "next/image";
import Link from "next/link";

import { portraitExamples } from "@/lib/portrait-gallery";

export function PortraitExamples({ active }: { active: string }) {
  return <nav aria-label="Portrait examples" className="mb-8 grid gap-3 sm:grid-cols-2">
    {portraitExamples.map((portrait) => <Link key={portrait.slug} href={portrait.href} aria-current={active === portrait.slug ? "page" : undefined} className={`flex items-center gap-4 rounded-xl border p-3 transition hover:border-webb-accent/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-webb-accent ${active === portrait.slug ? "border-webb-accent/40 bg-webb-accent/10" : "border-webb-star/15 bg-webb-ink"}`}>
      <Image src={portrait.image} alt="" width={64} height={64} unoptimized className="size-16 rounded-lg bg-black" />
      <div><p className="text-[10px] uppercase tracking-widest text-webb-accent">Portrait {portrait.number}</p><p className="mt-1 font-medium">{portrait.name}</p><p className="mt-1 text-xs text-webb-star/55">{portrait.description}</p></div>
    </Link>)}
  </nav>;
}
