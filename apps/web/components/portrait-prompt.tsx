"use client";

import { useRef, useState } from "react";

export function PortraitPrompt({ name, prompt, evidence }: { name: string; prompt: string; evidence: string }) {
  const [message, setMessage] = useState("");
  const text = useRef<HTMLTextAreaElement>(null);
  const fileName = name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const button = "inline-flex min-h-11 items-center rounded-lg border border-webb-accent/35 px-4 py-2 text-sm text-webb-accent hover:bg-webb-accent/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-webb-accent";
  function download(contents: string, suffix: string, type: string) {
    const url = URL.createObjectURL(new Blob([contents], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${fileName}-${suffix}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <section aria-labelledby="prompt-heading" className="rounded-2xl border border-webb-accent/25 bg-webb-ink p-5 sm:p-6">
      <p className="text-xs uppercase tracking-widest text-webb-accent">Your next image</p>
      <h2 id="prompt-heading" className="mt-2 text-2xl font-semibold">Image prompt</h2>
      <p className="mt-3 text-sm leading-relaxed text-webb-star/65">The complete generation brief, including catalog constraints, source links, unknowns and the requested viewpoint. Copy or download it to keep your own record. Detailed appearance remains hypothetical.</p>
      <div className="mt-5 flex flex-wrap gap-3">
        <button className={`${button} bg-webb-accent/10`} onClick={async () => {
          try { await navigator.clipboard.writeText(prompt); setMessage("Prompt copied."); }
          catch { text.current?.focus(); text.current?.select(); setMessage("Clipboard unavailable. The prompt is selected; copy it with Ctrl+C or ⌘C."); }
        }}>Copy image prompt</button>
        <button className={button} onClick={() => download(prompt, "prompt.txt", "text/plain;charset=utf-8")}>Download prompt</button>
        <button className={button} onClick={() => download(evidence, "evidence.json", "application/json")}>Download evidence</button>
      </div>
      <p role="status" className="mt-2 min-h-5 text-sm text-emerald-300">{message}</p>
      <label htmlFor="image-prompt" className="sr-only">Full image prompt for {name}</label>
      <textarea ref={text} id="image-prompt" readOnly value={prompt} spellCheck={false} className="mt-2 h-80 w-full resize-y rounded-xl border border-webb-star/15 bg-webb-deep p-4 font-mono text-xs leading-relaxed text-webb-star/75 focus:outline focus:outline-2 focus:outline-webb-accent" />
    </section>
  );
}
