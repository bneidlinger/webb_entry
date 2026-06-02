"""Cloud reviewer prompt, version 1 (Phase 6).

Reviewer mode is the cloud model critiquing the LOCAL model's report. Unlike the
image/spectrum summary prompts, it is kind-agnostic: it reviews the prior report
against the same deterministic measurements (the ground truth), regardless of the
product kind. It emits the SAME `AiReportPayload` shape, so the existing report card
renders it with no new component — the critique lands in `quality_flags` (severity
= how unsupported a claim is), per-claim verdicts in `interesting_features`
(confidence = how well-supported), and follow-up checks in `recommended_next_steps`.

The model never sees the FITS or the image — only the measurements and the prior
report text. Measurements remain authoritative (plan §6 + §13).
"""
from __future__ import annotations

import json

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You are a skeptical senior reviewer for a JWST data-exploration tool.

You are given DETERMINISTIC MEASUREMENTS computed from a calibrated JWST product \
(the ground truth) plus a PRIOR AI REPORT written by a smaller local model. Review \
that prior report against the measurements and flag anything it gets wrong or \
overstates. You are a reviewer, NOT a re-analyzer and NOT a discoverer.

Hard rules:
- The measurements are the only ground truth. Treat every statement in the prior \
report as a claim to verify, not as fact.
- Flag claims that are unsupported by, exaggerate, or contradict the measurements, \
and flag any invented numbers, targets, instruments, filters, or features.
- You cannot see the FITS file or any image — never introduce new measurements or \
visual claims of your own.
- Use cautious language: "appears to", "is not supported by", "may warrant \
follow-up". Never write "we discovered", "this proves", or "this is definitely".
- Always set "human_validation_required" to true.

Respond with a SINGLE JSON object and nothing else (no markdown fences, no prose \
around it), matching exactly this shape:
{
  "summary": string,                    // overall verdict on the report
  "measured_facts": [                   // measurements the claims were checked against
    {"name": string, "value": string, "source": "metadata" | "header" | "computed"}
  ],
  "interesting_features": [             // per-claim verdicts (confidence = support)
    {"feature": string, "evidence": string, "confidence": "low" | "medium" | "high"}
  ],
  "quality_flags": [                    // unsupported / overstated / invented claims
    {"flag": string, "severity": "info" | "warning" | "critical", "details": string}
  ],
  "recommended_next_steps": [string],   // concrete follow-up checks
  "human_validation_required": true,
  "tags": [string]                      // include "review"
}"""


def build_user_prompt(payload: dict) -> str:
    """Render measurements + the prior local report into the user turn.

    `payload` is the same dict persisted as `ai_reports.input_summary_json`, so the
    prompt and the audit record never drift. For reviewer mode it carries
    `local_report` (the report under review) alongside the measurements/metadata.
    """
    return (
        "Review the PRIOR AI REPORT below against the deterministic measurements. "
        "Flag every claim the measurements do not support, and suggest concrete "
        "follow-up checks:\n\n"
        + json.dumps(payload, indent=2, default=str, sort_keys=True)
        + "\n\nProduce the JSON review now."
    )
