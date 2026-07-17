"""pr-delta 사실로부터 검증 배지를 결정론적으로 부여한다.

핵심 불변식: verified 상태는 이 모듈만 부여한다. 서술기(LLM) 출력은
어떤 경로로도 여기를 거치지 않으므로 "자신 있게 틀린 검증"이 구조적으로 불가능하다.
"""
from __future__ import annotations

VERIFIED = "verified"
WARNING = "warning"
NARRATED = "narrated"
# 스펙 §7은 VERIFIED(초록)를 "X 계약/스키마 불변", "하위호환", "테스트 커버됨"
# 세 형태에만 인가한다. 버전 상수 bump(breaking=False)나 스키마 필드 추가는 이
# 세 형태 중 어디에도 속하지 않는다 — extractor의 breaking 플래그는 §8 규칙으로
# 실제 판정된 적이 없어(값 변경 시 하드코딩 False) 이를 VERIFIED로 표기하면
# "이 변경은 안전하다"는 근거 없는 보증이 된다(Critical B). 그렇다고 매 bump마다
# WARNING을 띄우면 "애매하면 경고"가 노이즈로 퇴색한다. INFO는 초록도 경고도
# 아닌 중립 사실 표기 — 리뷰어에게 사실은 보여주되 안전을 보증하지 않는다.
INFO = "info"


def _claim(status: str, text: str, module: str | None = None, line: int | None = None) -> dict:
    return {"status": status, "text": text, "module": module, "line": line}


def _singularize(token: str) -> str:
    # 아주 단순한 단복수 정규화: 끝의 "s"를 벗긴다. 길이 3 이하 토큰은 건드리지
    # 않는다("as"·"is" 같은 짧은 토큰이 "a"·"i"로 뭉개지는 것을 막는다).
    # "jobs"→"job", "features"→"feature", "logs"→"log" 등 이 판정에 필요한
    # 케이스에는 충분하고, 정교한 형태소 분석은 이 정도 판정에 과하다.
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def _test_file_covers(module_id: str, test_files: list[str]) -> bool:
    # 이 판정은 이미 네 번 고쳐졌고, 매번 반대 방향 회귀를 냈다:
    #   1) 부분 문자열 대조("log" in "action_logs_daily") → 짧은 모듈명이 무관한
    #      테스트 파일명에 우연히 포함되어 허위 초록.
    #   2) 단일 토큰 완전 일치(mod_name in stem.split("_")) → "llm_generator"처럼
    #      언더스코어로 여러 단어를 잇는 모듈명은 토큰 리스트의 원소가 될 수 없어
    #      영원히 매칭 실패(허위 warning 회귀).
    #   3) 연속 부분열 대조(마지막 구성요소만) → 패키지명을 안 봐서 "schema.py"
    #      같은 동명 파일이 여러 스테이지에 있으면 서로의 테스트로 오매칭된다
    #      (action_logs.schema가 무관한 test_virtual_users_schema.py로 "커버됨"
    #      오판 — 허위 초록).
    #   4) 패키지 토큰 하나라도 겹치면 통과 → 두 갈래 반대 방향 회귀를 동시에 냄:
    #      (a) "youtube" 토큰이 youtube_collection 패키지와 jobs.youtube_* 테스트에
    #          공통으로 등장해, youtube_collection.backfill이 무관한
    #          test_youtube_backfill_job.py(jobs.youtube_backfill의 테스트)로
    #          "커버됨" 오판 — 허위 초록.
    #      (b) "jobs" != "job"(단수) 문자열 불일치로 jobs.* 스테이지 모듈 전부가
    #          진짜 대응 테스트(test_action_log_job.py 등)가 있어도 영원히
    #          warning — 안전 방향이지만 문구가 사실과 반대("대응 테스트 변경이
    #          없습니다"인데 있음)이고 airflow가 소비하는 표면 전체가 초록을
    #          못 받는 회귀.
    # 그래서 이번에는 (a)(b)를 동시에 잡기 위해 두 조건을 모두 요구하되, 3)의
    # 조건(b)를 다시 설계한다:
    #   (a) 모듈명(마지막 구성요소)이 stem 토큰열에 연속 부분열로 나타나야 한다
    #       (기존 조건, 그대로 유지 — 단복수 정규화를 적용하지 않는다. 짧은
    #       토큰의 우연한 단복수 일치로 1)이 재발하는 것을 막기 위해서다. 예:
    #       모듈 "action_logs.log"의 mod_token "log"가 무관한 테스트
    #       "action_logs_daily"의 "logs"(패키지 접두사, 정규화하면 "log")에
    #       엄밀 매칭 없이 우연히 걸리면 허위 초록이 재발한다).
    #   (b) 패키지 구성요소는 **가장 가까운 상위 디렉터리 하나만**(마지막을
    #       제외한 나머지 중 최後 원소, "_" 토큰화 후 단복수 정규화) 본다 —
    #       "src.features.feature_builder"처럼 3단 모듈 id에서 최상위 "src"는
    #       (autoresearch/ 아래 모듈은 이미 최상위가 벗겨지는 것과 대칭적으로)
    #       테스트 파일명에 반영되지 않는 관례적 상위 디렉터리이므로 대조에서
    #       제외한다. 그 패키지 구성요소의 **토큰 전부**(단복수 정규화 후)가
    #       stem 토큰열(마찬가지로 정규화)의 부분집합이어야 한다 — "토큰 하나만
    #       겹쳐도 통과"였던 4)를 "전부 겹쳐야 통과"로 좁혀 (a) 오매칭을 막는다.
    #       "youtube_collection"은 {youtube, collection} 전부가 필요한데
    #       "youtube_backfill_job"에는 "collection"이 없어 탈락하고, "jobs"는
    #       정규화하면 {job} 하나뿐이라 "action_log_job"에 있는 "job"만으로
    #       충분히 통과한다.
    # 패키지 구성요소가 없는(점이 없는) 최상위 모듈 id는 (b)를 건너뛰고 (a)만으로
    # 판정한다 — 대조할 패키지명 자체가 없다.
    parts = module_id.split(".")
    mod_tokens = parts[-1].split("_")
    pkg_tokens = {_singularize(tok) for tok in parts[-2].split("_")} if len(parts) > 1 else set()
    n = len(mod_tokens)
    for f in test_files:
        stem = f.rsplit("/", 1)[-1].removeprefix("test_").removesuffix(".py")
        stem_tokens = stem.split("_")
        mod_matched = any(
            stem_tokens[i:i + n] == mod_tokens for i in range(len(stem_tokens) - n + 1))
        if not mod_matched:
            continue
        if not pkg_tokens:
            return True
        normalized_stem_tokens = {_singularize(tok) for tok in stem_tokens}
        if pkg_tokens <= normalized_stem_tokens:
            return True
    return False


