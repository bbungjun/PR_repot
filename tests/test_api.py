import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archmap.api import create_app

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = {"X-Archmap-Token": "test-token"}


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHMAP_TOKEN", "test-token")
    monkeypatch.setenv("ARCHMAP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARCHMAP_BASE_URL", "http://testserver")
    return TestClient(create_app())


def test_pr_report_roundtrip(client):
    body = {"architecture": _load("architecture_120.json"), "pr_delta": _load("pr_delta_120.json")}
    res = client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 200
    assert res.json()["report_url"] == "http://testserver/reports/Autoresearch/120"
    page = client.get("/reports/Autoresearch/120")
    assert page.status_code == 200 and "PR #120" in page.text


def test_manifest_accepted(client):
    res = client.post("/api/manifest", json=_load("architecture_120.json"), headers=TOKEN)
    assert res.status_code == 200 and res.json() == {"ok": True}


def test_invalid_payload_rejected(client):
    bad = _load("pr_delta_120.json")
    del bad["changed_modules"]
    body = {"architecture": _load("architecture_120.json"), "pr_delta": bad}
    assert client.post("/api/pr-report", json=body, headers=TOKEN).status_code == 400


def test_missing_token_rejected(client):
    assert client.post("/api/manifest", json=_load("architecture_120.json")).status_code == 401


def test_unknown_report_404(client):
    assert client.get("/reports/Autoresearch/999").status_code == 404
