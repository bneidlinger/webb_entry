"""Catalog browsing preserves ranks, provenance and conservative prompt behavior."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli.exoplanets import app as cli
from app.main import app
from app.routes.exoplanets import snapshot
from app.services.exoplanet_catalog import CatalogSnapshot, load_snapshot, planet_id
from tests.test_exoplanets import planet


@pytest.fixture
def catalog():
    return CatalogSnapshot([
        planet("A b", pl_nespec=1, disc_facility="TESS"),
        planet("B b", pl_nespec=1, disc_facility="Other"),
        planet("C b", pl_ntranspec=3, disc_facility="TESS"),
        {"pl_name": "Empty b", "hostname": "Unmeasured"},
    ], {"catalog_sha256": "a" * 64, "retrieved_at_utc": "2026-10-19T03:00:00Z",
        "record_count": 4, "source": "C:/private/catalog.json", "catalog_path": "private"})


@pytest.fixture
def catalog_client(client, catalog):
    app.dependency_overrides[snapshot] = lambda: catalog
    yield client
    app.dependency_overrides.pop(snapshot, None)


def test_pagination_and_filters_preserve_global_ties(catalog_client):
    first = catalog_client.get("/api/exoplanets", params={"limit": 1}).json()
    second = catalog_client.get("/api/exoplanets", params={"limit": 1, "offset": 1}).json()
    assert first["total"] == 4
    assert first["items"][0]["rank"] == second["items"][0]["rank"] == 1
    assert first["items"][0]["tied_count"] == 2
    filtered = catalog_client.get("/api/exoplanets", params={
        "facility": "TESS", "spectrum": "transmission", "min_score": 70,
    }).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["planet"] == "C b"
    assert filtered["items"][0]["rank"] == 3
    assert "private" not in json.dumps(first)
    assert first["snapshot"]["with_spectra"] == 3


def test_search_empty_unknown_and_bounds(catalog_client):
    for query in (" a B ", "synthetic"):
        assert catalog_client.get("/api/exoplanets", params={"q": query}).json()["total"] > 0
    assert catalog_client.get("/api/exoplanets?q=unmeasured").json()["total"] == 1
    assert catalog_client.get("/api/exoplanets?q=absent").json()["items"] == []
    assert catalog_client.get("/api/exoplanets?offset=999").json()["items"] == []
    assert catalog_client.get("/api/exoplanets/not-a-planet").status_code == 404
    for query in ("limit=101", "offset=-1", "spectrum=invalid", "min_score=101", "min_score=nan"):
        assert catalog_client.get(f"/api/exoplanets?{query}").status_code == 422


def test_detail_cites_parameters_retains_errors_and_flags_unscalable(catalog_client):
    detail = catalog_client.get(f"/api/exoplanets/{planet_id('A b')}").json()
    brief = detail["brief"]
    assert brief["planet"] == "A b"
    assert brief["catalog_sha256"] == "a" * 64
    assert "https://example.org/paper" in brief["prompt"]
    assert "neutral-gray" in brief["prompt"]
    assert brief["parameters"][0]["uncertainty_minus"] == -0.1
    empty = catalog_client.get(f"/api/exoplanets/{planet_id('Empty b')}").json()["brief"]
    assert empty["status"] == "insufficient_for_scaled_portrait"
    assert empty["geometry"]["angular_diameter_degrees"] is None
    assert "do not generate a physically scaled portrait" in empty["prompt"]


def test_curated_appearance_only_applies_to_named_planet():
    evidence = {"planet": "A b", "claims": [{"kind": "model_inference", "text": "Blue",
                                            "source_url": "https://example.org/blue"}]}
    catalog = CatalogSnapshot([planet("A b"), planet("B b")], {}, evidence)
    assert catalog.detail(planet_id("A b"))["brief"]["appearance_evidence"] == evidence
    assert catalog.detail(planet_id("B b"))["brief"]["appearance_evidence"] is None
    assert catalog.by_id[planet_id("A b")]["has_curated_appearance"]
    assert planet_id("A b") != planet_id("A-b")
    assert "/" not in planet_id("../../ b")


def test_multiple_appearance_examples_keep_identities_and_ranking_separate():
    def evidence(name, color):
        return {"planet": name, "claims": [{"kind": "model_inference", "text": color,
                                           "source_url": "https://example.org/paper"}]}
    rows = [planet("A b"), planet("B b"), planet("C b")]
    examples = [evidence("A b", "Blue"), evidence("B b", "White")]
    plain = CatalogSnapshot(rows, {})
    enriched = CatalogSnapshot(rows, {}, examples)
    assert [(r["score"], r["rank"]) for r in plain.ranked] == [
        (r["score"], r["rank"]) for r in enriched.ranked
    ]
    for item in examples:
        brief = enriched.detail(planet_id(item["planet"]))["brief"]
        assert brief["appearance_evidence"] == item
    assert enriched.detail(planet_id("C b"))["brief"]["appearance_evidence"] is None
    with pytest.raises(ValueError, match="Duplicate"):
        CatalogSnapshot(rows, {}, [examples[0], examples[0]])
    with pytest.raises(ValueError, match="absent"):
        CatalogSnapshot(rows, {}, [evidence("Absent b", "Gray")])


def test_saved_second_portrait_uses_current_sourced_catalog_brief():
    repo = Path(__file__).resolve().parents[3]
    catalog = load_snapshot(repo / "services/api/app/catalog_snapshots/exoplanets")
    saved = json.loads((repo / "apps/web/public/portraits/ltt-9779-b/evidence.json").read_text(encoding="utf-8"))
    actual = catalog.detail(planet_id("LTT 9779 b"))
    assert actual["brief"] == saved["brief"]
    assert actual["ranking"]["rank"] == 1 and actual["ranking"]["tied_count"] == 79
    assert actual["brief"]["geometry"]["horizontal_fov_degrees"] == 15
    assert "113 ppm" in actual["brief"]["prompt"]
    assert sum(row["has_curated_appearance"] for row in catalog.ranked) == 2
    assert catalog.detail(planet_id("HD 189733 b"))["brief"]["geometry"]["horizontal_fov_degrees"] == 45
    assert saved["image_provenance"]["geometry_validated"] is False


def test_prompt_preserves_small_uncertainties_and_catalog_precision():
    catalog = CatalogSnapshot([planet("A b", pl_orbper=4.0552941, pl_orbpererr1=0.0000001,
                                      pl_orbpererr2=-0.0000001)], {})
    prompt = catalog.detail(planet_id("A b"))["brief"]["prompt"]
    assert "4.0552941 days" in prompt
    assert "+1e-07/(-1e-07)" in prompt


def test_bundle_round_trip_checksum_validation_and_no_overwrite(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    payload = json.dumps([planet()]).encode()
    (source / "catalog.json").write_bytes(payload)
    manifest = {"catalog_sha256": hashlib.sha256(payload).hexdigest(), "record_count": 1,
                "source": "C:/private/source", "retrieved_at_utc": "2026-10-19T03:00:00Z"}
    (source / "manifest.json").write_text(json.dumps(manifest))
    output = tmp_path / "bundle"
    args = ["bundle", "--snapshot-dir", str(source), "--output-dir", str(output)]
    runner = CliRunner()
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert load_snapshot(output).search()["total"] == 1
    assert "private" not in (output / "manifest.json").read_text()
    assert runner.invoke(cli, args).exit_code == 1
    (output / "catalog.json.gz").write_bytes(gzip.compress(b"[]"))
    with pytest.raises(ValueError, match="checksum"):
        load_snapshot(output)
    (source / "catalog.json").write_bytes(b"[]")
    result = runner.invoke(cli, [*args[:-1], str(tmp_path / "bad")])
    assert result.exit_code == 1
    assert not (tmp_path / "bad").exists()


def test_unavailable_snapshot_returns_503(client, monkeypatch):
    def unavailable():
        raise ValueError("private filesystem detail")
    monkeypatch.setattr("app.routes.exoplanets.get_catalog", unavailable)
    response = client.get("/api/exoplanets")
    assert response.status_code == 503
    assert "private" not in response.text
