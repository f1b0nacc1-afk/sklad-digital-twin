import json

import pytest

from app.core.config import get_settings


@pytest.fixture
def stand_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path)
    run = tmp_path / "stand_demo" / "20260101_000000"
    (run / "scenes" / "scene_00").mkdir(parents=True)
    summary = {"run": run.name, "created": "2026-01-01T00:00:00", "weights": "m.pt",
               "totals": {"scenes": 1}, "scenes": [{"id": "scene_00"}]}
    (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run / "scenes" / "scene_00" / "scene.json").write_text('{"id": "scene_00"}')
    (run / "scenes" / "scene_00" / "frame.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path / "secret.txt").write_text("x")
    return run


def test_stand_runs(client, admin_headers, stand_storage):
    runs = client.get("/api/stand/runs", headers=admin_headers).json()
    assert [r["run"] for r in runs] == [stand_storage.name]
    run = client.get(f"/api/stand/runs/{stand_storage.name}", headers=admin_headers).json()
    assert run["scenes"][0]["id"] == "scene_00"
    scene = client.get(f"/api/stand/runs/{stand_storage.name}/scenes/scene_00",
                       headers=admin_headers)
    assert scene.json()["id"] == "scene_00"


def test_stand_file_served_and_traversal_blocked(client, admin_headers, stand_storage):
    base = f"/api/stand/runs/{stand_storage.name}/files"
    resp = client.get(f"{base}/scenes/scene_00/frame.jpg", headers=admin_headers)
    assert resp.status_code == 200 and resp.headers["content-type"] == "image/jpeg"
    assert client.get(f"{base}/../../secret.txt", headers=admin_headers).status_code == 404
    assert client.get(f"{base}/%2e%2e/%2e%2e/secret.txt",
                      headers=admin_headers).status_code == 404
    assert client.get("/api/stand/runs/..", headers=admin_headers).status_code == 404


def test_stand_requires_auth(client, stand_storage):
    assert client.get("/api/stand/runs").status_code == 401


def test_stand_empty_storage(client, admin_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "storage_dir", tmp_path)
    assert client.get("/api/stand/runs", headers=admin_headers).json() == []
