import json
from pathlib import Path

from archmap.verify import INFO, NARRATED, VERIFIED, WARNING, build_claims

FIXTURES = Path(__file__).parent / "fixtures"


def _delta():
    return json.loads((FIXTURES / "pr_delta_120.json").read_text(encoding="utf-8"))


def test_unchanged_contract_is_verified():
    claims = build_claims(_delta())
    hit = [c for c in claims if "ACTION_LOG_SCHEMA_VERSION" in c["text"] and "불변" in c["text"]]
    assert hit and hit[0]["status"] == VERIFIED
    assert hit[0]["module"] == "action_logs.schema" and hit[0]["line"] == 16


def test_nonbreaking_version_change_is_not_verified():
    # Critical B 회귀 재현: 스펙 §7이 VERIFIED를 인가하는 형태는 "X 계약/스키마
    # 불변", "하위호환", "테스트 커버됨" 세 가지뿐이다. 버전 상수 bump는
    # breaking=False라도 이 세 형태 중 어디에도 속하지 않는다 — extractor의
    # breaking 플래그는 §8 규칙으로 실제 판정된 적이 없어(값 변경 시 하드코딩
    # False) "비파괴 변경"이라는 초록 배지가 근거 없는 안전 보증이 된다.
    claims = build_claims(_delta())
    hit = [c for c in claims if "PROMPT_VERSION" in c["text"]]
    assert hit and hit[0]["status"] != VERIFIED


def test_nonbreaking_version_change_is_info():
    claims = build_claims(_delta())
    hit = [c for c in claims if "PROMPT_VERSION" in c["text"]]
    assert hit and hit[0]["status"] == INFO and "action_log_ctr_v4" in hit[0]["text"]


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


def test_nonbreaking_cross_repo_is_verified():
    # §7이 인가한 세 형태 중 "하위호환" 회귀 방지: cross_repo breaking=False는
    # 여전히 VERIFIED여야 한다(원본 픽스처가 이미 이 형태).
    claims = build_claims(_delta())
    hit = [c for c in claims if "batch-contract-v1" in c["text"] and "하위호환" in c["text"]]
    assert hit and hit[0]["status"] == VERIFIED


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


def test_unchanged_contract_claim_text_is_narrowly_scoped():
    # 최종 수용 검사관 지적(수정 1): 추출기가 실제로 아는 것은 "버전 상수 값과
    # 스키마 필드 목록이 안 바뀌었다"는 사실뿐이다. 옛 문구 "저장·생성 계약이
    # 바뀌지 않았습니다"는 validator(예: watch_time_sec >= 0 → >= 1)처럼 필드
    # 목록·타입은 그대로인 채 의미만 바뀌는 변경까지 "계약 불변"으로 단언해
    # 허위 보증이 된다. 문구가 검증된 사실 범위로 좁혀졌는지 고정한다.
    claims = build_claims(_delta())
    hit = [c for c in claims if "ACTION_LOG_SCHEMA_VERSION" in c["text"] and "불변" in c["text"]]
    assert hit and hit[0]["status"] == VERIFIED
    assert "저장·생성 계약이 바뀌지 않았습니다" not in hit[0]["text"]
    assert "필드 목록" in hit[0]["text"]


def test_schema_change_added_is_info_and_removed_is_warning():
    # §7의 세 형태에는 "필드 추가"가 없다 — breaking=False인 필드 추가도
    # version_changes와 같은 이유로 VERIFIED가 아니라 INFO여야 한다.
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
    assert added and added[0]["status"] == INFO and "필드 추가" in added[0]["text"]
    assert removed and removed[0]["status"] == WARNING and "필드 제거" in removed[0]["text"]


