"""pr-delta 사실로부터 검증 배지를 결정론적으로 부여한다.

핵심 불변식: verified 상태는 이 모듈만 부여한다. 서술기(LLM) 출력은
어떤 경로로도 여기를 거치지 않으므로 "자신 있게 틀린 검증"이 구조적으로 불가능하다.
"""
from __future__ import annotations

VERIFIED = "verified"
WARNING = "warning"
NARRATED = "narrated"


def _claim(status: str, text: str, module: str | None = None, line: int | None = None) -> dict:
    return {"status": status, "text": text, "module": module, "line": line}


def _test_file_covers(module_id: str, test_files: list[str]) -> bool:
    # 모듈 id의 마지막 구성요소만 대조한다 — 패키지명 대조는 같은 패키지의
    # 무관한 테스트 변경을 "커버됨"으로 오판한다(허위 초록 금지).
    mod_name = module_id.rsplit(".", 1)[-1]
    for f in test_files:
        stem = f.rsplit("/", 1)[-1].removeprefix("test_").removesuffix(".py")
        if mod_name in stem:
            return True
    return False


def build_claims(pr_delta: dict) -> list[dict]:
    claims: list[dict] = []
    for c in pr_delta["unchanged_contracts"]:
        claims.append(_claim(
            VERIFIED, f'{c["const"]} = "{c["value"]}" 불변 — 저장·생성 계약이 바뀌지 않았습니다',
            c["module"], c.get("line")))
    for v in pr_delta["version_changes"]:
        status = WARNING if v["breaking"] else VERIFIED
        label = "파괴적 변경" if v["breaking"] else "비파괴 변경"
        claims.append(_claim(
            status, f'{v["const"]}: {v["from"]} → {v["to"]} ({label})',
            v["module"], v.get("line")))
    for s in pr_delta["schema_changes"]:
        status = WARNING if s["breaking"] else VERIFIED
        kind = {"added": "필드 추가", "removed": "필드 제거"}[s["change"]]
        claims.append(_claim(status, f'{s["model"]}.{s["field"]} {kind}', s["module"]))
    for x in pr_delta["cross_repo"]:
        if x["breaking"]:
            claims.append(_claim(
                WARNING, f'{x["contract"]} 파괴적 영향({x["impact"]}) — 소비자 전환 PR 필요'))
        else:
            claims.append(_claim(VERIFIED, f'{x["contract"]} 하위호환 영향({x["impact"]})'))
    test_files = pr_delta["tests"]["files"]
    for m in pr_delta["changed_modules"]:
        if not m["public_surface_changed"]:
            continue
        if _test_file_covers(m["id"], test_files):
            claims.append(_claim(VERIFIED, "테스트 커버됨 — 대응 테스트 파일이 함께 변경되었습니다", m["id"]))
        else:
            claims.append(_claim(WARNING, "테스트 없음 — public 표면이 바뀌었으나 대응 테스트 변경이 없습니다", m["id"]))
    return claims
