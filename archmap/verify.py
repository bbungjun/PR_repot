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
    # 모듈 id의 마지막 구성요소만 대조한다 — 패키지명 대조는 같은 패키지의
    # 무관한 테스트 변경을 "커버됨"으로 오판한다(허위 초록 금지).
    # 대조는 부분 문자열이 아니라 단어 경계(토큰) 단위로 한다: mod_name과 stem을
    # 각각 "_" 기준으로 토큰화한 뒤, mod_name의 토큰 리스트가 stem의 토큰 리스트에
    # "연속된 부분열(contiguous sublist)"로 나타날 때만 커버된 것으로 본다.
    # 단일 토큰과의 완전 일치 비교(mod_name in stem.split("_"))는 mod_name 자체가
    # "llm_generator"처럼 언더스코어로 여러 단어를 잇는 경우, 그 문자열이 토큰
    # 리스트의 원소가 될 수 없어 영원히 매칭에 실패한다(허위 warning 회귀).
    # 부분 문자열 대조("log" in "action_logs_daily")는 반대로 짧은 모듈명이
    # 무관한 테스트 파일명에 우연히 포함되는 경우까지 커버됨으로 오판해 허위
    # 초록을 만든다. 연속 부분열 대조는 두 문제를 모두 피한다.
    mod_tokens = module_id.rsplit(".", 1)[-1].split("_")
    n = len(mod_tokens)
    for f in test_files:
        stem = f.rsplit("/", 1)[-1].removeprefix("test_").removesuffix(".py")
        stem_tokens = stem.split("_")
        if any(stem_tokens[i:i + n] == mod_tokens for i in range(len(stem_tokens) - n + 1)):
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
