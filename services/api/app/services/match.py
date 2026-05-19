"""Watchlist matching: does a (product, observation) pair satisfy this watchlist?

Criteria schema (free-form JSON on `Watchlist.criteria_json`):

    {
      "instruments":    ["NIRCAM", "MIRI"],          # OR, case-insensitive exact
      "programs":       ["1234", "2731"],             # OR, exact string match
      "targets":        ["NGC 1234", "M82"],          # OR, substring (case-insensitive)
      "product_types":  ["i2d", "x1d"],               # OR, lowercase exact
      "cone":           {"ra": 12.34, "dec": -56.78,  # AND across the cone
                         "radius_arcsec": 60},
      "keywords":       ["transit", "spectrum"]       # OR, substring on filename+target
    }

Top-level keys are AND-ed: an empty / missing key is a free pass; a populated
key must match. Unknown keys are ignored for forward-compat.

Returns `(matched, reason)`. The reason string is human-readable and stored on
`Alert.reason` so the UI can show "matched instrument=NIRCAM, target~NGC 1234".
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from app.models import DataProduct, Observation


def _norm_list(value: Any) -> list[str]:
    """Coerce a criterion value into a list of non-empty strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Iterable):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _angular_distance_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Great-circle distance in arcseconds (haversine on the celestial sphere)."""
    ra1_r, dec1_r, ra2_r, dec2_r = (math.radians(x) for x in (ra1, dec1, ra2, dec2))
    d_dec = dec2_r - dec1_r
    d_ra = ra2_r - ra1_r
    a = (
        math.sin(d_dec / 2) ** 2
        + math.cos(dec1_r) * math.cos(dec2_r) * math.sin(d_ra / 2) ** 2
    )
    return 2 * math.asin(min(1.0, math.sqrt(a))) * (180 / math.pi) * 3600


def matches(
    product: DataProduct,
    observation: Observation,
    criteria: dict[str, Any],
) -> tuple[bool, str]:
    """Evaluate `criteria` against `(product, observation)`.

    Empty / missing criteria fields are treated as wildcards. A criteria dict
    with no populated fields matches everything — caller is responsible for
    deciding whether that's desirable (watchlist UI should require ≥1 field).
    """
    if not criteria:
        return False, ""

    reasons: list[str] = []

    # instruments: case-insensitive exact match on the observation's instrument
    instruments = [s.upper() for s in _norm_list(criteria.get("instruments"))]
    if instruments:
        if not observation.instrument or observation.instrument.upper() not in instruments:
            return False, ""
        reasons.append(f"instrument={observation.instrument}")

    # programs: exact string match on program_id
    programs = _norm_list(criteria.get("programs"))
    if programs:
        if not observation.program_id or observation.program_id not in programs:
            return False, ""
        reasons.append(f"program={observation.program_id}")

    # targets: substring (case-insensitive)
    targets = [s.lower() for s in _norm_list(criteria.get("targets"))]
    if targets:
        target_name = (observation.target_name or "").lower()
        hit = next((t for t in targets if t in target_name), None)
        if hit is None:
            return False, ""
        reasons.append(f"target~{hit}")

    # product_types: case-insensitive exact (we store lowercase)
    product_types = [s.lower() for s in _norm_list(criteria.get("product_types"))]
    if product_types:
        if not product.product_type or product.product_type.lower() not in product_types:
            return False, ""
        reasons.append(f"type={product.product_type}")

    # cone: AND — requires ra, dec, radius_arcsec all present and within radius
    cone = criteria.get("cone")
    if isinstance(cone, dict):
        try:
            ra = float(cone["ra"])
            dec = float(cone["dec"])
            radius = float(cone["radius_arcsec"])
        except (KeyError, TypeError, ValueError):
            return False, ""
        if observation.ra is None or observation.dec is None:
            return False, ""
        dist = _angular_distance_arcsec(observation.ra, observation.dec, ra, dec)
        if dist > radius:
            return False, ""
        reasons.append(f"cone={dist:.1f}\"≤{radius:.0f}\"")

    # keywords: substring on filename OR target_name
    keywords = [s.lower() for s in _norm_list(criteria.get("keywords"))]
    if keywords:
        haystack = " ".join(
            filter(None, [product.filename, observation.target_name])
        ).lower()
        hit = next((k for k in keywords if k in haystack), None)
        if hit is None:
            return False, ""
        reasons.append(f"keyword~{hit}")

    if not reasons:
        # All criteria were empty — refuse to match rather than alerting on everything.
        return False, ""

    return True, ", ".join(reasons)
