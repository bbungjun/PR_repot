"""고정 HTML 템플릿의 사실 슬롯을 채워 리포트를 조립한다. UI 비종속."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from archmap.verify import NARRATED, VERIFIED, WARNING, build_claims

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# status -> 한국어 라벨의 명시적 매핑. 예전 템플릿은 status == "verified"가
# 아니면 전부 "주의"로 표시했는데, verify.py에는 이미 NARRATED 상수가
# 선언되어 있어(Phase 2의 GLM 서술 claim용) 그 관습이 그대로였다면 서술을
# 경고로 오표기했을 것이다. 매핑을 코드로 명시하고, 아래 render_report에서
# 매핑에 없는 status를 만나면 조용히 "주의"로 넘기지 않고 렌더를 실패시켜
# 이 불변식을 구조적으로 강제한다.
#
# 핵심 불변식: narrated는 절대 "검증됨"으로 표시되지 않는다 — verified 배지는
# archmap/verify.py의 build_claims만 부여하고(pr-delta 사실 기반), 렌더러는
# 그 status를 표시만 한다.
STATUS_LABELS = {
    VERIFIED: "검증됨",
    WARNING: "주의",
    NARRATED: "서술",
}


class UnknownClaimStatusError(ValueError):
    """claim의 status가 STATUS_LABELS에 없을 때 던진다.

    status 종류가 늘어날 때(예: Phase 2의 "narrated") 이 매핑을 갱신하지
    않으면 예전에는 조용히 "주의"로 뭉뚱그려졌다. 그 대신 여기서 렌더를
    실패시켜, 새 status를 매핑에 등록하는 일을 선택이 아니라 필수로 만든다.
    """
# select_autoescape(["html"])는 템플릿 파일명이 ".html"로 끝나는지만 검사한다.
# 실제 템플릿 파일명은 "pr_report.html.j2"로 ".j2"로 끝나 판정이 항상 False가
# 되어 autoescape가 꺼진 채로 렌더링되었다(HTML 인젝션 가능). 이 렌더러는
# HTML 템플릿만 렌더하므로 파일명 판정에 기대지 않고 무조건 켠다.
_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR), autoescape=True)


def anchor_url(repo_url: str, sha: str, path: str, line: int | None) -> str:
    url = f"{repo_url}/blob/{sha}/{path}"
    return f"{url}#L{line}" if line is not None else url


def render_report(architecture: dict, pr_delta: dict) -> str:
    repo_url = architecture.get("repo_url", "")
    sha = pr_delta["head_sha"]
    path_by_module = {m["id"]: m["path"] for m in architecture["modules"]}

    claims = build_claims(pr_delta)
    for c in claims:
        if c["status"] not in STATUS_LABELS:
            raise UnknownClaimStatusError(f"알 수 없는 claim status입니다: {c['status']!r}")
        c["status_label"] = STATUS_LABELS[c["status"]]
        path = path_by_module.get(c["module"]) if c["module"] else None
        if repo_url and path:
            c["anchor"] = anchor_url(repo_url, sha, path, c["line"])
            c["anchor_label"] = f'{path.rsplit("/", 1)[-1]}#L{c["line"]}' if c["line"] else path
        else:
            c["anchor"] = None

    changed_modules = []
    for m in pr_delta["changed_modules"]:
        line = next((s.get("line") for s in m["symbols_changed"] if s.get("line")), None)
        anchor = anchor_url(repo_url, sha, m["path"], line) if repo_url else None
        changed_modules.append({**m, "anchor": anchor})

    hit_stages = {m["stage"] for m in pr_delta["changed_modules"]}
    # architecture.json과 pr-delta.json은 서로 독립적으로 생성되는 산출물이라
    # 실제로 어긋날 수 있다. changed_modules가 architecture.stages에 없는
    # stage를 가리키면, 예전에는 흐름 스트립에서 하이라이트가 경고 없이 통째로
    # 누락됐다(사실이 조용히 유실됨). 그런 stage를 따로 모아 눈에 띄게
    # 표시한다 — 없는 사실을 지어내지 않고, 있는 불일치를 숨기지 않는다.
    unknown_stages = sorted(hit_stages - set(architecture["stages"]))
    template = _env.get_template("pr_report.html.j2")
    return template.render(architecture=architecture, pr_delta=pr_delta,
                           claims=claims, changed_modules=changed_modules,
                           hit_stages=hit_stages, unknown_stages=unknown_stages)
