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


# --- Critical 1(재재리뷰): 깊은 중첩 JSON·거대 정수 리터럴이 500으로 유출됨 ---
#
# json.JSONDecodeError -> (json.JSONDecodeError, UnicodeDecodeError)로
# 화이트리스트를 넓혀온 접근이 다시 두 입력에서 뚫렸다:
#   - 깊게 중첩된 JSON은 파싱 중 RecursionError를 던진다. RecursionError는
#     RuntimeError의 서브클래스라 ValueError 계열(JSONDecodeError,
#     UnicodeDecodeError)에 속하지 않아 기존 except에 걸리지 않았다.
#   - 거대한 정수 리터럴(수천 자리)은 CPython의 정수-문자열 변환 한도
#     보호장치에 걸려 ValueError를 던지지만, 이 ValueError는
#     json.JSONDecodeError의 인스턴스가 아닌 자매 클래스(둘 다 ValueError를
#     상속할 뿐 서로 무관)라 걸리지 않았다.
# 둘 다 악의적 공격이 아니라 CI 쪽의 단순한 직렬화 루프 버그나 잘못된 숫자
# 생성으로도 우발적으로 트리거될 수 있는, 평범한 크기(수십 KB)의 입력이다.
# 이번에는 예외 클래스를 하나 더 추가하는 대신, _read_json_object의 파싱
# 단계 전체를 감싸는 원칙(모든 파싱 실패는 400)으로 바꿔 근본적으로 막았다.

PATHOLOGICAL_BODIES = {
    "deep_nesting": b'{"a":' * 10000 + b"1" + b"}" * 10000,
    "huge_integer_literal": b'{"architecture": ' + b"9" * 5000 + b', "pr_delta": {}}',
}


@pytest.mark.parametrize("body", PATHOLOGICAL_BODIES.values(), ids=PATHOLOGICAL_BODIES.keys())
def test_pr_report_rejects_pathological_body(client, body):
    res = client.post("/api/pr-report", content=body, headers=TOKEN)
    assert res.status_code == 400


@pytest.mark.parametrize("body", PATHOLOGICAL_BODIES.values(), ids=PATHOLOGICAL_BODIES.keys())
def test_manifest_rejects_pathological_body(client, body):
    res = client.post("/api/manifest", content=body, headers=TOKEN)
    assert res.status_code == 400


# --- 원칙적 수정의 범위 검증: 파싱 이후 단계의 진짜 서버 버그는 여전히 500이어야 한다 ---
#
# _read_json_object의 광범위한 except Exception은 "파싱 단계"에만 적용된다.
# 만약 이 범위를 넓혀 핸들러 전체나 렌더링·저장 단계까지 감쌌다면, render_report의
# 렌더러 결함이나 Store.save_report의 디스크 오류 같은 진짜 서버 버그까지
# 400(클라이언트 잘못)으로 위장되어 운영 중 디버깅이 불가능해졌을 것이다.
# 아래 두 테스트는 그런 예외가 여전히 500으로 보고되는지 확인해, 이번 수정이
# 파싱 경계에만 좁게 적용됐음을 증명한다.


def _raw_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ARCHMAP_TOKEN", "test-token")
    monkeypatch.setenv("ARCHMAP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARCHMAP_BASE_URL", "http://testserver")
    # 기본 TestClient는 핸들러에서 처리되지 않은 예외를 파이썬 예외로 그대로
    # 재발생시킨다. 실제 500 응답이 만들어지는지 보려면 이를 꺼야 한다.
    return TestClient(create_app(), raise_server_exceptions=False)


def test_render_report_bug_still_returns_500(monkeypatch, tmp_path):
    def _boom(architecture, pr_delta):
        raise RuntimeError("렌더러 결함 시뮬레이션")

    monkeypatch.setattr("archmap.api.render_report", _boom)
    raw_client = _raw_client(monkeypatch, tmp_path)
    body = {"architecture": _load("architecture_120.json"), "pr_delta": _load("pr_delta_120.json")}
    res = raw_client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 500


