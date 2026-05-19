"""Watchlist CRUD round-trip via TestClient."""
from __future__ import annotations


def test_create_then_list_then_get(client):
    payload = {
        "name": "NIRCam imaging",
        "criteria": {"instruments": ["NIRCAM"], "product_types": ["i2d"]},
    }
    created = client.post("/api/watchlists", json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "NIRCam imaging"
    assert body["enabled"] is True
    assert body["criteria_json"]["instruments"] == ["NIRCAM"]
    wl_id = body["id"]

    listed = client.get("/api/watchlists")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = client.get(f"/api/watchlists/{wl_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == wl_id


def test_patch_toggles_enabled_and_replaces_criteria(client):
    created = client.post(
        "/api/watchlists",
        json={"name": "x", "criteria": {"instruments": ["NIRCAM"]}},
    ).json()
    wl_id = created["id"]

    patched = client.patch(
        f"/api/watchlists/{wl_id}",
        json={"enabled": False, "criteria": {"instruments": ["MIRI"], "product_types": ["x1d"]}},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["enabled"] is False
    assert body["criteria_json"]["instruments"] == ["MIRI"]
    assert body["criteria_json"]["product_types"] == ["x1d"]


def test_delete_404s_after(client):
    created = client.post(
        "/api/watchlists", json={"name": "x", "criteria": {"instruments": ["NIRCAM"]}}
    ).json()
    wl_id = created["id"]

    assert client.delete(f"/api/watchlists/{wl_id}").status_code == 204
    assert client.get(f"/api/watchlists/{wl_id}").status_code == 404


def test_cone_validation_rejects_out_of_range(client):
    bad = client.post(
        "/api/watchlists",
        json={
            "name": "bad cone",
            "criteria": {"cone": {"ra": 999, "dec": 0, "radius_arcsec": 60}},
        },
    )
    assert bad.status_code == 422
