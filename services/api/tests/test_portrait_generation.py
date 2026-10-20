from __future__ import annotations

import base64
import io
import json
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from openai import APIStatusError, APITimeoutError
from PIL import Image
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.main import app
from app.models import PlanetPortrait
from app.routes import planet_portraits as routes
from app.routes.exoplanets import snapshot
from app.services.exoplanet_catalog import CatalogSnapshot, planet_id
from app.services.portrait_generation import (
    config_error,
    digest,
    evidence_groups,
    run_generation,
)
from app.services.storage import LocalFilesystemStorage
from tests.test_exoplanet_catalog import planet


@pytest.fixture
def generation(client, session, tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None, openai_api_key="test-not-a-real-key", portrait_generation_enable=True
    )
    catalog = CatalogSnapshot(
        [planet("Test b"), planet("Other b"), {"pl_name": "Empty b"}], {"catalog_sha256": "a" * 64}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[snapshot] = lambda: catalog
    storage = LocalFilesystemStorage(tmp_path, "http://localhost:8000")
    monkeypatch.setattr(routes, "get_preview_storage", lambda _: storage)
    captured = []
    queued = []
    output = io.BytesIO()
    Image.new("RGB", (1024, 1024), "gray").save(output, format="PNG")
    data = output.getvalue()

    def generate(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    b64_json=base64.b64encode(data).decode(), revised_prompt="Provider revision"
                )
            ],
            _request_id="provider-test",
            usage=None,
        )

    provider = SimpleNamespace(images=SimpleNamespace(generate=generate))

    @contextmanager
    def scope():
        with Session(session.bind, expire_on_commit=False) as scoped:
            yield scoped
            scoped.commit()

    def run(identity, saved_settings):
        run_generation(identity, saved_settings, scope=scope, storage=storage, client=provider)

    monkeypatch.setattr(routes, "run_generation", lambda identity, _: queued.append(identity))
    return SimpleNamespace(
        client=client,
        session=session,
        settings=settings,
        catalog=catalog,
        storage=storage,
        provider=provider,
        captured=captured,
        queued=queued,
        run=run,
        data=data,
    )


def submit(g, *, name="Test b", identity=None, hash_value=None, **kwargs):
    detail = g.catalog.detail(planet_id(name))
    return g.client.post(
        "/api/planet-portraits",
        json={
            "request_id": identity or str(uuid4()),
            "planet_id": planet_id(name),
            "prompt_sha256": hash_value or digest(detail["brief"]["prompt"]),
        },
        headers={"X-WebbWatch-Action": "generate-portrait", **kwargs},
    )


def test_full_generation_persists_exact_prompt_image_and_evidence(generation):
    g = generation
    response = submit(g)
    assert response.status_code == 202
    identity = response.json()["id"]
    assert response.json()["status"] == "queued"
    before = g.client.get(f"/api/planet-portraits/{identity}").json()
    g.run(identity, g.settings)
    g.session.expire_all()
    result = g.client.get(f"/api/planet-portraits/{identity}").json()
    assert result["status"] == "completed"
    assert result["prompt"] == g.captured[0]["prompt"] == before["prompt"]
    assert g.captured[0]["model"] == before["model"]
    assert result["evidence"] == before["evidence"]
    assert [group["id"] for group in result["evidence"]["groups"]] == [
        "measured",
        "inferred",
        "illustrative",
    ]
    assert result["output"]["revised_prompt"] == "Provider revision"
    assert g.client.get(result["image_url"]).content == g.data
    assert (
        "attachment"
        in g.client.get(result["image_url"] + "?download=true").headers["content-disposition"]
    )
    assert g.client.get(result["prompt_url"]).text == result["prompt"]
    evidence = g.client.get(result["evidence_url"]).json()
    assert evidence["geometry_validated"] is False
    assert evidence["generation"]["prompt_sha256"] == digest(result["prompt"])
    assert "test-not-a-real-key" not in json.dumps(evidence)
    stored = json.loads(g.storage.read(f"planet-portraits/{identity}/evidence.json"))
    assert stored == evidence
    # Updating the live catalog must not rewrite a historical brief or its source categories.
    g.catalog.rows[planet_id("Test b")]["pl_rade"] = 999
    assert (
        g.client.get(f"/api/planet-portraits/{identity}").json()["evidence"] == before["evidence"]
    )