# --- Critical: 길이 제한 없는 화이트리스트가 500으로 유출되는 문제 ------------
#
# archmap/storage.py의 _validate_component가 문자 "종류"만 검사하고 "길이"는
# 검사하지 않아, 문자는 안전하지만 파일시스템 컴포넌트 한도를 넘는 값이
# 검증을 통과한 뒤 Path.resolve()/exists()나 tempfile.mkstemp에서
# OSError(Errno 36, "File name too long")를 던지고 500으로 유출됐다. 아래
# 네 가지는 재리뷰가 실행으로 재현한 시나리오를 그대로 회귀 테스트로 옮긴
# 것이다(수정 전 실행 결과는 태스크 보고서에 기록).

def test_pr_report_rejects_overlong_repo_returns_400(client):
    pr_delta = dict(_load("pr_delta_120.json"), repo="a" * 255)
    body = {"architecture": _load("architecture_120.json"), "pr_delta": pr_delta}
    res = client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 400


def test_manifest_rejects_overlong_repo_returns_400(client):
    arch = dict(_load("architecture_120.json"), repo="a" * 255)
    res = client.post("/api/manifest", json=arch, headers=TOKEN)
    assert res.status_code == 400


def test_pr_report_rejects_overlong_repo_5000_returns_400(client):
    pr_delta = dict(_load("pr_delta_120.json"), repo="a" * 5000)
    body = {"architecture": _load("architecture_120.json"), "pr_delta": pr_delta}
    res = client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 400


def test_pr_report_rejects_overlong_head_sha_returns_400(client):
    pr_delta = dict(_load("pr_delta_120.json"), head_sha="a" * 5000)
    body = {"architecture": _load("architecture_120.json"), "pr_delta": pr_delta}
    res = client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 400


def test_get_report_rejects_overlong_repo_5000_returns_400(client):
    res = client.get(f"/reports/{'a' * 5000}/1")
    assert res.status_code == 400


# --- Important: pr이 정수가 아니면 200과 함께 깨진 report_url이 반환되던 문제 ---
#
# JSON Schema draft 2020-12의 "integer" 타입은 3.0처럼 소수부가 0인 숫자를
# 허용한다. 수정 전에는 pr: 3.0이 계약 검증을 통과해 200과
# "report_url": ".../reports/Autoresearch/3.0"을 반환했지만, 그 URL을 GET하면
# 404였다(리포트는 "pr-3.0" 디렉터리에 저장되지만 API로는 도달 불가). 서버가
# 스스로 반환한 링크가 깨지는 것은 공개 계약의 최악의 실패 모드이므로 400으로
# 막는다.

@pytest.mark.parametrize("pr_value", [3.0, True, "3"])
def test_pr_report_rejects_non_integer_pr(client, pr_value):
    pr_delta = dict(_load("pr_delta_120.json"), pr=pr_value)
    body = {"architecture": _load("architecture_120.json"), "pr_delta": pr_delta}
    assert client.post("/api/pr-report", json=body, headers=TOKEN).status_code == 400


def test_pr_report_accepts_real_integer_pr(client):
    # 정상 pr(정수)은 계속 200과 도달 가능한 report_url을 반환해야 한다.
    body = {"architecture": _load("architecture_120.json"), "pr_delta": _load("pr_delta_120.json")}
    res = client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 200
    report_url = res.json()["report_url"]
    path = report_url.replace("http://testserver", "")
    assert client.get(path).status_code == 200


def test_store_save_report_bug_still_returns_500(monkeypatch, tmp_path):
    def _boom(self, pr_delta, html):
        raise OSError("디스크 오류 시뮬레이션")

    monkeypatch.setattr("archmap.storage.Store.save_report", _boom)
    raw_client = _raw_client(monkeypatch, tmp_path)
    body = {"architecture": _load("architecture_120.json"), "pr_delta": _load("pr_delta_120.json")}
    res = raw_client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 500
