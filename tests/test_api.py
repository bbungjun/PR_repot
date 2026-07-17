import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from archmap.api import _check_token, create_app

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


# --- Critical 1(재리뷰): 비-UTF8 바이트 바디는 400이어야 한다 ---
#
# request.json()은 내부적으로 json.loads(body)를 호출하는데, body가 유효한
# UTF-8이 아니면 UnicodeDecodeError를 던진다. 이는 json.JSONDecodeError의
# 서브클래스가 아닌 별개 예외라 기존 except 절에 걸리지 않고 그대로 500으로
# 유출됐었다.
#
# 주의: b"\xff\xfe..."처럼 UTF-16 BOM으로 시작하는 바이트열은 json.loads가
# UTF-16으로 재해석해버려(json.detect_encoding) UnicodeDecodeError가 아니라
# JSONDecodeError만 발생시킨다(우연히 400이 나서 이 결함을 가림). BOM이 아니고
# 길이가 4바이트 이상도 아닌 순수 잘못된 UTF-8 시작 바이트를 써야 실제
# UnicodeDecodeError가 재현된다.

NON_UTF8_BODY = b"\x80\x81\x82"


def test_pr_report_rejects_non_utf8_body(client):
    res = client.post("/api/pr-report", content=NON_UTF8_BODY, headers=TOKEN)
    assert res.status_code == 400


def test_manifest_rejects_non_utf8_body(client):
    res = client.post("/api/manifest", content=NON_UTF8_BODY, headers=TOKEN)
    assert res.status_code == 400


# --- Critical 2(재리뷰): 비-ASCII 토큰 헤더는 401이어야 한다 ---
#
# Starlette는 헤더 값을 latin-1로 디코딩하므로, 상위 바이트(0x80 이상)가 든
# 원시 헤더도 성공적으로 디코딩되어 non-ASCII 문자가 든 str이 된다. 이를
# hmac.compare_digest(provided, expected)에 그대로 넘기면
# "comparing strings with non-ASCII characters is not supported" TypeError가
# 나며 500으로 유출됐었다.
#
# httpx의 Python 클라이언트 API(headers=dict[str, str])는 str 헤더를 ASCII로만
# 인코딩하려 해서 이 케이스를 가리므로, raw byte 헤더 튜플로 직접 요청을
# 구성해야 재현된다.

NON_ASCII_TOKEN_HEADERS = [(b"X-Archmap-Token", b"\xf6\xe9\xe8\xe0")]


def test_manifest_rejects_non_ascii_token_header(client):
    request = client.build_request(
        "POST",
        "/api/manifest",
        json=_load("architecture_120.json"),
        headers=NON_ASCII_TOKEN_HEADERS,
    )
    res = client.send(request)
    assert res.status_code == 401


def test_check_token_rejects_non_ascii_token_directly():
    # 위 e2e 테스트가 httpx/starlette 내부 동작 변경에 영향받을 수 있으므로,
    # _check_token을 직접 호출하는 단위 테스트로도 동일한 결함을 커버한다.
    import os

    os.environ["ARCHMAP_TOKEN"] = "test-token"
    try:
        from starlette.requests import Request as StarletteRequest

        scope = {
            "type": "http",
            "headers": [(b"x-archmap-token", b"\xf6\xe9\xe8\xe0")],
        }
        req = StarletteRequest(scope)
        with pytest.raises(HTTPException) as exc_info:
            _check_token(req)
        assert exc_info.value.status_code == 401
    finally:
        os.environ.pop("ARCHMAP_TOKEN", None)