def test_breaking_signature_is_warning_with_symbol_name():
    # breaking_signatures 항목은 항상 WARNING이어야 하고, 리뷰어가 무엇이
    # 깨졌는지 알 수 있도록 심볼 이름이 문면에 포함되어야 한다.
    d = _delta()
    d["breaking_signatures"] = [
        {"module": "action_logs.daily", "name": "run_daily_action_log"},
        {"module": "action_logs.schema", "name": "EventLog"},
    ]
    claims = build_claims(d)
    daily = [c for c in claims if "run_daily_action_log" in c["text"]]
    event_log = [c for c in claims if "EventLog" in c["text"]]
    assert daily and daily[0]["status"] == WARNING and daily[0]["module"] == "action_logs.daily"
    assert event_log and event_log[0]["status"] == WARNING and event_log[0]["module"] == "action_logs.schema"


def test_missing_breaking_signatures_field_is_backward_compatible():
    # 기존 픽스처(필드 없음)에서는 아무 일도 일어나지 않아야 한다 — 필드는
    # 스키마 required가 아니므로 .get()으로 접근해 하위호환을 보장해야 한다.
    d = _delta()
    assert "breaking_signatures" not in d
    claims_without_field = build_claims(d)
    d2 = _delta()
    d2["breaking_signatures"] = []
    claims_with_empty_field = build_claims(d2)
    assert claims_without_field == claims_with_empty_field
    # 기존 6개 판정 계열의 claim 수(unchanged_contracts, version_changes,
    # cross_repo, changed_modules 2건)에서 변화가 없어야 한다.
    assert len(claims_without_field) == 5


def test_breaking_signature_never_verified_even_if_symbol_also_unchanged():
    # 핵심 불변식: breaking_signatures 항목은 어떤 상황에서도 verified가 될 수
    # 없다. 같은 심볼명이 unchanged_contracts에도 나타나 VERIFIED claim을 만들어도
    # breaking_signatures가 만든 claim 자체는 별개이며 여전히 WARNING이어야 한다.
    d = _delta()
    d["breaking_signatures"] = [
        {"module": "action_logs.schema", "name": "ACTION_LOG_SCHEMA_VERSION"},
    ]
    claims = build_claims(d)
    matches = [c for c in claims if "ACTION_LOG_SCHEMA_VERSION" in c["text"]]
    # unchanged_contracts가 만든 VERIFIED claim 1개 + breaking_signatures가
    # 만든 WARNING claim 1개, 총 2개가 있어야 하며 그중 어느 것도 뒤바뀌지 않는다.
    assert len(matches) == 2
    statuses = {c["status"] for c in matches}
    assert statuses == {VERIFIED, WARNING}
    warning_ones = [c for c in matches if c["status"] == WARNING]
    assert all(c["status"] != VERIFIED for c in warning_ones)


def test_cross_stage_same_filename_not_falsely_covered():
    # 회귀 재현 테스트(이번 수정의 핵심 대상): 이 레포에는 schema.py가
    # action_logs/virtual_users/youtube_collection 세 스테이지에 동시에 존재한다.
    # 마지막 구성요소("schema")만 대조하면 action_logs.schema가 완전히 무관한
    # virtual_users 스테이지의 test_virtual_users_schema.py 변경만으로 "테스트
    # 커버됨" 초록을 받는다 — 이 레포에는 tests/test_action_logs_schema.py가
    # 존재조차 하지 않으므로 이는 명백한 허위 초록이다. 패키지 토큰이 하나도
    # 겹치지 않으므로(action/logs vs virtual/users) warning이어야 한다.
    d = _delta()
    d["changed_modules"][0]["public_surface_changed"] = True  # action_logs.schema
    d["tests"]["files"] = ["tests/test_virtual_users_schema.py"]
    claims = build_claims(d)
    hit = [c for c in claims if c["module"] == "action_logs.schema" and "테스트" in c["text"]]
    assert hit and hit[0]["status"] == WARNING


