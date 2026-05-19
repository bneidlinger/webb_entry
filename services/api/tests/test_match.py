"""Unit tests for watchlist matching — no DB needed beyond ORM objects in memory."""
from __future__ import annotations

import pytest

from app.models import DataProduct, Observation
from app.services.match import matches


def _obs(**over) -> Observation:
    defaults = dict(
        id=1,
        mast_obs_id="o1",
        program_id="1234",
        target_name="NGC 1234",
        instrument="NIRCAM",
        filters="F444W",
        ra=12.5,
        dec=-30.0,
    )
    defaults.update(over)
    return Observation(**defaults)


def _prod(**over) -> DataProduct:
    defaults = dict(
        id=1,
        observation_id=1,
        filename="jw01234_001_i2d.fits",
        product_type="i2d",
    )
    defaults.update(over)
    return DataProduct(**defaults)


def test_empty_criteria_does_not_match():
    matched, _ = matches(_prod(), _obs(), {})
    assert matched is False


def test_instrument_match():
    matched, reason = matches(_prod(), _obs(), {"instruments": ["nircam"]})
    assert matched is True
    assert "instrument=NIRCAM" in reason


def test_instrument_miss():
    matched, _ = matches(_prod(), _obs(instrument="MIRI"), {"instruments": ["NIRCAM"]})
    assert matched is False


def test_program_exact_match():
    matched, _ = matches(_prod(), _obs(), {"programs": ["1234"]})
    assert matched is True


def test_target_substring_case_insensitive():
    matched, reason = matches(_prod(), _obs(), {"targets": ["ngc"]})
    assert matched is True
    assert "target~ngc" in reason


def test_product_type_filters():
    matched, _ = matches(_prod(product_type="i2d"), _obs(), {"product_types": ["i2d", "x1d"]})
    assert matched is True

    matched, _ = matches(_prod(product_type="rate"), _obs(), {"product_types": ["i2d"]})
    assert matched is False


def test_cone_inside_radius():
    obs = _obs(ra=12.500001, dec=-30.0)
    matched, _ = matches(_prod(), obs, {"cone": {"ra": 12.5, "dec": -30.0, "radius_arcsec": 60}})
    assert matched is True


def test_cone_outside_radius():
    obs = _obs(ra=13.0, dec=-30.0)  # ~3600 arcsec away
    matched, _ = matches(_prod(), obs, {"cone": {"ra": 12.5, "dec": -30.0, "radius_arcsec": 60}})
    assert matched is False


def test_keyword_in_filename():
    matched, reason = matches(
        _prod(filename="jw01234_transit_spectrum_x1d.fits"),
        _obs(),
        {"keywords": ["transit"]},
    )
    assert matched is True
    assert "keyword~transit" in reason


def test_all_criteria_must_pass_when_set():
    # instrument matches but program doesn't → fail
    matched, _ = matches(
        _prod(),
        _obs(),
        {"instruments": ["NIRCAM"], "programs": ["9999"]},
    )
    assert matched is False


def test_unknown_keys_are_ignored():
    matched, _ = matches(
        _prod(), _obs(), {"instruments": ["NIRCAM"], "futureKey": ["whatever"]}
    )
    assert matched is True


@pytest.mark.parametrize(
    "criteria",
    [
        {"instruments": []},        # empty list — wildcard
        {"programs": [""]},          # blank string filtered
        {"targets": None},           # None ignored
    ],
)
def test_wildcards_alone_do_not_match(criteria):
    # No populated criterion → no reason → no match (we refuse to alert on everything).
    matched, _ = matches(_prod(), _obs(), criteria)
    assert matched is False
