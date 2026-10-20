"""Bounded, read-only NASA Exoplanet Archive TAP snapshots."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import httpx

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
MAX_BYTES = 32 * 1024**2
MAX_RECORDS = 100_000
PARAMETERS = {
    "pl_rade": ("Planet radius", "Earth radii", 10),
    "pl_bmasse": ("Planet mass", "Earth masses", 8),
    "pl_orbper": ("Orbital period", "days", 4),
    "pl_orbsmax": ("Orbital semi-major axis", "AU", 4),
    "pl_eqt": ("Equilibrium temperature estimate", "K", 4),
    "st_teff": ("Host effective temperature", "K", 6),
    "st_rad": ("Host radius", "Solar radii", 4),
}
SPECTRA = {
    "pl_ntranspec": "transmission",
    "pl_nespec": "eclipse",
    "pl_ndispec": "direct_imaging",
}
PLANNED = ("pl_nobs_jwst_tran", "pl_nobs_jwst_e", "pl_nobs_jwst_pc")
COLUMNS = [
    "pl_name", "hostname", "discoverymethod", "disc_facility", "disc_year", "pl_bmassprov",
    *SPECTRA, *PLANNED,
    *(field + suffix for field in PARAMETERS for suffix in ("", "err1", "err2", "lim", "_reflink")),
]
QUERY = f"select {','.join(COLUMNS)} from pscomppars order by pl_name"


def validate_catalog(rows: Any) -> list[dict[str, Any]]:
    """Reject TAP errors, empty/truncated-shaped payloads, and duplicate identities."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("Expected a non-empty JSON array of confirmed-planet records.")
    names: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each catalog record must be an object.")
        name = row.get("pl_name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Every catalog record must have a planet name (pl_name).")
        key = name.strip().casefold()
        if key in names:
            raise ValueError(f"Duplicate planet in snapshot: {name}")
        names.add(key)
    return rows


def _query(client: httpx.Client, query: str) -> bytes:
    with client.stream(
        "GET", TAP_URL,
        params={"query": query, "format": "json", "MAXREC": MAX_RECORDS},
    ) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=64 * 1024):
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError("Archive response exceeded the 32 MiB download budget.")
    return bytes(body)


def fetch_catalog(client: httpx.Client | None = None) -> tuple[list[dict], dict]:
    """Check counts on both sides of retrieval; never silently call a subset 'all'."""
    if client is None:
        with httpx.Client(timeout=60, follow_redirects=True) as owned:
            return fetch_catalog(owned)
    count_query = "select count(*) as planet_count from pscomppars"
    before = json.loads(_query(client, count_query))[0]["planet_count"]
    if not isinstance(before, int) or not 0 < before <= MAX_RECORDS:
        raise ValueError("Archive count is invalid or exceeds the snapshot record budget.")
    payload = _query(client, QUERY)
    rows = validate_catalog(json.loads(payload))
    after = json.loads(_query(client, count_query))[0]["planet_count"]
    if len(rows) != before or before != after:
        raise ValueError(
            f"Incomplete or changing archive snapshot: before={before}, "
            f"downloaded={len(rows)}, after={after}. Retry the snapshot."
        )
    return rows, {
        "source": TAP_URL,
        "table": "pscomppars",
        "query": QUERY,
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "archive_count_before": before,
        "archive_count_after": after,
        "record_count": len(rows),
        "source_response_sha256": hashlib.sha256(payload).hexdigest(),
        "coverage": "all_confirmed_in_archive_at_retrieval",
        "caveat": "Counts detect truncation, not changes to values during retrieval.",
    }
