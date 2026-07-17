import json
from pathlib import Path

from archmap.verify import NARRATED, VERIFIED, WARNING, build_claims

FIXTURES = Path(__file__).parent / "fixtures"


def _delta():
    return json.loads((FIXTURES / "pr_delta_120.json").read_text(encoding="utf-8"))


def test_unchanged_contract_is_verified():
    claims = build_claims(_delta())
    hit = [c for c in claims if "ACTION_LOG_SCHEMA_VERSION" in c["text"] and "불변" in c["text"]]
    assert hit and hit[0]["status"] == VERIFIED
    assert hit[0]["module"] == "action_logs.schema" and hit[0]["line"] == 16


def test_nonbreaking_version_change_is_verified():
    claims = build_claims(_delta())
    hit = [c for c in claims if "PROMPT_VERSION" in c["text"]]
    assert hit and hit[0]["status"] == VERIFIED and "action_log_ctr_v4" in hit[0]["text"]


def test_breaking_version_change_is_warning():
    d = _delta()
    d["version_changes"][0]["breaking"] = True
    claims = build_claims(d)
    hit = [c for c in claims if "PROMPT_VERSION" in c["text"]]
    assert hit[0]["status"] == WARNING


def test_tests_covered_module_verified_and_uncovered_warned():
    d = _delta()
    d["tests"]["files"] = ["tests/test_action_logs_daily.py"]
    claims = build_claims(d)
    daily = [c for c in claims if c["module"] == "action_logs.daily" and "테스트" in c["text"]]
    llm = [c for c in claims if c["module"] == "action_logs.llm_generator" and "테스트" in c["text"]]
    assert daily[0]["status"] == VERIFIED
    assert llm[0]["status"] == WARNING


def test_breaking_cross_repo_is_warning():
    d = _delta()
    d["cross_repo"][0]["breaking"] = True
    claims = build_claims(d)
    hit = [c for c in claims if "batch-contract-v1" in c["text"]]
    assert hit[0]["status"] == WARNING


def test_no_claim_is_narrated_by_default():
    assert all(c["status"] != NARRATED for c in build_claims(_delta()))


def test_short_module_name_not_falsely_covered_by_substring_match():
    # 회귀 테스트: 모듈명 "log"가 무관한 테스트 파일명 "action_logs_daily"에
    # 부분 문자열로 우연히 포함되어도 verified를 받아서는 안 된다(허위 초록 금지).
    # "log"를 실제로 검증하는 테스트는 존재하지 않으므로 warning이어야 한다.
    d = _delta()
    d["changed_modules"].append({
        "id": "action_logs.log",
        "path": "autoresearch/action_logs/log.py",
        "stage": "action_logs",
        "symbols_changed": [{"name": "write_log", "change": "signature", "line": 1}],
        "public_surface_changed": True,
    })
    d["tests"]["files"] = ["tests/test_action_logs_daily.py"]
    claims = build_claims(d)
    hit = [c for c in claims if c["module"] == "action_logs.log" and "테스트" in c["text"]]
    assert hit and hit[0]["status"] == WARNING


def test_schema_change_added_verified_and_removed_warning():
    d = _delta()
    d["schema_changes"] = [
        {"model": "ActionLog", "field": "retry_count", "change": "added",
         "module": "action_logs.schema", "breaking": False},
        {"model": "ActionLog", "field": "legacy_id", "change": "removed",
         "module": "action_logs.schema", "breaking": True},
    ]
    claims = build_claims(d)
    added = [c for c in claims if "retry_count" in c["text"]]
    removed = [c for c in claims if "legacy_id" in c["text"]]
    assert added and added[0]["status"] == VERIFIED and "필드 추가" in added[0]["text"]
    assert removed and removed[0]["status"] == WARNING and "필드 제거" in removed[0]["text"]
