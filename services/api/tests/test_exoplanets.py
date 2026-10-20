"""Scientific provenance, complete snapshots, and offline CLI replay."""
from __future__ import annotations

import csv
import hashlib
import json

import httpx
import pytest
from typer.testing import CliRunner

from app.cli.exoplanets import app
from app.clients.exoplanets import PARAMETERS, PLANNED, SPECTRA, fetch_catalog, validate_catalog
from app.services.exoplanets import build_portrait_brief, parameter, rank_catalog


def planet(name="Synthetic b", **overrides):
    row = {"pl_name": name, "hostname": "Synthetic", "pl_bmassprov": "Mass"}
    for field in PARAMETERS:
        row.update({field: 1, field + "err1": 0.1, field + "err2": -0.1, field + "lim": 0,
                    field + "_reflink": '<a href="https://example.org/paper">Test paper</a>'})
    row.update(dict.fromkeys(SPECTRA, 0))
    return row | overrides


def test_missing_data_not_imputed_and_planned_observations_not_counted():
    row = {"pl_name": "Empty b", **dict.fromkeys(PLANNED, 1000)}
    result = rank_catalog([row])[0]
    assert result["score"] == 0
    assert result["tier"] == "insufficient_evidence"
    assert len(result["unknown_spectrum_counts"]) == 3
    assert result["appearance_assessed"] is False


@pytest.mark.parametrize(("overrides", "basis"), [
    ({"pl_rade_reflink": "Calculated Value"}, "archive_calculated"),
    ({"pl_radelim": 1}, "limit_only"),
    ({"pl_rade": float("nan")}, "missing_or_invalid"),
    ({"pl_rade": -1}, "missing_or_invalid"),
    ({"pl_rade_reflink": None}, "unverified_reference"),
])
def test_radius_provenance_excludes_unsupported_credit(overrides, basis):
    result = parameter(planet(**overrides), "pl_rade")
    assert result["points"] == 0
    assert result["basis"] == basis


def test_minimum_mass_is_not_true_mass_and_missing_errors_reduce_credit():
    assert parameter(planet(pl_bmassprov="Msini"), "pl_bmasse")["points"] == 0
    assert parameter(planet(pl_radeerr1=None), "pl_rade")["points"] == 5
    assert parameter(planet(pl_radeerr2=0.1), "pl_rade")["points"] == 5


def test_archive_unquoted_reference_links_preserved():
    row = planet(pl_rade_reflink=(
        '<a refstr=STASSUN_ET_AL__2017 '
        'href=https://ui.adsabs.harvard.edu/abs/2017AJ....153..136S/abstract '
        'target=ref>Stassun et al. 2017</a>'
    ))
    result = parameter(row, "pl_rade")
    assert result["reference"] == "Stassun et al. 2017"
    assert result["source_urls"] == ["https://ui.adsabs.harvard.edu/abs/2017AJ....153..136S/abstract"]


def test_duplicate_spectra_cannot_increase_score_and_ties_share_rank():
    rows = [planet("Z b", pl_ntranspec=100), planet("A b", pl_ntranspec=1), planet("C b")]
    results = rank_catalog(rows)
    assert [(r["planet"], r["score"], r["rank"]) for r in results] == [
        ("A b", 80, 1), ("Z b", 80, 1), ("C b", 40, 3),
    ]


def test_complementary_spectra_are_triage_not_appearance_claims():
    result = rank_catalog([planet(pl_ntranspec=1, pl_nespec=1)])[0]
    assert result["score"] == 100
    assert result["appearance_assessed"] is False
    assert rank_catalog([planet(pl_ndispec=1)])[0]["score"] == 90


@pytest.mark.parametrize("rows", [[], {"error": "bad query"}, [{"pl_name": "x"}] * 2])
def test_invalid_catalog_rejected(rows):
    with pytest.raises(ValueError):
        validate_catalog(rows)


def test_fetch_complete_snapshot_and_source_hash():
    def handler(request):
        query = request.url.params["query"]
        return httpx.Response(200, json=[{"planet_count": 1}] if "count(*)" in query else [planet()])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows, manifest = fetch_catalog(client)
    assert len(rows) == manifest["archive_count_before"] == manifest["archive_count_after"] == 1
    assert len(manifest["source_response_sha256"]) == 64


@pytest.mark.parametrize("counts", [[2, 2], [1, 2]])
def test_truncated_or_changing_snapshot_rejected(counts):
    values = iter(counts)
    def handler(request):
        return httpx.Response(200, json=[{"planet_count": next(values)}]
                              if "count(*)" in request.url.params["query"] else [planet()])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, pytest.raises(ValueError):
        fetch_catalog(client)


