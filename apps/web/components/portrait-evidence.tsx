"use client";

import { useRef, useState } from "react";

import type { EvidenceGroup, EvidenceLink } from "@/lib/portraits";

const treatments = {
  measured: { text: "text-emerald-300", dot: "bg-emerald-300", background: "bg-emerald-300/10" },
  inferred: { text: "text-webb-accent", dot: "bg-webb-accent", background: "bg-webb-accent/10" },
  illustrative: { text: "text-amber-200", dot: "bg-amber-200", background: "bg-amber-200/10" },
};

function SourceLink({ source }: { source: EvidenceLink }) {
  const external = source.href.startsWith("https://");
  return (
    <a
      href={source.href}
      target={external ? "_blank" : undefined}
      rel={external ? "noreferrer noopener" : undefined}
      className="inline-flex items-baseline gap-1 text-xs leading-relaxed text-webb-accent underline decoration-webb-accent/30 underline-offset-4 hover:decoration-webb-accent focus-visible:rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent"
    >
      {source.label}
      {external && <><span aria-hidden="true">↗</span><span className="sr-only"> (opens in a new tab)</span></>}
    </a>
  );
}

export function PortraitEvidence({ groups, title = "Behind the portrait" }: { groups: EvidenceGroup[]; title?: string }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  function focusTab(index: number) {
    setActiveIndex(index);
    tabs.current[index]?.focus();
  }

  return (
    <aside aria-labelledby="evidence-heading" className="min-w-0">
      <div className="mb-5">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-webb-accent">Follow the evidence</p>
        <h2 id="evidence-heading" className="mt-2 text-2xl font-semibold tracking-tight">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-webb-star/65">
          Choose a category to see what supports the image and where imagination begins.
        </p>
      </div>
      <div role="tablist" aria-label="Evidence categories" className="mb-3 grid grid-cols-3 gap-1 rounded-xl border border-webb-star/10 bg-webb-ink p-1">
        {groups.map((group, index) => (
          <button
            key={group.id}
            ref={(element) => { tabs.current[index] = element; }}
            role="tab"
            id={`tab-${group.id}`}
            aria-selected={activeIndex === index}
            aria-controls={`panel-${group.id}`}
            tabIndex={activeIndex === index ? 0 : -1}
            onClick={() => setActiveIndex(index)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight") {
                event.preventDefault();
                focusTab((index + 1) % groups.length);
              } else if (event.key === "ArrowLeft") {
                event.preventDefault();
                focusTab((index - 1 + groups.length) % groups.length);
              } else if (event.key === "Home" || event.key === "End") {
                event.preventDefault();
                focusTab(event.key === "Home" ? 0 : groups.length - 1);
              }
            }}
            className={`min-h-11 rounded-lg px-2 text-xs font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-webb-accent sm:text-sm ${activeIndex === index ? `${treatments[group.id].background} ${treatments[group.id].text}` : "text-webb-star/60 hover:bg-webb-star/5 hover:text-webb-star"}`}
          >
            {group.title}
          </button>
        ))}
      </div>
      <div>
        {groups.map((group, index) => {
          const treatment = treatments[group.id];
          return (
            <section
              key={group.id}
              id={`panel-${group.id}`}
              role="tabpanel"
              aria-labelledby={`tab-${group.id}`}
              hidden={activeIndex !== index}
              tabIndex={0}
              className="rounded-2xl border border-webb-star/10 bg-webb-ink/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-webb-accent"
            >
              <div className="flex items-center gap-3 p-5">
                <span aria-hidden="true" className={`flex size-8 shrink-0 items-center justify-center rounded-full ${treatment.background}`}>
                  <span className={`size-2 rounded-full ${treatment.dot}`} />
                </span>
                <span className="flex-1">
                  <span className={`block text-base font-semibold ${treatment.text}`}>{group.title}</span>
                  <span className="mt-1 block text-xs leading-relaxed text-webb-star/60">{group.description}</span>
                </span>
              </div>
              <ul className="divide-y divide-webb-star/10 border-t border-webb-star/10 px-5">
                {group.claims.map((claim) => (
                  <li key={claim.title} className="py-4">
                    <h3 className="text-sm font-medium text-webb-star">{claim.title}</h3>
                    {claim.value && <p className="mt-1.5 text-sm font-medium tabular-nums text-webb-star/90">{claim.value}</p>}
                    <p className="mt-2 text-sm leading-relaxed text-webb-star/65">{claim.explanation}</p>
                    <div className="mt-3 flex flex-col items-start gap-2">
                      {claim.sources.map((source) => <SourceLink key={source.href} source={source} />)}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </aside>
  );
}