def test_false_positive_youtube_backfill_job_test_does_not_cover_unrelated_package():
    # 최종 수용 검사관 지적 (a): "youtube" 토큰이 youtube_collection 패키지와
    # jobs.youtube_* 테스트에 겹쳐 test_youtube_backfill_job.py가
    # youtube_collection.backfill(다른 모듈, jobs.youtube_backfill이 아님)까지
    # "테스트 커버됨"으로 오판했다. youtube_collection의 실제 대응 테스트
    # test_youtube_collection_backfill.py는 미변경이므로 이건 허위 초록이다.
    d = _delta()
    d["changed_modules"].append({
        "id": "youtube_collection.backfill",
        "path": "autoresearch/youtube_collection/backfill.py",
        "stage": "youtube_collection",
        "symbols_changed": [{"name": "run_backfill", "change": "signature", "line": 1}],
        "public_surface_changed": True,
    })
    d["tests"]["files"] = ["tests/test_youtube_backfill_job.py"]
    claims = build_claims(d)
    hit = [c for c in claims if c["module"] == "youtube_collection.backfill" and "테스트" in c["text"]]
    assert hit and hit[0]["status"] == WARNING


def _module_claim_for(module_id: str, path: str, stage: str, test_file: str) -> dict:
    d = _delta()
    d["changed_modules"] = [{
        "id": module_id,
        "path": path,
        "stage": stage,
        "symbols_changed": [{"name": "run", "change": "signature", "line": 1}],
        "public_surface_changed": True,
    }]
    d["tests"]["files"] = [test_file]
    claims = build_claims(d)
    hit = [c for c in claims if c["module"] == module_id and "테스트" in c["text"]]
    assert hit, f"claim missing for {module_id}"
    return hit[0]


def test_jobs_action_log_covered_by_singular_job_test():
    # 최종 수용 검사관 지적 (b) 회귀 1/5: jobs(복수) != job(단수) 불일치로
    # 진짜 대응 테스트가 있는데도 warning이 뜨던 회귀. 단복수 정규화로 해소.
    # 이 스위트에는 jobs.* 픽스처가 없었으므로(검사관 지적) dict를 직접 구성한다.
    hit = _module_claim_for(
        "jobs.action_log", "autoresearch/jobs/action_log.py", "orchestration",
        "tests/test_action_log_job.py")
    assert hit["status"] == VERIFIED


def test_jobs_action_log_quality_covered_by_singular_job_test():
    # 회귀 2/5.
    hit = _module_claim_for(
        "jobs.action_log_quality", "autoresearch/jobs/action_log_quality.py", "orchestration",
        "tests/test_action_log_quality_job.py")
    assert hit["status"] == VERIFIED


def test_jobs_youtube_backfill_covered_by_singular_job_test():
    # 회귀 3/5. youtube_collection.backfill(위 false-positive 테스트)과 대조적으로
    # jobs.youtube_backfill은 이 테스트 파일과 실제로 대응하므로 매칭되어야 한다.
    hit = _module_claim_for(
        "jobs.youtube_backfill", "autoresearch/jobs/youtube_backfill.py", "orchestration",
        "tests/test_youtube_backfill_job.py")
    assert hit["status"] == VERIFIED


def test_jobs_youtube_trending_covered_by_singular_job_test():
    # 회귀 4/5.
    hit = _module_claim_for(
        "jobs.youtube_trending", "autoresearch/jobs/youtube_trending.py", "orchestration",
        "tests/test_youtube_trending_job.py")
    assert hit["status"] == VERIFIED


def test_src_features_feature_builder_covered_by_singular_feature_test():
    # 회귀 5/5: features(복수) != feature(단수) 불일치. 또한 3단 모듈 id
    # (src.features.feature_builder)에서 최상위 "src" 세그먼트가 대조에 끼어들어
    # 방해하지 않아야 한다.
    hit = _module_claim_for(
        "src.features.feature_builder", "src/features/feature_builder.py", "training",
        "tests/test_feature_builder.py")
    assert hit["status"] == VERIFIED


