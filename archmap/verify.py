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


def _test_file_covers(module_id: str, test_files: list[str]) -> bool:
    # 이 판정은 이미 두 번 고쳐졌다(마지막 구성요소만 대조하도록 좁혀졌다가,
    # 스테이지를 넘나드는 오매칭을 냈다):
    #   1) 부분 문자열 대조("log" in "action_logs_daily") → 짧은 모듈명이 무관한
    #      테스트 파일명에 우연히 포함되어 허위 초록.
    #   2) 단일 토큰 완전 일치(mod_name in stem.split("_")) → "llm_generator"처럼
    #      언더스코어로 여러 단어를 잇는 모듈명은 토큰 리스트의 원소가 될 수 없어
    #      영원히 매칭 실패(허위 warning 회귀).
    #   3) 연속 부분열 대조(마지막 구성요소만) → 1)·2)는 해결했으나 패키지명을
    #      보지 않아 "schema.py"·"pipeline.py"처럼 여러 스테이지에 동명 파일이
    #      있으면 서로의 테스트로 오매칭된다(예: action_logs.schema가 무관한
    #      test_virtual_users_schema.py로 "커버됨" 오판 — 허위 초록).
    # 그래서 이번에는 두 조건을 모두 요구한다:
    #   (a) 모듈명(마지막 구성요소)이 stem 토큰열에 연속 부분열로 나타나야 한다
    #       (기존 조건, 유지 — 1)·2) 재발 방지).
    #   (b) 패키지 구성요소(마지막을 제외한 나머지, 각각 "_" 토큰화) 중 최소
    #       하나가 stem 토큰열에 (순서 무관, 부분열 아니어도) 나타나야 한다
    #       — 다른 스테이지 패키지와는 토큰이 겹칠 수 없으므로 3)의 오매칭을 막는다.
    # (b)를 완전 일치가 아니라 "토큰 하나라도 겹침"으로 느슨하게 둔 이유: 실제
    # 파일명 관례가 항상 패키지명을 그대로 쓰지 않는다(예: "action_logs" 패키지의
    # 테스트가 "test_action_log_llm_generator.py"처럼 단수형 "log"를 쓰는 경우가
    # 있다). 패키지 토큰 전부 일치를 요구하면 이런 정당한 커버를 허위 경고로
    # 놓친다. 토큰 하나(예: "action")만 겹쳐도 같은 패키지 계열임을 강하게
    # 시사하고, 다른 스테이지 패키지명과는 애초에 토큰이 겹치지 않으므로 허위
    # 초록 위험 없이 이 완화가 안전하다.
    # 패키지 구성요소가 없는(점이 없는) 최상위 모듈 id는 (b)를 건너뛰고 (a)만으로
    # 판정한다 — 대조할 패키지명 자체가 없다.
    parts = module_id.split(".")
    mod_tokens = parts[-1].split("_")
    pkg_tokens = {tok for p in parts[:-1] for tok in p.split("_")}
    n = len(mod_tokens)
    for f in test_files:
        stem = f.rsplit("/", 1)[-1].removeprefix("test_").removesuffix(".py")
        stem_tokens = stem.split("_")
        mod_matched = any(
            stem_tokens[i:i + n] == mod_tokens for i in range(len(stem_tokens) - n + 1))
        if not mod_matched:
            continue
        if not pkg_tokens or pkg_tokens & set(stem_tokens):
            return True
    return False


def build_claims(pr_delta: dict) -> list[dict]:
    claims: list[dict] = []
    for c in pr_delta["unchanged_contracts"]:
        claims.append(_claim(
            VERIFIED, f'{c["const"]} = "{c["value"]}" 불변 — 저장·생성 계약이 바뀌지 않았습니다',
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
