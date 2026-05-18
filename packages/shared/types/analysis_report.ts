// Mirrors packages/shared/schemas/analysis_report.schema.json (plan §7).
// Keep in sync with the JSON Schema; consider auto-generating later via `json-schema-to-typescript`.

export type AnalysisMode = "local" | "cloud" | "hybrid" | "deterministic";
export type FactSource = "metadata" | "header" | "computed";
export type Confidence = "low" | "medium" | "high";
export type Severity = "info" | "warning" | "critical";

export interface MeasuredFact {
  name: string;
  value: string;
  source: FactSource;
}

export interface InterestingFeature {
  feature: string;
  evidence: string;
  confidence: Confidence;
}

export interface QualityFlag {
  flag: string;
  severity: Severity;
  details?: string;
}

export interface ModelNotes {
  model: string;
  prompt_version: string;
  created_at: string;
}

export interface AnalysisReport {
  product_id: string;
  analysis_run_id: string;
  analysis_mode: AnalysisMode;
  summary: string;
  measured_facts: MeasuredFact[];
  interesting_features: InterestingFeature[];
  quality_flags: QualityFlag[];
  recommended_next_steps: string[];
  human_validation_required: boolean;
  tags: string[];
  model_notes: ModelNotes;
}
