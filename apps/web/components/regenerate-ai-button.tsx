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

function reasonMessage(reason: string | null | undefined): string {
  if (reason === "local_ai_disabled") return "Local AI is disabled (set LOCAL_AI_ENABLE).";
  if (reason === "vision_disabled") return "Vision is disabled (set LOCAL_AI_VISION_ENABLE).";
  if (reason === "queue_unavailable") return "Worker queue unavailable (is Redis + the worker up?).";
  return "Could not queue a regeneration.";
}

export function RegenerateAiButton({
  productId,
  vision = false,
}: {
  productId: number;
  vision?: boolean;
}) {
  const router = useRouter();
  const [state, setState] = useState<ButtonState>("idle");
  const [message, setMessage] = useState("");

  const idleLabel = vision ? "Generate vision summary" : "Regenerate AI summary";
  const busyLabel = vision ? "Generating…" : "Regenerating…";

  async function onClick() {
    setState("loading");
    setMessage("");
    try {
      const url = `${API_BASE}/api/products/${productId}/ai-reports/regenerate${
        vision ? "?vision=true" : ""
      }`;
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
        {state === "loading" ? busyLabel : idleLabel}
      </button>
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
