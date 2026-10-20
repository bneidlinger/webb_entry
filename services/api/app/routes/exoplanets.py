"""Browse and select targets from a reproducible, bundled archive snapshot."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.exoplanet_catalog import CatalogSnapshot, get_catalog

router = APIRouter(prefix="/api/exoplanets", tags=["exoplanets"])


def snapshot() -> CatalogSnapshot:
    try:
        return get_catalog()
    except (OSError, ValueError, EOFError) as exc:
        raise HTTPException(503, "Catalog snapshot unavailable or invalid.") from exc


@router.get("")
def list_exoplanets(
    q: str = Query("", max_length=120),
    spectrum: Literal["all", "any", "transmission", "eclipse", "direct_imaging"] = "all",
    facility: str = Query("", max_length=200),
    min_score: float = Query(0, ge=0, le=100),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    catalog: CatalogSnapshot = Depends(snapshot),
) -> dict:
    return catalog.search(q=q, spectrum=spectrum, facility=facility, min_score=min_score,
                          limit=limit, offset=offset)


@router.get("/{planet_id}")
def get_exoplanet(planet_id: str, catalog: CatalogSnapshot = Depends(snapshot)) -> dict:
    result = catalog.detail(planet_id)
    if result is None:
        raise HTTPException(404, "Planet not found in this snapshot.")
    return result