def test_idempotent_submission_and_worker_claim_prevent_duplicate_calls(generation):
    g = generation
    identity = str(uuid4())
    assert submit(g, identity=identity).status_code == 202
    assert submit(g, identity=identity).status_code == 202
    assert g.queued == [identity]
    g.run(identity, g.settings)
    g.run(identity, g.settings)
    g.session.expire_all()
    assert submit(g, identity=identity).json()["status"] == "completed"
    assert len(g.captured) == 1
    assert submit(g, name="Other b", identity=identity).status_code == 409
    # Explicit new versions are separate; the old image stays intact.
    second = submit(g)
    assert second.status_code == 202 and second.json()["id"] != identity
    assert g.client.get(f"/api/planet-portraits/{identity}/image").content == g.data


def test_busy_stale_brief_missing_radius_and_unknown_planet_do_not_generate(generation):
    g = generation
    assert submit(g, hash_value="0" * 64).status_code == 409
    assert submit(g, name="Empty b").status_code == 422
    assert (
        g.client.post(
            "/api/planet-portraits",
            json={"request_id": str(uuid4()), "planet_id": "absent", "prompt_sha256": "a" * 64},
            headers={"X-WebbWatch-Action": "generate-portrait"},
        ).status_code
        == 404
    )
    assert submit(g).status_code == 202
    assert submit(g, name="Other b").status_code == 409
    assert len(g.queued) == 1 and not g.captured


@pytest.mark.parametrize(
    "change",
    [
        {"openai_api_key": None},
        {"portrait_generation_enable": False},
        {"environment": "production"},
    ],
)
def test_configuration_gates_paid_requests(generation, change):
    g = generation
    app.dependency_overrides[get_settings] = lambda: g.settings.model_copy(update=change)
    config = g.client.get("/api/planet-portraits/config").json()
    assert not config["ready"] and config["reason"]
    assert submit(g).status_code in (403, 503)
    assert not g.queued


def test_foreign_origin_and_missing_action_header_are_rejected(generation, monkeypatch):
    g = generation
    assert submit(g, origin="https://foreign.example").status_code == 403
    assert submit(g, **{"X-WebbWatch-Action": ""}).status_code == 403
    monkeypatch.setattr(routes, "local_client", lambda _: False)
    assert submit(g).status_code == 403
    assert not g.client.get("/api/planet-portraits/config").json()["ready"]
    assert not g.queued


def test_stale_jobs_become_interrupted_without_automatic_retry(generation):
    g = generation
    identity = submit(g).json()["id"]
    row = g.session.get(PlanetPortrait, identity)
    row.deadline = time.time() - 1
    g.session.commit()
    result = g.client.get(f"/api/planet-portraits/{identity}").json()
    assert result["status"] == "interrupted" and "charged" in result["error"]
    g.run(identity, g.settings)
    assert not g.captured
    assert submit(g).status_code == 202


@pytest.mark.parametrize("error_kind", ["timeout", "denied", "invalid_image", "storage"])
def test_failure_keeps_brief_and_never_leaks_provider_error(generation, monkeypatch, error_kind):
    g = generation
    identity = submit(g).json()["id"]
    request = httpx.Request("POST", "https://api.openai.com/v1/images/generations")
    secret = "private-key-must-not-appear"

    def fail(**kwargs):
        if error_kind == "timeout":
            raise APITimeoutError(request=request)
        if error_kind == "denied":
            raise APIStatusError(secret, response=httpx.Response(403, request=request), body=None)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"bad").decode())])

    if error_kind == "storage":
        original_upload = g.storage.upload

        def broken_upload(**kwargs):
            if kwargs["key"].endswith("evidence.json"):
                raise OSError(secret)
            return original_upload(**kwargs)

        monkeypatch.setattr(g.storage, "upload", broken_upload)
    else:
        g.provider.images.generate = fail
    g.run(identity, g.settings)
    g.session.expire_all()
    result = g.client.get(f"/api/planet-portraits/{identity}").json()
    assert result["status"] == "failed" and result["error"]
    assert result["image_url"] is None and secret not in json.dumps(result)
    assert result["prompt"] and result["evidence"]["groups"]
    assert g.client.get(result["prompt_url"]).status_code == 200
    assert g.client.get(result["evidence_url"]).status_code == 200
    assert g.client.get(f"/api/planet-portraits/{identity}/image").status_code == 404


def test_list_pagination_filter_and_invalid_download_identifiers(generation):
    g = generation
    one = submit(g).json()["id"]
    g.run(one, g.settings)
    two = submit(g, name="Other b").json()["id"]
    g.run(two, g.settings)
    response = g.client.get("/api/planet-portraits?limit=1").json()
    assert response["has_more"] and len(response["items"]) == 1
    filtered = g.client.get(f"/api/planet-portraits?planet_id={planet_id('Test b')}").json()
    assert [item["id"] for item in filtered["items"]] == [one]
    assert "prompt" not in filtered["items"][0]
    assert g.client.get("/api/planet-portraits/not-a-uuid/image").status_code == 422
    assert g.client.get(f"/api/planet-portraits/{uuid4()}").status_code == 404


