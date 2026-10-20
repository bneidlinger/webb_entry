"""Explainable catalog triage and conservative portrait briefs; no AI calls."""
from __future__ import annotations

import html
import math
import re
from typing import Any
from urllib.parse import urlsplit

from app.clients.exoplanets import PARAMETERS, PLANNED, SPECTRA, validate_catalog

SCORE_VERSION = "catalog-readiness-v1"
PROMPT_VERSION = "planet-portrait-v3"
LIMITATION = (
    "Catalog readiness proxy, not image accuracy or probability of discovery. "
    "Spectra contents, signal quality, phase curves, and visible color have not been assessed. "
    "Composite parameters may mix publications and include calculated estimates."
)


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def count(value: Any) -> int | None:
    result = number(value)
    if result is None or result < 0 or not result.is_integer():
        return None
    return int(result)


def parameter(row: dict, field: str) -> dict:
    label, unit, weight = PARAMETERS[field]
    value = number(row.get(field))
    reference = str(row.get(field + "_reflink") or "")
    ref_text = html.unescape(re.sub(r"<[^>]*>", "", reference)).strip()
    links = re.findall(
        r'''href\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s>]+))''', reference, flags=re.I,
    )
    urls = [next(part for part in link if part) for link in links]
    urls = [url for url in urls if urlsplit(url).scheme in {"https", "http"}]
    upper, lower = number(row.get(field + "err1")), number(row.get(field + "err2"))
    limit = number(row.get(field + "lim"))
    quality = 0.0
    if value is None or value <= 0:
        basis = "missing_or_invalid"
    elif limit is not None and limit != 0:
        basis = "limit_only"
    elif "calculated" in ref_text.casefold():
        basis = "archive_calculated"
    elif field == "pl_bmasse" and str(row.get("pl_bmassprov", "")).casefold() != "mass":
        basis = "minimum_or_model_mass"
    elif not ref_text:
        basis = "unverified_reference"
    elif upper is None or lower is None or upper <= 0 or lower >= 0:
        basis = "reported_without_two_sided_uncertainty"
        quality = 0.5
    else:
        basis = "reported_with_uncertainty"
        quality = 1.0
    return {
        "field": field, "label": label, "value": value, "unit": unit,
        "uncertainty_plus": upper, "uncertainty_minus": lower, "limit_flag": limit,
        "reference": ref_text, "source_urls": [html.unescape(url) for url in urls],
        "basis": basis, "points": weight * quality, "max_points": weight,
    }


def rank_catalog(rows: list[dict]) -> list[dict]:
    validate_catalog(rows)
    ranked = []
    for row in rows:
        params = [parameter(row, field) for field in PARAMETERS]
        spectra = {kind: count(row.get(field)) for field, kind in SPECTRA.items()}
        kinds = [kind for kind, n in spectra.items() if n is not None and n > 0]
        # Presence only: repeated bins/reductions/papers cannot increase the score.
        parts = {
            "bulk_parameters": sum(p["points"] for p in params),
            "published_spectral_data": 40 if kinds else 0,
            "complementary_spectrum_types": 10 if len(kinds) >= 2 else 0,
            "thermal_spectrum_available": (
                10 if "eclipse" in kinds or "direct_imaging" in kinds else 0
            ),
        }
        ranked.append({
            "planet": row["pl_name"], "host": row.get("hostname"),
            "discovery_facility": row.get("disc_facility"),
            "score": sum(parts.values()), "components": parts,
            "score_version": SCORE_VERSION,
            "tier": "spectral_followup" if kinds else (
                "bulk_only" if any(p["points"] for p in params) else "insufficient_evidence"
            ),
            "spectra_counts": spectra,
            "jwst_approved_observation_counts": {f: count(row.get(f)) for f in PLANNED},
            "uncredited_parameters": [p["field"] for p in params if p["points"] == 0],
            "parameter_assessment": {
                p["field"]: {k: p[k] for k in ("basis", "points", "max_points")}
                for p in params
            },
            "unknown_spectrum_counts": [kind for kind, n in spectra.items() if n is None],
            "appearance_assessed": False,
        })
    ranked.sort(key=lambda r: (-r["score"], r["planet"].casefold()))
    # Shared ranks communicate ties; alphabetical order is only a display convention.
    previous = None
    rank = 0
    for position, row in enumerate(ranked, 1):
        if row["score"] != previous:
            rank = position
        row["rank"] = rank
        previous = row["score"]
    return ranked


def _appearance_claims(row: dict, evidence: dict | None) -> list[dict]:
    if evidence is None:
        return []
    if not isinstance(evidence, dict) or evidence.get("planet") != row["pl_name"]:
        raise ValueError("Appearance evidence must name the same planet as the catalog record.")
    claims = evidence.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("Appearance evidence requires a non-empty claims list.")
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("kind") not in {
            "reported_constraint", "model_inference", "rendering_assumption",
        }:
            raise ValueError("Each appearance claim needs a supported evidence kind.")
        if not isinstance(claim.get("text"), str) or not claim["text"].strip():
            raise ValueError("Each appearance claim needs non-empty text.")
        if claim["kind"] != "rendering_assumption":
            url = urlsplit(str(claim.get("source_url", "")))
            if url.scheme != "https" or not url.netloc:
                raise ValueError("Scientific appearance claims require an HTTPS source URL.")
    return claims


