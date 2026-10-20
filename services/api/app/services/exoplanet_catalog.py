"""Read-only, versioned catalog for the web UI; shares CLI scoring and prompts."""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from app.clients.exoplanets import validate_catalog
from app.services.exoplanets import LIMITATION, SCORE_VERSION, build_portrait_brief, rank_catalog

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "catalog_snapshots" / "exoplanets"
ARCHIVE_DOCS = "https://exoplanetarchive.ipac.caltech.edu/docs/pscp_about.html"


def planet_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "planet"
    return f"{slug}-{hashlib.sha256(name.encode()).hexdigest()[:10]}"


class CatalogSnapshot:
    def __init__(self, rows: list[dict], manifest: dict,
                 appearance: dict | list[dict] | None = None):
        validate_catalog(rows)
        self.rows = {planet_id(row["pl_name"]): row for row in rows}
        if len(self.rows) != len(rows):
            raise ValueError("Planet IDs must be unique.")
        self.appearances: dict[str, dict] = {}
        entries = appearance if isinstance(appearance, list) else [appearance] if appearance else []
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("planet"), str):
                raise ValueError("Appearance evidence must name a planet.")
            identity = planet_id(entry["planet"])
            target = self.rows.get(identity)
            if target is None:
                raise ValueError("Appearance evidence planet is absent from snapshot.")
            if identity in self.appearances:
                raise ValueError("Duplicate planet in appearance evidence.")
            build_portrait_brief(target, entry)
            self.appearances[identity] = entry
        self.ranked = rank_catalog(rows)
        ties = Counter(row["score"] for row in self.ranked)
        for row in self.ranked:
            row["id"] = planet_id(row["planet"])
            row["tied_count"] = ties[row["score"]]
            row["has_curated_appearance"] = row["id"] in self.appearances
        self.by_id = {row["id"]: row for row in self.ranked}
        # Explicit allowlist: public responses must never leak local source paths.
        self.metadata = {
            key: manifest.get(key) for key in (
                "retrieved_at_utc", "catalog_sha256", "coverage", "record_count",
            )
        } | {
            "source": ARCHIVE_DOCS,
            "score_version": SCORE_VERSION,
            "limitation": LIMITATION,
            "record_count": len(rows),
            "with_spectra": sum(r["tier"] == "spectral_followup" for r in self.ranked),
            "top_score": self.ranked[0]["score"],
            "top_tied_count": ties[self.ranked[0]["score"]],
            "facilities": sorted({r["discovery_facility"] for r in self.ranked
                                  if r["discovery_facility"]}),
        }

    def search(self, *, q: str = "", spectrum: str = "all", facility: str = "",
               min_score: float = 0, limit: int = 25, offset: int = 0) -> dict:
        needle = q.strip().casefold()
        results = [r for r in self.ranked if (
            (not needle or needle in r["planet"].casefold()
             or needle in str(r["host"] or "").casefold())
            and (not facility or r["discovery_facility"] == facility)
            and r["score"] >= min_score
            and (spectrum == "all"
                 or (spectrum == "any" and r["tier"] == "spectral_followup")
                 or (spectrum in r["spectra_counts"]
                     and (r["spectra_counts"][spectrum] or 0) > 0))
        )]
        return {"items": results[offset:offset + limit], "total": len(results),
                "limit": limit, "offset": offset, "snapshot": self.metadata}

    def detail(self, identity: str) -> dict | None:
        row = self.rows.get(identity)
        if row is None:
            return None
        evidence = self.appearances.get(identity)
        brief = build_portrait_brief(row, evidence)
        provenance = {
            "catalog_sha256": self.metadata["catalog_sha256"],
            "retrieved_at_utc": self.metadata["retrieved_at_utc"],
            "archive_url": "https://exoplanetarchive.ipac.caltech.edu/overview/"
                           + quote(row["pl_name"], safe=""),
        }
        brief.update(provenance)
        brief["prompt"] += (
            f"\n\nEvidence snapshot: {provenance['retrieved_at_utc']}. "
            f"Catalog SHA-256: {provenance['catalog_sha256']}.\n"
            f"NASA archive: {provenance['archive_url']}\n"
        )
        return {"ranking": self.by_id[identity], "brief": brief, "snapshot": self.metadata}


def load_snapshot(directory: Path) -> CatalogSnapshot:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    payload = gzip.decompress((directory / "catalog.json.gz").read_bytes())
    if hashlib.sha256(payload).hexdigest() != manifest.get("catalog_sha256"):
        raise ValueError("Catalog snapshot checksum mismatch.")
    rows = validate_catalog(json.loads(payload))
    if len(rows) != manifest.get("record_count"):
        raise ValueError("Catalog snapshot record count mismatch.")
    evidence_path = directory / "appearance.json"
    appearance = (
        json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else None
    )
    return CatalogSnapshot(rows, manifest, appearance)


@lru_cache(maxsize=1)
def get_catalog() -> CatalogSnapshot:
    return load_snapshot(SNAPSHOT_DIR)
