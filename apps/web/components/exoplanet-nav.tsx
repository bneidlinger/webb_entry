import Link from "next/link";

export function ExoplanetNav({ active }: { active: "catalog" | "portrait" | "saved" }) {
  return (
    <nav aria-label="Main navigation" className="flex flex-wrap items-center justify-between gap-4 border-b border-webb-star/10 pb-6">
      <Link href="/" className="text-lg font-semibold">WebbWatch <span className="text-webb-accent">AI</span></Link>
      <div className="flex flex-wrap gap-5 text-sm">
        <Link href="/" className="text-webb-star/65 hover:text-webb-star">JWST feed</Link>
        <Link href="/exoplanets/catalog" aria-current={active === "catalog" ? "page" : undefined} className={active === "catalog" ? "text-webb-accent" : "text-webb-star/65 hover:text-webb-star"}>Ranked catalog</Link>
        <Link href="/exoplanets" aria-current={active === "portrait" ? "page" : undefined} className={active === "portrait" ? "text-webb-accent" : "text-webb-star/65 hover:text-webb-star"}>Portrait examples</Link>
        <Link href="/exoplanets/generated" aria-current={active === "saved" ? "page" : undefined} className={active === "saved" ? "text-webb-accent" : "text-webb-star/65 hover:text-webb-star"}>Saved portraits</Link>
        <Link href="/alerts" className="text-webb-star/65 hover:text-webb-star">Alerts</Link>
      </div>
    </nav>
  );
}
