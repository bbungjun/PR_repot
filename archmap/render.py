"""고정 HTML 템플릿의 사실 슬롯을 채워 리포트를 조립한다. UI 비종속."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from archmap.verify import build_claims

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
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
    template = _env.get_template("pr_report.html.j2")
    return template.render(architecture=architecture, pr_delta=pr_delta,
                           claims=claims, changed_modules=changed_modules,
                           hit_stages=hit_stages)
