"""Prompt-template tests (Phase 5).

We snapshot the *prompt* (dispatch, version, guardrails, that measurements flow
through) — never the model's output, which varies at T>0 (HANDOFF §7c.6).
"""
from __future__ import annotations

from app.services.ai.prompts import (
    get_prompt_for,
    image_summary_v1,
    spectrum_summary_v1,
)


def _image_payload() -> dict:
    return {
        "product": {"filename": "jw01234_i2d.fits", "product_type": "i2d"},
        "observation": {
            "target_name": "M82",
            "instrument": "NIRCAM",
            "program_id": "GO-1234",
            "filters": "F444W",
        },
        "measurements": {
            "kind": "image",
            "dimensions": [2048, 2048],
            "source_count": 42,
            "saturated_pixel_count": 120,
            "meta": {"crds_context": "jwst_1250.pmap", "calibration_version": "1.13.0"},
        },
    }


def _spectrum_payload() -> dict:
    return {
        "product": {"filename": "jw00777_x1d.fits", "product_type": "x1d"},
        "observation": {
            "target_name": "WASP-39b",
            "instrument": "NIRSPEC",
            "program_id": "GTO-2",
        },
        "measurements": {
            "kind": "spectrum",
            "peak_count": 3,
            "wavelength_unit": "um",
            "snr_proxy": 12.5,
            "meta": {"crds_context": "jwst_1300.pmap"},
        },
    }


def test_get_prompt_for_dispatch():
    assert get_prompt_for("image") is image_summary_v1
    assert get_prompt_for("spectrum") is spectrum_summary_v1
    assert get_prompt_for("Image") is image_summary_v1  # case-insensitive
    assert get_prompt_for("cube") is None
    assert get_prompt_for(None) is None


def test_prompt_modules_declare_version():
    assert image_summary_v1.PROMPT_VERSION == "v1"
    assert spectrum_summary_v1.PROMPT_VERSION == "v1"


def test_image_system_prompt_has_guardrails():
    sys = image_summary_v1.SYSTEM_PROMPT
    assert "human_validation_required" in sys
    assert "appears to" in sys.lower()
    assert "discover" in sys.lower()  # forbidden-phrase guardrail present
    assert "only" in sys.lower()


def test_image_user_prompt_includes_facts_and_metadata():
    prompt = image_summary_v1.build_user_prompt(_image_payload())
    for needle in ["M82", "NIRCAM", "GO-1234", "F444W", "42", "jwst_1250.pmap", "1.13.0"]:
        assert needle in prompt, needle


def test_spectrum_system_prompt_warns_against_line_id():
    sys = spectrum_summary_v1.SYSTEM_PROMPT
    assert "proxy" in sys.lower()  # S/N caveat present
    assert "line" in sys.lower()  # no-line-identification guardrail
    assert "human_validation_required" in sys


def test_spectrum_user_prompt_includes_features():
    prompt = spectrum_summary_v1.build_user_prompt(_spectrum_payload())
    for needle in ["WASP-39b", "NIRSPEC", "GTO-2", "um", "jwst_1300.pmap"]:
        assert needle in prompt, needle