def build_claims(pr_delta: dict) -> list[dict]:
    claims: list[dict] = []
    for c in pr_delta["unchanged_contracts"]:
        # 최종 수용 검사관 지적(근본 원인): 추출기가 실제로 아는 것은 "버전
        # 상수 값과 스키마 필드 목록(이름·타입)이 안 바뀌었다"는 사실뿐이다.
        # 옛 문구 "저장·생성 계약이 바뀌지 않았습니다"는 이보다 훨씬 넓은
        # 보증을 단언한다 — validator 강화(예: watch_time_sec >= 0 → >= 1)처럼
        # 필드 목록·타입은 그대로인 채 계약의 의미가 바뀌는 변경도 이 문구
        # 아래에서는 여전히 초록으로 뜬다. schema.py의 validator를 계속 쫓아
        # 추출 범위를 넓히는 것은 바닥이 없으므로(§7 취지), 검증된 사실
        # 범위로 문구를 좁힌다 — "계약이 바뀌지 않았다"는 포괄 보증 대신
        # "버전 상수 값과 필드 목록이 그대로"라는 좁고 참인 사실만 말한다.
        claims.append(_claim(
            VERIFIED,
            f'{c["const"]} = "{c["value"]}" 값 불변 — 이 모듈의 버전 상수 값과 '
            f'스키마 필드 목록(이름·타입)이 그대로입니다',
            c["module"], c.get("line")))
    for v in pr_delta["version_changes"]:
        # breaking=True는 §7 세 형태 밖이라도 "애매하면 경고" 원칙으로 WARNING.
        # breaking=False는 VERIFIED를 인가받지 못했으므로(§7) INFO — 사실은
        # 보여주되 "안전하다"는 보증은 하지 않는다.
        status = WARNING if v["breaking"] else INFO
        label = "파괴적 변경" if v["breaking"] else "비파괴 변경"
        claims.append(_claim(
            status, f'{v["const"]}: {v["from"]} → {v["to"]} ({label})',
            v["module"], v.get("line")))
    for s in pr_delta["schema_changes"]:
        # §7의 세 형태에 "필드 추가"는 없다 — breaking=False인 필드 추가도
        # version_changes와 동일한 이유로 VERIFIED가 아니라 INFO.
        status = WARNING if s["breaking"] else INFO
        kind = {"added": "필드 추가", "removed": "필드 제거"}[s["change"]]
        claims.append(_claim(status, f'{s["model"]}.{s["field"]} {kind}', s["module"]))
    for x in pr_delta["cross_repo"]:
        if x["breaking"]:
            claims.append(_claim(
                WARNING, f'{x["contract"]} 파괴적 영향({x["impact"]}) — 소비자 전환 PR 필요'))
        else:
            claims.append(_claim(VERIFIED, f'{x["contract"]} 하위호환 영향({x["impact"]})'))
    # breaking_signatures는 스키마 required가 아니다(추출기가 새로 채우기 시작한
    # 필드). 없는 델타(기존 픽스처 등)에서도 하위호환되도록 .get()으로 접근한다.
    # 이 항목들은 정의상 하위호환되지 않는 공개 심볼 변경이므로 항상 WARNING —
    # 이 판정 규칙만으로 verified가 나올 일은 없다(핵심 불변식 유지).
    for b in pr_delta.get("breaking_signatures", []):
        claims.append(_claim(
            WARNING,
            f'{b["name"]} 파괴적 변경 — 공개 심볼의 시그니처·종류가 하위호환되지 않게 '
            f'바뀌었거나 제거되었습니다 (모듈: {b["module"]})',
            b["module"]))
    test_files = pr_delta["tests"]["files"]
    for m in pr_delta["changed_modules"]:
        if not m["public_surface_changed"]:
            continue
        if _test_file_covers(m["id"], test_files):
            claims.append(_claim(VERIFIED, "테스트 커버됨 — 대응 테스트 파일이 함께 변경되었습니다", m["id"]))
        else:
            claims.append(_claim(WARNING, "테스트 없음 — public 표면이 바뀌었으나 대응 테스트 변경이 없습니다", m["id"]))
    return claims
