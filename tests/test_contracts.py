import json
from pathlib import Path

import jsonschema
import pytest

from archmap.contracts import SCHEMA_VERSION, validate_architecture, validate_pr_delta

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_schema_version_const():
    assert SCHEMA_VERSION == "archmap-v0"


def test_architecture_fixture_is_valid():
    validate_architecture(_load("architecture_120.json"))


def test_pr_delta_fixture_is_valid():
    validate_pr_delta(_load("pr_delta_120.json"))


def test_architecture_missing_required_field_rejected():
    doc = _load("architecture_120.json")
    del doc["modules"]
    with pytest.raises(jsonschema.ValidationError):
        validate_architecture(doc)


def test_pr_delta_wrong_schema_version_rejected():
    doc = _load("pr_delta_120.json")
    doc["schema_version"] = "archmap-v999"
    with pytest.raises(jsonschema.ValidationError):
        validate_pr_delta(doc)


# --- Important: repo_url 스킴 미검증 -> 클릭 가능한 XSS -------------------
#
# repo_url이 "javascript:alert(1)" 같은 값이면 렌더러의 앵커가
# href="javascript:alert(1)/blob/..."가 된다. autoescape는 속성값을
# 이스케이프하지만 스킴 자체는 막지 못하므로, 계약(스키마) 단계에서
# http(s) 스킴만 허용해야 한다. repo_url은 required가 아니고 추출기가
# --repo-url 미지정 시 빈 문자열을 보내는 경로가 있으므로, 빈 문자열은
# 계속 통과해야 한다(기존 추출기 산출물 호환).

def test_architecture_rejects_javascript_scheme_repo_url():
    doc = _load("architecture_120.json")
    doc["repo_url"] = "javascript:alert(1)"
    with pytest.raises(jsonschema.ValidationError):
        validate_architecture(doc)


def test_architecture_accepts_https_repo_url():
    doc = _load("architecture_120.json")
    doc["repo_url"] = "https://github.com/SKYAHO/Autoresearch"
    validate_architecture(doc)  # 예외 없이 통과해야 한다.


def test_architecture_accepts_empty_repo_url():
    # 추출기가 --repo-url 미지정 시 빈 문자열을 보내는 기존 경로 호환.
    doc = _load("architecture_120.json")
    doc["repo_url"] = ""
    validate_architecture(doc)  # 예외 없이 통과해야 한다.