def test_download_budget(monkeypatch):
    monkeypatch.setattr("app.clients.exoplanets.MAX_BYTES", 1)
    with (
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[planet()]))) as client,
        pytest.raises(ValueError, match="download budget"),
    ):
        fetch_catalog(client)


def test_brief_preserves_scale_unknowns_and_model_assumptions():
    brief = build_portrait_brief(planet())
    assert brief["geometry"]["angular_diameter_degrees"] == pytest.approx(1.8993, abs=0.001)
    assert brief["geometry"]["distance_from_center_km"] == 384400
    assert brief["parameters"][0]["source_urls"] == ["https://example.org/paper"]
    assert "not measured surface temperature" in brief["prompt"]
    assert "true color is unknown" in brief["prompt"]
    assert build_portrait_brief({"pl_name": "Empty b"})["geometry"]["angular_diameter_degrees"] is None
    assert build_portrait_brief(planet(pl_radelim=1))["status"] == "insufficient_for_scaled_portrait"


def test_appearance_evidence_requires_matching_planet_and_citations():
    evidence = {"planet": "Synthetic b", "claims": [
        {"kind": "model_inference", "text": "Blue hue is plausible.", "source_url": "https://example.org/paper"},
    ]}
    brief = build_portrait_brief(planet(), evidence)
    assert brief["status"] == "evidence_informed_illustration"
    assert "[model_inference] Blue hue is plausible" in brief["prompt"]
    assert not brief["appearance_evidence_automatically_verified"]
    with pytest.raises(ValueError, match="same planet"):
        build_portrait_brief(planet("Different b"), evidence)
    evidence["claims"][0].pop("source_url")
    with pytest.raises(ValueError, match="source URL"):
        build_portrait_brief(planet(), evidence)


@pytest.mark.parametrize("fov", [None, True, 0, 180, float("nan"), "invalid"])
def test_portrait_camera_rejects_invalid_fov(fov):
    evidence = {"planet": "Synthetic b", "rendering_horizontal_fov_degrees": fov,
                "claims": [{"kind": "rendering_assumption", "text": "Gray illustration"}]}
    with pytest.raises(ValueError, match="field of view"):
        build_portrait_brief(planet(), evidence)


def test_portrait_camera_labels_explicit_narrower_framing():
    evidence = {"planet": "Synthetic b", "rendering_horizontal_fov_degrees": 15,
                "claims": [{"kind": "rendering_assumption", "text": "Gray illustration"}]}
    brief = build_portrait_brief(planet(), evidence)
    assert brief["geometry"]["horizontal_fov_degrees"] == 15
    assert "15-degree horizontal field of view" in brief["prompt"]
    assert "atlas default of 45 degrees" in brief["prompt"]
    assert brief["geometry"]["distance_from_center_km"] == 384400


def test_offline_cli_exports_every_row_and_replay_is_deterministic(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps([planet("A b"), planet("Z b", pl_nespec=1)]))
    runner = CliRunner()
    outputs = [tmp_path / "one", tmp_path / "two"]
    for output in outputs:
        result = runner.invoke(app, ["rank", "--catalog", str(source), "--output-dir", str(output), "--top", "1"])
        assert result.exit_code == 0, result.output
        assert len(list(csv.DictReader((output / "ranking.csv").open()))) == 2
        manifest = json.loads((output / "manifest.json").read_text())
        assert "local_input_only" in manifest["coverage"]
        assert manifest["catalog_sha256"] == hashlib.sha256((output / "catalog.json").read_bytes()).hexdigest()
    assert (outputs[0] / "ranking.json").read_bytes() == (outputs[1] / "ranking.json").read_bytes()
    result = runner.invoke(app, ["prompt", "--catalog", str(source), "--planet", "z b", "--output-dir", str(tmp_path / "brief")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "brief" / "prompt.txt").is_file()
    assert runner.invoke(app, ["rank", "--catalog", str(source), "--output-dir", str(outputs[0])]).exit_code == 1


def test_cli_requires_one_source_and_missing_planet_does_not_create_output(tmp_path):
    runner = CliRunner()
    output = tmp_path / "output"
    assert runner.invoke(app, ["rank", "--output-dir", str(output)]).exit_code == 2
    source = tmp_path / "input.json"
    source.write_text(json.dumps([planet()]))
    result = runner.invoke(app, ["prompt", "--catalog", str(source), "--planet", "No b", "--output-dir", str(output)])
    assert result.exit_code == 1
    assert not output.exists()