def test_jobs_action_log_not_falsely_covered_by_sibling_quality_test():
    # 최종 수용 검사관 지적(이번 수정의 핵심 대상): "jobs.action_log"(mod 토큰
    # [action, log])의 토큰열이 형제 모듈 "jobs.action_log_quality"의 토큰열의
    # 접두라서, 형제 모듈의 테스트 test_action_log_quality_job.py(진짜 대응
    # 테스트 test_action_log_job.py는 미변경)만으로도 mod 연속 부분열 매칭과
    # 패키지 토큰 {job} 부분집합 검사를 모두 통과해 "커버됨" 오판을 냈다.
    # stem에서 mod·패키지 토큰을 제거하면 "quality"가 잔여로 남아야 탈락한다.
    hit = _module_claim_for(
        "jobs.action_log", "autoresearch/jobs/action_log.py", "orchestration",
        "tests/test_action_log_quality_job.py")
    assert hit["status"] == WARNING


def test_jobs_action_log_quality_still_covered_by_own_test_after_leftover_fix():
    # 위 수정의 반대 방향 회귀 방지: "jobs.action_log_quality" 자신의 테스트
    # test_action_log_quality_job.py와는 여전히 매칭되어야 한다(mod 토큰 3개가
    # stem을 모두 소비하고 남은 "job"을 패키지 토큰이 소비해 잔여가 없다).
    hit = _module_claim_for(
        "jobs.action_log_quality", "autoresearch/jobs/action_log_quality.py", "orchestration",
        "tests/test_action_log_quality_job.py")
    assert hit["status"] == VERIFIED


def test_jobs_action_log_still_covered_by_its_own_real_test():
    # 회귀 방지: jobs.action_log의 진짜 대응 테스트 test_action_log_job.py와는
    # (형제 quality 테스트가 섞여 있어도) 여전히 매칭되어야 한다.
    hit = _module_claim_for(
        "jobs.action_log", "autoresearch/jobs/action_log.py", "orchestration",
        "tests/test_action_log_job.py")
    assert hit["status"] == VERIFIED


def test_build_claims_sibling_prefix_false_positive_end_to_end():
    # 최종 수용 검사관 재현(★ 자기 검증 — 반드시 검사관 원본 재현 그대로 실행):
    # jobs.action_log의 public 표면이 바뀌었는데 PR이 형제 job인
    # test_action_log_quality_job.py만 건드리고 진짜 대응 test_action_log_job.py는
    # 손대지 않은 상황을 build_claims 층위에서 그대로 재현한다. jobs.action_log
    # 배지는 verified가 아니라 warning("테스트 없음")이어야 한다.
    d = _delta()
    d["changed_modules"] = [{
        "id": "jobs.action_log",
        "path": "autoresearch/jobs/action_log.py",
        "stage": "orchestration",
        "symbols_changed": [{"name": "run_action_log_job", "change": "signature", "line": 1}],
        "public_surface_changed": True,
    }]
    d["tests"]["files"] = ["tests/test_action_log_quality_job.py"]
    claims = build_claims(d)
    hit = [c for c in claims if c["module"] == "jobs.action_log" and "테스트" in c["text"]]
    assert hit and hit[0]["status"] == WARNING
    assert hit[0]["status"] != VERIFIED
    assert "대응 테스트 변경이 없습니다" in hit[0]["text"]

    # 동시에: 같은 PR이 진짜 대응 테스트 test_action_log_job.py를 건드리면
    # verified가 나와야 한다(안전 방향 과탐이 아님을 함께 확인).
    d2 = _delta()
    d2["changed_modules"] = d["changed_modules"]
    d2["tests"]["files"] = ["tests/test_action_log_job.py"]
    claims2 = build_claims(d2)
    hit2 = [c for c in claims2 if c["module"] == "jobs.action_log" and "테스트" in c["text"]]
    assert hit2 and hit2[0]["status"] == VERIFIED


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
    assert removed_nonbreaking and removed_nonbreaking[0]["status"] == INFO \
        and "필드 제거" in removed_nonbreaking[0]["text"]
