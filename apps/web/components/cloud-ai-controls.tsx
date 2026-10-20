"use client";

import { useEffect, useState } from "react";

import { RegenerateAiButton } from "@/components/regenerate-ai-button";
import type { CloudModelOption, CostEstimateResponse } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function CloudAiControls({ productId, models }: {
  productId: number;
  models: CloudModelOption[];
}) {
  const [selected, setSelected] = useState("configured");
  const [estimateError, setEstimateError] = useState(false);
  const [estimates, setEstimates] = useState<{
    model: string;
    cloud: CostEstimateResponse;
    cloud_review: CostEstimateResponse;
  } | null>(null);
  const choice = models.find((m) => m.id === selected);

  useEffect(() => {
    const controller = new AbortController();
    setEstimates(null);
    setEstimateError(false);
    if (!choice?.configured) return () => controller.abort();
    async function loadEstimates() {
      const results = await Promise.all(["cloud", "cloud_review"].map(async (mode) => {
        const params = new URLSearchParams({ mode });
        if (selected !== "configured") params.set("cloud_model", selected);
        const response = await fetch(
          `${API_BASE}/api/products/${productId}/ai-reports/cost-estimate?${params}`,
          { signal: controller.signal },
        );
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json() as CostEstimateResponse;
      }));
      if (!controller.signal.aborted) {
        setEstimates({ model: selected, cloud: results[0], cloud_review: results[1] });
      }
    }
    loadEstimates().catch(() => {
      if (!controller.signal.aborted) setEstimateError(true);
    });
    return () => controller.abort();
  }, [productId, selected, choice?.configured]);

  if (!models.length) return <p className="text-sm text-amber-300">Cloud model options unavailable.</p>;
  const current = estimates?.model === selected ? estimates : null;
  const disabled = !choice?.configured || !choice?.enabled;
  return (
    <div className="w-full space-y-3">
      <label className="block text-xs text-webb-star/70" htmlFor="cloud-model">
        Cloud model
      </label>
      <select
        id="cloud-model"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        className="w-full rounded border border-webb-star/20 bg-webb-deep px-3 py-2 text-sm text-webb-star"
      >
        {models.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
      </select>
      {!choice?.configured ? (
        <p className="text-xs text-amber-200">Connect {choice?.provider === "anthropic" ? "Anthropic" : "OpenAI / Azure"} API credentials to use this model.</p>
      ) : !choice.enabled ? (
        <p className="text-xs text-webb-star/60">Cloud generation is disabled in this installation.</p>
      ) : null}
      <div className="flex flex-wrap gap-3">
        <RegenerateAiButton
          key={`${selected}-cloud`} productId={productId} mode="cloud" cloudModel={selected}
          disabled={disabled || !current?.cloud.available}
          estimateUsd={current?.cloud.estimate_usd}
        />
        <RegenerateAiButton
          key={`${selected}-review`} productId={productId} mode="cloud_review" cloudModel={selected}
          disabled={disabled || !current?.cloud_review.available}
          estimateUsd={current?.cloud_review.estimate_usd}
        />
      </div>
      {choice?.configured && !current && (
        <p className="text-xs text-webb-star/50">{estimateError
          ? "Cost estimates could not be loaded. Refresh the page to try again."
          : "Waiting for cost estimates. Generation is available when estimates load."}</p>
      )}
      {current?.cloud.reason === "no_analysis" && <p className="text-xs text-webb-star/50">Generate deterministic measurements before requesting a summary.</p>}
      {current?.cloud_review.reason === "no_local_report" && <p className="text-xs text-webb-star/50">A cloud review needs a local summary to critique.</p>}
      {current?.cloud.available && <p className="text-xs text-webb-star/40">Estimated standard token cost, including the reasoning allowance. Billed usage may vary.</p>}
    </div>
  );
}
