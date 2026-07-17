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


# --- Critical 1: 잘못된 JSON·비-객체 바디는 500이 아니라 400이어야 한다 ---

MALFORMED_BODIES = {
    "invalid_json_syntax": b"{not valid json",
    "empty_body": b"",
    "top_level_list": b'["a", "b"]',
    "top_level_string": b'"hello"',
}


@pytest.mark.parametrize("body", MALFORMED_BODIES.values(), ids=MALFORMED_BODIES.keys())
def test_pr_report_rejects_malformed_body(client, body):
    res = client.post("/api/pr-report", content=body, headers=TOKEN)
    assert res.status_code == 400


@pytest.mark.parametrize("body", MALFORMED_BODIES.values(), ids=MALFORMED_BODIES.keys())
def test_manifest_rejects_malformed_body(client, body):
    res = client.post("/api/manifest", content=body, headers=TOKEN)
    assert res.status_code == 400


# --- Important 2: 토큰 비교는 상수 시간이어야 하고, 헤더 부재도 안전해야 한다 ---

def test_wrong_token_rejected(client):
    res = client.post(
        "/api/manifest", json=_load("architecture_120.json"),
        headers={"X-Archmap-Token": "wrong-token"},
    )
    assert res.status_code == 401


def test_missing_header_does_not_crash(client):
    # 토큰 헤더 자체가 없을 때 hmac.compare_digest에 None이 들어가 TypeError로
    # 500이 나지 않고, 정상적으로 401을 반환해야 한다.
    res = client.post("/api/manifest", json=_load("architecture_120.json"))
    assert res.status_code == 401


# --- Important 3: 경로 주입 방어(Store의 ValueError -> 400) 회귀 테스트 ---

MALICIOUS_REPO_VALUES = ["../../etc/passwd", "has space", "a/b", "..", "."]


@pytest.mark.parametrize("repo", MALICIOUS_REPO_VALUES)
def test_pr_report_rejects_malicious_repo(client, repo):
    pr_delta = _load("pr_delta_120.json")
    pr_delta["repo"] = repo
    body = {"architecture": _load("architecture_120.json"), "pr_delta": pr_delta}
    assert client.post("/api/pr-report", json=body, headers=TOKEN).status_code == 400


@pytest.mark.parametrize("repo", MALICIOUS_REPO_VALUES)
def test_manifest_rejects_malicious_repo(client, repo):
    arch = _load("architecture_120.json")
    arch["repo"] = repo
    assert client.post("/api/manifest", json=arch, headers=TOKEN).status_code == 400


# GET 경로의 {repo}는 URL 경로 세그먼트라서, 슬래시나 "."/".."로만 이루어진
# 값은 서버에 도달하기 전에 HTTP 클라이언트가 URL 정규화 과정에서 없애버린다
# (예: "/reports/../1" -> "/1"). 이는 우리 코드가 아닌 클라이언트 동작이므로,
# 여기서는 정규화되지 않고 단일 세그먼트로 그대로 전달되는 악성 값만 사용한다.
GET_MALICIOUS_REPO_VALUES = ["has space", "semi;colon", 'quote"mark']


@pytest.mark.parametrize("repo", GET_MALICIOUS_REPO_VALUES)
def test_get_report_rejects_malicious_repo(client, repo):
    assert client.get(f"/reports/{repo}/1").status_code == 400


# --- Important 4: 400 메시지에 스키마 전문이 노출되면 안 된다 ---

def test_validation_error_detail_excludes_full_schema(client):
    bad = _load("pr_delta_120.json")
    del bad["changed_modules"]
    body = {"architecture": _load("architecture_120.json"), "pr_delta": bad}
    res = client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "$schema" not in detail
    assert "changed_modules" in detail
