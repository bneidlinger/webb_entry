"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type ButtonState = "idle" | "loading" | "done" | "error";

interface RegenerateResult {
  status: string;
  enqueued: boolean;
  reason?: string | null;
}

// Per-mode button labels. Any mode the API accepts has an entry here.
const LABELS: Record<string, { idle: string; busy: string }> = {
  local: { idle: "Regenerate AI summary", busy: "Regenerating…" },
  local_vision: { idle: "Generate vision summary", busy: "Generating…" },
  cloud: { idle: "Run cloud summary", busy: "Running…" },
  cloud_review: { idle: "Run cloud review", busy: "Reviewing…" },
};

function reasonMessage(reason: string | null | undefined): string {
  if (reason === "local_ai_disabled") return "Local AI is disabled (set LOCAL_AI_ENABLE).";
  if (reason === "vision_disabled") return "Vision is disabled (set LOCAL_AI_VISION_ENABLE).";
  if (reason === "cloud_ai_disabled") return "Cloud AI is disabled (set CLOUD_AI_ENABLE).";
  if (reason === "cloud_not_configured")
    return "Cloud AI isn't configured (set a provider API key).";
  if (reason === "queue_unavailable")
    return "Worker queue unavailable (is Redis + the worker up?).";
  return "Could not queue a regeneration.";
}

function formatUsd(v: number): string {
  return v < 0.01 ? `~$${v.toFixed(4)}` : `~$${v.toFixed(2)}`;
}

export function RegenerateAiButton({
  productId,
  mode = "local",
  estimateUsd = null,
}: {
  productId: number;
  mode?: string;
  estimateUsd?: number | null;
}) {
  const router = useRouter();
  const [state, setState] = useState<ButtonState>("idle");
  const [message, setMessage] = useState("");

  const labels = LABELS[mode] ?? LABELS.local;

  async function onClick() {
    setState("loading");
    setMessage("");
    try {
      const url = `${API_BASE}/api/products/${productId}/ai-reports/regenerate?mode=${mode}`;
      const res = await fetch(url, { method: "POST" });
      const body = (await res.json()) as RegenerateResult;
      if (body.enqueued) {
        setState("done");
        setMessage("Queued — the summary will update shortly.");
        router.refresh();
      } else {
        setState("error");
        setMessage(reasonMessage(body.reason));
      }
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={onClick}
        disabled={state === "loading"}
        className="rounded border border-webb-star/20 bg-webb-deep/60 px-3 py-1.5 text-xs text-webb-star/80 hover:border-webb-accent/40 hover:text-webb-star disabled:opacity-50"
      >
        {state === "loading" ? labels.busy : labels.idle}
      </button>
      {estimateUsd != null && state === "idle" && (
        <span className="text-xs text-webb-star/40">est. {formatUsd(estimateUsd)}</span>
      )}
      {message && (
        <span
          className={`text-xs ${state === "error" ? "text-amber-300/80" : "text-webb-star/50"}`}
        >
          {message}
        </span>
      )}
    </div>
  );
}