def test_latest_previews_select_completed_versions_across_planets_and_history(generation):
    g = generation
    first = submit(g).json()["id"]
    g.run(first, g.settings)
    second = submit(g).json()["id"]
    g.run(second, g.settings)
    other = submit(g, name="Other b").json()["id"]
    g.run(other, g.settings)
    g.session.expire_all()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for index, identity in enumerate([first, second, other]):
        g.session.get(PlanetPortrait, identity).created_at = start + timedelta(minutes=index)
    g.session.commit()
    # A completed image must remain discoverable beyond the five recent history entries.
    for status in ["failed"] * 5 + ["interrupted", "generating"]:
        identity = submit(g).json()["id"]
        row = g.session.get(PlanetPortrait, identity)
        row.status = status
        row.active_slot = None
        g.session.commit()
    response = g.client.get(
        "/api/planet-portraits/latest",
        params=[("planet_id", planet_id(name)) for name in ["Test b", "Other b", "Empty b"]],
    )
    assert response.status_code == 200
    items = {item["planet_id"]: item for item in response.json()["items"]}
    assert {key: value["id"] for key, value in items.items()} == {
        planet_id("Test b"): second,
        planet_id("Other b"): other,
    }
    assert "prompt" not in items[planet_id("Test b")]
    assert items[planet_id("Test b")]["thumbnail_url"].endswith(f"/{second}/thumbnail")
    # Read-only browsing needs neither the generation flag nor an API key.
    app.dependency_overrides[get_settings] = lambda: g.settings.model_copy(
        update={"openai_api_key": None, "portrait_generation_enable": False}
    )
    filtered = g.client.get(
        "/api/planet-portraits/latest", params={"planet_id": planet_id("Other b")}
    ).json()
    assert [item["id"] for item in filtered["items"]] == [other]
    assert g.client.get("/api/planet-portraits/latest?planet_id=unknown").json() == {"items": []}
    assert len(g.captured) == 3


def test_latest_preview_query_is_bounded(generation):
    client = generation.client
    assert client.get("/api/planet-portraits/latest").status_code == 422
    assert client.get("/api/planet-portraits/latest?planet_id=").status_code == 422
    assert client.get("/api/planet-portraits/latest?planet_id=" + "a" * 161).status_code == 422
    assert client.get(
        "/api/planet-portraits/latest", params=[("planet_id", str(i)) for i in range(101)]
    ).status_code == 422


def test_thumbnail_preserves_full_frame_and_original_and_handles_unavailable_image(
    generation, monkeypatch
):
    g = generation
    identity = submit(g).json()["id"]
    url = f"/api/planet-portraits/{identity}/thumbnail"
    assert g.client.get(url).status_code == 404
    g.run(identity, g.settings)
    response = g.client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "private, max-age=86400"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (256, 256)
    assert g.client.get(f"/api/planet-portraits/{identity}/image").content == g.data
    # Also retain the full bounds if a stored image has a different aspect ratio.
    frame = Image.new("RGB", (1024, 512), "red")
    frame.paste("blue", (512, 0, 1024, 512))
    framed = io.BytesIO()
    frame.save(framed, format="PNG")
    monkeypatch.setattr(g.storage, "read", lambda _: framed.getvalue())
    with Image.open(io.BytesIO(g.client.get(url).content)) as image:
        assert image.size == (256, 128)
        assert image.getpixel((0, 0))[0] > 240
        assert image.getpixel((255, 127))[2] > 240

    def missing(_):
        raise FileNotFoundError("private storage path")

    monkeypatch.setattr(g.storage, "read", missing)
    assert g.client.get(url).status_code == 503
    assert "private storage path" not in g.client.get(url).text
    assert g.client.get("/api/planet-portraits/invalid/thumbnail").status_code == 422


def test_evidence_classification_preserves_limits_estimates_and_sources():
    catalog = CatalogSnapshot([planet("Bound b", pl_radelim=1)], {})
    groups = evidence_groups(catalog.detail(planet_id("Bound b")))
    radius = next(c for c in groups[0]["claims"] if c["title"] == "Planet radius")
    assert radius["value"].startswith("< ") and radius["sources"]
    assert any("surface temperature" in c["explanation"] for c in groups[1]["claims"])
    assert any("neutral gray" in c["explanation"] for c in groups[1]["claims"])
    assert "not a physical simulation" in groups[2]["claims"][-1]["explanation"]


def test_settings_never_disclose_keys_in_config_error():
    assert config_error(Settings(_env_file=None, openai_api_key=None))
    assert (
        config_error(
            Settings(_env_file=None, openai_api_key="private", portrait_generation_enable=True)
        )
        is None
    )
