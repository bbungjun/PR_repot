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


def test_underscored_module_name_covered_by_original_fixture():
    # 회귀 재현 테스트: 픽스처를 변형하지 않고 원본 그대로 사용한다. 모듈
    # "action_logs.llm_generator"(mod_name="llm_generator", 언더스코어 포함)는
    # tests.files의 "tests/test_action_log_llm_generator.py"에 실제로 대응하는
    # 테스트 파일이 있으므로 verified를 받아야 한다. 이전 구현(mod_name in
    # stem.split("_"))은 "llm_generator" 문자열 자체가 토큰 리스트
    # ["action", "log", "llm", "generator"]의 원소가 될 수 없어 영원히
    # 매칭에 실패했다(허위 warning 회귀).
    claims = build_claims(_delta())
    hit = [c for c in claims if c["module"] == "action_logs.llm_generator" and "테스트" in c["text"]]
    assert hit and hit[0]["status"] == VERIFIED


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


def test_schema_change_status_depends_only_on_breaking_flag_not_change_value():
    # schema_changes 판정은 change 값("added"/"removed")이 아니라 오직 breaking
    # 플래그에만 의존해야 한다. added+breaking=True는 warning, removed+breaking=False는
    # verified가 되어야 함을 확인해 change 값과 판정이 우연히 일치하지 않음을 증명한다.
    d = _delta()
    d["schema_changes"] = [
        {"model": "ActionLog", "field": "risky_new_field", "change": "added",
         "module": "action_logs.schema", "breaking": True},
        {"model": "ActionLog", "field": "safe_removed_field", "change": "removed",
         "module": "action_logs.schema", "breaking": False},
    ]
    claims = build_claims(d)
    added_breaking = [c for c in claims if "risky_new_field" in c["text"]]
    removed_nonbreaking = [c for c in claims if "safe_removed_field" in c["text"]]
    assert added_breaking and added_breaking[0]["status"] == WARNING and "필드 추가" in added_breaking[0]["text"]
    assert removed_nonbreaking and removed_nonbreaking[0]["status"] == VERIFIED \
        and "필드 제거" in removed_nonbreaking[0]["text"]
