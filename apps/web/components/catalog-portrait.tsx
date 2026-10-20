import Image from "next/image";
import Link from "next/link";

import { portraitPreview, type PortraitPreview } from "@/lib/portrait-previews";

export function CatalogPortraitThumbnail({ name, saved, unavailable }: { name: string; saved?: PortraitPreview; unavailable: boolean }) {
  const preview = portraitPreview(name, saved);
  if (!preview) return <span className="text-xs text-webb-star/35">{unavailable ? "Unavailable" : "—"}<span className="sr-only">{unavailable ? "" : " No saved image"}</span></span>;
  return <Link prefetch={false} href={preview.href} className="group block w-16 rounded-lg focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent" aria-label={`View ${name} image, prompt and evidence`}>
    <Image src={preview.image} alt={`Hypothetical illustration of ${name}`} width={64} height={64} sizes="64px" unoptimized={preview.saved} className="h-16 w-16 rounded-lg border border-webb-star/15 bg-black object-contain group-hover:border-webb-accent" />
    <span className="mt-1 block text-center text-[10px] text-webb-accent">View image</span>
  </Link>;
}

export function CatalogPortraitPreview({ name, saved }: { name: string; saved?: PortraitPreview | null }) {
  const preview = portraitPreview(name, saved);
  if (!preview) return null;
  return <figure className="mb-6 flex flex-col gap-5 border-b border-webb-star/10 pb-6 sm:flex-row sm:items-center">
    <Link prefetch={false} href={preview.href} className="block w-64 max-w-full shrink-0 self-start rounded-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent" aria-label={`Open full ${name} image with saved prompt and evidence`}>
      <Image src={preview.image} alt={`Hypothetical illustration of ${name}`} width={256} height={256} sizes="256px" unoptimized={preview.saved} className="aspect-square w-full rounded-xl border border-webb-star/15 bg-black object-contain" />
    </Link>
    <figcaption className="max-w-lg">
      <p className="text-xs uppercase tracking-widest text-emerald-300">{preview.label}</p>
      <h3 className="mt-2 text-2xl font-semibold">{name}</h3>
      <p className="mt-3 text-sm leading-relaxed text-webb-star/65">Hypothetical illustration. Detailed appearance is not observed. Open the full image to see its saved prompt and Measured / Inferred / Illustrative evidence.</p>
      <Link prefetch={false} href={preview.href} className="mt-3 inline-flex min-h-11 items-center text-sm text-webb-accent underline underline-offset-4">View full image & evidence →</Link>
    </figcaption>
  </figure>;
}
