"""MAST client (astroquery.mast wrapper).

This is the only place in the app that knows about astroquery — everything
downstream sees plain dataclasses. That makes the ingest service trivial to
unit-test without touching the network.

Column reference:
  - Observations: https://mast.stsci.edu/api/v0/_o_data_summary.html
  - Products:     https://mast.stsci.edu/api/v0/_productsfields.html
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from astropy.table import Row, Table
from astropy.time import Time
from astroquery.mast import Observations

# JWST per-product filename suffixes we recognize. Subset of plan §4 — extend as needed.
# Examples: jw01234567001_02101_00001_nrca1_i2d.fits  →  product_type=i2d, ext=fits
#
# FITS-only on purpose: Phase 3/4 dispatch on product_type and would try to open
# a JPG/CSV as a FITS file. Non-FITS entries (JPG previews, PDF reports, CSV/ECSV
# catalogs) keep file_extension but get product_type=None.
_FITS_PRODUCT_SUFFIX_RE = re.compile(
    r"_(?P<ptype>uncal|rate|rateints|cal|calints|i2d|s2d|s3d|x1d|c1d|cat|segm|phot|preview)"
    r"\.fits(?:\.gz)?$",
    re.IGNORECASE,
)


@dataclass
class MastProduct:
    mast_product_id: str | None
    filename: str
    product_type: str | None
    file_extension: str | None
    file_size: int | None
    cloud_uri: str | None
    mast_download_uri: str | None
    calib_level: int | None
    description: str | None


@dataclass
class MastObservation:
    mast_obs_id: str
    program_id: str | None
    target_name: str | None
    instrument: str | None
    filters: str | None
    proposal_type: str | None
    ra: float | None
    dec: float | None
    observation_date: datetime | None
    public_release_date: datetime | None
    products: list[MastProduct] = field(default_factory=list)


# ---------------------------------------------------------------------------


def _cell(row: Row | dict, key: str) -> Any:
    """Read a cell from either an astropy Row or a plain dict, normalizing masked / NaN."""
    if isinstance(row, dict):
        value = row.get(key)
    else:
        try:
            value = row[key]
        except (KeyError, IndexError):
            return None
        # Astropy masked values
        if hasattr(value, "mask") and value.mask:
            return None
    if value is None:
        return None
    try:
        # numpy scalars → Python scalars
        if hasattr(value, "item"):
            value = value.item()
    except Exception:  # noqa: BLE001
        pass
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def _mjd_to_datetime(mjd: float | None) -> datetime | None:
    if mjd is None:
        return None
    try:
        return Time(mjd, format="mjd", scale="utc").to_datetime(timezone=UTC)
    except Exception:  # noqa: BLE001
        return None


def _classify_product(filename: str) -> tuple[str | None, str | None]:
    """Return (product_type, file_extension) inferred from a JWST product filename."""
    if not filename:
        return None, None
    m = _FITS_PRODUCT_SUFFIX_RE.search(filename)
    if m:
        return m.group("ptype").lower(), "fits"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else None
    return None, ext


# ---------------------------------------------------------------------------


class MastClient:
    """Thin wrapper around astroquery.mast.Observations.

    All public methods are blocking (astroquery is sync). Callers run them in a
    thread pool when invoked from async contexts.
    """

    OBS_COLLECTION = "JWST"

    def query_observations(
        self,
        *,
        instrument: str | None = None,
        program_id: str | None = None,
        target_name: str | None = None,
        limit: int = 100,
    ) -> Table:
        """Query JWST observations matching the given criteria.

        Returns the raw astropy Table — caller usually passes it straight into
        `get_products_for` so we keep the original row objects MAST needs for the
        product lookup.
        """
        criteria: dict[str, Any] = {"obs_collection": self.OBS_COLLECTION}
        if instrument:
            # MAST stores instrument_name as e.g. "NIRCAM/IMAGE"; wildcard prefix-match.
            criteria["instrument_name"] = f"{instrument.upper()}*"
        if program_id:
            criteria["proposal_id"] = program_id
        if target_name:
            criteria["target_name"] = target_name

        table = Observations.query_criteria(**criteria)
        if limit and len(table) > limit:
            table = table[:limit]
        return table

    def get_products_for(self, observations_table: Table) -> Table:
        """Fetch the per-observation product list for previously-queried observations."""
        if len(observations_table) == 0:
            return Table()
        return Observations.get_product_list(observations_table)

    # ------------------------------------------------------------------

    def fetch_jwst(
        self,
        *,
        instrument: str | None = None,
        program_id: str | None = None,
        target_name: str | None = None,
        limit: int = 100,
    ) -> list[MastObservation]:
        """Convenience: observations + products in one call, returned as dataclasses."""
        obs_table = self.query_observations(
            instrument=instrument,
            program_id=program_id,
            target_name=target_name,
            limit=limit,
        )
        if len(obs_table) == 0:
            return []

        prod_table = self.get_products_for(obs_table)
        return self.assemble(obs_table, prod_table)

    # ------------------------------------------------------------------
    # The conversion below is pure-Python on Tables — kept separate so unit
    # tests can drive it with synthetic Tables and skip the network entirely.

    @staticmethod
    def assemble(obs_table: Table, prod_table: Table) -> list[MastObservation]:
        products_by_obsid: dict[str, list[MastProduct]] = {}
        for row in prod_table:
            obs_key = str(_cell(row, "obsID") or _cell(row, "parent_obsid") or "")
            if not obs_key:
                continue
            filename = _cell(row, "productFilename") or ""
            if not filename:
                continue
            ptype, ext = _classify_product(filename)
            data_uri = _cell(row, "dataURI")
            is_s3 = isinstance(data_uri, str) and data_uri.startswith("s3://")
            cloud_uri = data_uri if is_s3 else None
            mast_uri = data_uri if (isinstance(data_uri, str) and not is_s3) else None
            products_by_obsid.setdefault(obs_key, []).append(
                MastProduct(
                    mast_product_id=str(_cell(row, "productID") or "") or None,
                    filename=filename,
                    product_type=ptype,
                    file_extension=ext,
                    file_size=_cell(row, "size"),
                    cloud_uri=cloud_uri,
                    mast_download_uri=mast_uri,
                    calib_level=_cell(row, "calib_level"),
                    description=_cell(row, "description"),
                )
            )

        observations: list[MastObservation] = []
        for row in obs_table:
            obs_key = str(_cell(row, "obsid") or "")
            if not obs_key:
                continue
            instrument_full = _cell(row, "instrument_name")
            if isinstance(instrument_full, str):
                instrument = instrument_full.split("/")[0]
            else:
                instrument = instrument_full
            observations.append(
                MastObservation(
                    mast_obs_id=obs_key,
                    program_id=str(_cell(row, "proposal_id") or "") or None,
                    target_name=_cell(row, "target_name"),
                    instrument=instrument,
                    filters=_cell(row, "filters"),
                    proposal_type=_cell(row, "proposal_type"),
                    ra=_cell(row, "s_ra"),
                    dec=_cell(row, "s_dec"),
                    observation_date=_mjd_to_datetime(_cell(row, "t_min")),
                    public_release_date=_mjd_to_datetime(_cell(row, "t_obs_release")),
                    products=products_by_obsid.get(obs_key, []),
                )
            )
        return observations
