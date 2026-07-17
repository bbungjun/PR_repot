"""파일 기반 저장소. Phase 0은 로컬 디렉터리, 필요 시 관리형으로 교체한다."""
from __future__ import annotations

import json
import time
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    # --- manifests -------------------------------------------------
    def save_manifest(self, arch: dict) -> None:
        repo = arch["repo"]
        latest = self.root / "manifests" / f"{repo}.json"
        history = self.root / "manifests" / "history" / repo / f'{arch["revision"]}.json'
        for path in (latest, history):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(arch, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_manifests(self) -> dict[str, dict]:
        result = {}
        for path in sorted((self.root / "manifests").glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            result[doc["repo"]] = doc
        return result

    # --- reports ---------------------------------------------------
    def _report_dir(self, repo: str, pr: int) -> Path:
        return self.root / "reports" / repo / f"pr-{pr}"

    def save_report(self, pr_delta: dict, html: str) -> None:
        d = self._report_dir(pr_delta["repo"], pr_delta["pr"])
        d.mkdir(parents=True, exist_ok=True)
        (d / f'{pr_delta["head_sha"]}.html').write_text(html, encoding="utf-8")
        (d / "latest.html").write_text(html, encoding="utf-8")
        issue = pr_delta.get("issue") or {}
        meta = {"repo": pr_delta["repo"], "pr": pr_delta["pr"],
                "head_sha": pr_delta["head_sha"],
                "issue_title": issue.get("title", ""), "updated": time.time()}
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        (d / "pr-delta.json").write_text(
            json.dumps(pr_delta, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_reports(self) -> list[dict]:
        metas = [json.loads(p.read_text(encoding="utf-8"))
                 for p in (self.root / "reports").glob("*/pr-*/meta.json")]
        return sorted(metas, key=lambda m: m["updated"], reverse=True)

    def load_report_html(self, repo: str, pr: int) -> str | None:
        path = self._report_dir(repo, pr) / "latest.html"
        return path.read_text(encoding="utf-8") if path.exists() else None
