"""Drive MastClient.assemble() with synthetic astropy Tables — no network."""
from __future__ import annotations

from astropy.table import Table

from app.clients.mast import MastClient, _classify_product


def test_classify_product_known_suffixes():
    assert _classify_product("jw01234_001_i2d.fits") == ("i2d", "fits")
    assert _classify_product("jw01234_002_x1d.fits.gz") == ("x1d", "fits")
    assert _classify_product("preview.png") == (None, "png")
    assert _classify_product("") == (None, None)


def test_assemble_pairs_observations_with_their_products():
    obs_table = Table(
        rows=[
            ("1001", "NGC 1", "NIRCAM/IMAGE", "P-100", "F444W", None, 12.0, -1.0, None, None, None),
            ("1002", "NGC 2", "MIRI/IMAGE",   "P-100", "F1500W", None, 13.0, -2.0, None, None, None),
        ],
        names=(
            "obsid", "target_name", "instrument_name", "proposal_id", "filters",
            "proposal_type", "s_ra", "s_dec", "t_min", "t_obs_release", "calib_level",
        ),
    )
    prod_table = Table(
        rows=[
            ("1001", "jw01001_i2d.fits", "P-i2d", 2, 1024, "mast:JWST/p/jw01001_i2d.fits", "img"),
            ("1001", "jw01001_x1d.fits", "P-x1d", 2,  512, "mast:JWST/p/jw01001_x1d.fits", "spec"),
            ("1002", "jw01002_i2d.fits", "P-i2d2", 2, 2048, "s3://stpubdata/jwst/jw01002_i2d.fits", "img"),
        ],
        names=("obsID", "productFilename", "productID", "calib_level", "size", "dataURI", "description"),
    )

    observations = MastClient.assemble(obs_table, prod_table)

    assert {o.mast_obs_id for o in observations} == {"1001", "1002"}
    by_id = {o.mast_obs_id: o for o in observations}

    obs_1001 = by_id["1001"]
    assert obs_1001.instrument == "NIRCAM"  # split off /IMAGE suffix
    assert {p.filename for p in obs_1001.products} == {
        "jw01001_i2d.fits",
        "jw01001_x1d.fits",
    }
    types = {p.filename: p.product_type for p in obs_1001.products}
    assert types["jw01001_i2d.fits"] == "i2d"
    assert types["jw01001_x1d.fits"] == "x1d"

    obs_1002 = by_id["1002"]
    assert obs_1002.instrument == "MIRI"
    assert len(obs_1002.products) == 1
    s3_product = obs_1002.products[0]
    assert s3_product.cloud_uri == "s3://stpubdata/jwst/jw01002_i2d.fits"
    assert s3_product.mast_download_uri is None