def build_portrait_brief(row: dict, appearance_evidence: dict | None = None) -> dict:
    claims = _appearance_claims(row, appearance_evidence)
    fov = number((appearance_evidence or {}).get("rendering_horizontal_fov_degrees", 45))
    if fov is None or not 1 <= fov < 180:
        raise ValueError("Rendering horizontal field of view must be between 1 and 180 degrees.")
    params = [parameter(row, field) for field in PARAMETERS]
    radius = params[0]
    scalable = (
        radius["value"] is not None and radius["value"] > 0 and radius["basis"] != "limit_only"
    )
    distance = 384_400
    radius_km = radius["value"] * 6371 if scalable else None
    scalable = scalable and radius_km < distance
    angular = math.degrees(2 * math.asin(radius_km / distance)) if scalable else None
    assumptions = [
        "Virtual camera 384400 km from planet center; this does not imply a moon or stable orbit.",
        f"Phase angle 60 degrees; {fov:g}-degree horizontal field of view; square frame.",
        "Visible-light illustration with neutral display white balance; exact RGB is not measured.",
        "Use a neutral-gray disk unless the supplied appearance evidence supports a different hue.",
        "Any zoom/crop must be labeled; physical viewing distance alone does not set image scale.",
    ]
    if fov != 45:
        assumptions.append(
            f"Explicit framing choice: {fov:g}-degree field of view replaces the atlas default "
            "of 45 degrees; label this narrower/wider framing and retain the viewing distance."
        )
    unknowns = [
        "Without additional evidence, true color is unknown; "
        "exact RGB and cloud geography remain unknown.",
        "Surface type, continents, oceans, terrain, rings, moons and local weather patterns.",
        "Rotation, obliquity and spatial brightness maps unless independently sourced later.",
        "Equilibrium temperature is a model estimate, not measured surface temperature.",
        "Spectral counts do not establish detection of an atmosphere or any molecule.",
    ]
    facts = []
    for p in params:
        if p["basis"] != "missing_or_invalid":
            facts.append(
                f"{p['label']}: {p['value']} {p['unit']}; {p['basis']}; "
                f"uncertainties +{p['uncertainty_plus']}/({p['uncertainty_minus']}); "
                f"limit flag {p['limit_flag']}. "
                f"Reference: {p['reference'] or 'not supplied'}; "
                f"sources: {', '.join(p['source_urls']) or 'no source URL supplied'}."
            )
    instruction = (
        f"Create an explicitly labeled, hypothetical illustration of {row['pl_name']}. "
        "This is a catalog-based scenario, not a reconstructed photograph or physical simulation. "
        "The following numerical constraints are catalog estimates; calculated values, limits, "
        "and minimum masses are not independent measurements.\n\n"
        + "\n".join(facts)
        + "\n\nRendering assumptions:\n" + "\n".join(assumptions)
        + (f"\nPlanet angular diameter: {angular:.4f} degrees in the stated frame." if scalable else
           "\nRadius unavailable or unsuitable: do not generate a physically scaled portrait.")
        + "\n\nUnknowns:\n" + "\n".join(unknowns)
        + ("\n\nSupplied appearance evidence (not independently verified by this tool):\n"
           + "\n".join(f"[{c['kind']}] {c['text']} Source: {c.get('source_url', 'scenario choice')}"
                       for c in claims) if claims else "")
        + "\n\nDo not invent detailed features as observations. Do not infer visible colors "
        "from infrared observations or a surface from equilibrium temperature. "
        "Use no rings, moons, cities, vegetation, continents, storms, or ocean textures "
        "without separately supplied evidence or an explicitly labeled scenario. "
        "Specific texture, cloud shapes, and weather must remain labeled rendering assumptions. "
        "Caption: Hypothetical illustration; detailed appearance is not observed."
    )
    return {
        "planet": row["pl_name"], "prompt_version": PROMPT_VERSION,
        "status": (
            "evidence_informed_illustration" if scalable and any(
                c["kind"] != "rendering_assumption" for c in claims
            ) else "bulk_illustration_only" if scalable else "insufficient_for_scaled_portrait"
        ),
        "limitation": LIMITATION, "parameters": params,
        "mass_provenance": row.get("pl_bmassprov"),
        "appearance_evidence": appearance_evidence,
        "appearance_evidence_automatically_verified": False,
        "geometry": {
            "distance_from_center_km": distance, "phase_angle_degrees": 60,
            "horizontal_fov_degrees": fov, "angular_diameter_degrees": angular,
            "radius_conversion_km_per_earth_radius": 6371,
            "radius_basis": radius["basis"],
        },
        "assumptions": assumptions, "unknowns": unknowns,
        "spectra_counts": {kind: count(row.get(f)) for f, kind in SPECTRA.items()},
        "prompt": instruction,
    }
