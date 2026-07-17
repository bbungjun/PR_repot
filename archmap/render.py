"""고정 HTML 템플릿의 사실 슬롯을 채워 리포트를 조립한다. UI 비종속."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from archmap.verify import build_claims

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR),
                   autoescape=select_autoescape(["html"]))


def anchor_url(repo_url: str, sha: str, path: str, line: int | None) -> str:
    url = f"{repo_url}/blob/{sha}/{path}"
    return f"{url}#L{line}" if line else url


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
        changed_modules.append({**m, "anchor": anchor_url(repo_url, sha, m["path"], line)})

    hit_stages = {m["stage"] for m in pr_delta["changed_modules"]}
    template = _env.get_template("pr_report.html.j2")
    return template.render(architecture=architecture, pr_delta=pr_delta,
                           claims=claims, changed_modules=changed_modules,
                           hit_stages=hit_stages)
