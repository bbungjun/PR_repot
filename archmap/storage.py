"""파일 기반 저장소. Phase 0은 로컬 디렉터리, 필요 시 관리형으로 교체한다."""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path

# 경로 구성요소로 쓰이는 외부 입력(repo, revision, head_sha, pr)에 대한 화이트리스트.
# 슬래시·역슬래시·"." 단독·".." 등 경로 탈출에 쓰일 수 있는 문자를 모두 배제한다.
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_component(value, field_name: str) -> str:
    """외부 입력을 경로 구성요소로 쓰기 전에 검증한다.

    화이트리스트(영문/숫자/밑줄/점/하이픈)를 벗어나거나 "."·".."인 경우
    경로 주입(디렉터리 탈출)으로 간주하고 ValueError를 던진다.
    """
    s = str(value)
    if s in ("", ".", "..") or not _SAFE_COMPONENT.match(s):
        raise ValueError(f"허용되지 않는 {field_name} 값입니다: {value!r}")
    return s


def _atomic_write_text(path: Path, content: str) -> None:
    """같은 디렉터리에 임시 파일을 쓴 뒤 os.replace로 치환해 원자적으로 저장한다.

    프로세스가 중간에 죽거나 동시 쓰기가 겹치더라도, 이 함수가 성공적으로
    반환하기 전까지 대상 파일은 이전 내용(혹은 부재) 그대로 유지된다 —
    부분적으로 쓰인 내용이 읽히는 일이 없다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _safe_path(self, *parts: str) -> Path:
        """검증된 구성요소로 경로를 만들고, 저장소 루트 하위인지 한 번 더 확인한다."""
        path = self.root.joinpath(*parts)
        root_resolved = self.root.resolve()
        # 각 구성요소는 이미 화이트리스트로 검증됐지만, 방어적으로
        # 최종 경로가 여전히 루트 하위에 있는지 확인한다.
        if not path.resolve().is_relative_to(root_resolved):
            raise ValueError("저장소 루트를 벗어난 경로입니다.")
        return path

    # --- manifests -------------------------------------------------
    def save_manifest(self, arch: dict) -> None:
        repo = _validate_component(arch["repo"], "repo")
        revision = _validate_component(arch["revision"], "revision")
        latest = self._safe_path("manifests", f"{repo}.json")
        history = self._safe_path("manifests", "history", repo, f"{revision}.json")
        payload = json.dumps(arch, ensure_ascii=False, indent=2)
        for path in (latest, history):
            _atomic_write_text(path, payload)

    def load_manifests(self) -> dict[str, dict]:
        result = {}
        for path in sorted((self.root / "manifests").glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            result[doc["repo"]] = doc
        return result

    # --- reports ---------------------------------------------------
    def _report_dir(self, repo: str, pr: int) -> Path:
        repo = _validate_component(repo, "repo")
        pr = _validate_component(pr, "pr")
        return self._safe_path("reports", repo, f"pr-{pr}")

    def save_report(self, pr_delta: dict, html: str) -> None:
        _validate_component(pr_delta["head_sha"], "head_sha")
        d = self._report_dir(pr_delta["repo"], pr_delta["pr"])
        _atomic_write_text(d / f'{pr_delta["head_sha"]}.html', html)
        _atomic_write_text(d / "latest.html", html)
        issue = pr_delta.get("issue") or {}
        meta = {"repo": pr_delta["repo"], "pr": pr_delta["pr"],
                "head_sha": pr_delta["head_sha"],
                "issue_title": issue.get("title", ""), "updated": time.time()}
        _atomic_write_text(d / "meta.json", json.dumps(meta, ensure_ascii=False))
        _atomic_write_text(
            d / "pr-delta.json", json.dumps(pr_delta, ensure_ascii=False, indent=2))

    def list_reports(self) -> list[dict]:
        metas = [json.loads(p.read_text(encoding="utf-8"))
                 for p in (self.root / "reports").glob("*/pr-*/meta.json")]
        # updated 내림차순(최신순). 동점 시 파일시스템 glob 순서에 기대지 않도록
        # (repo, pr) 오름차순을 보조 정렬 키로 사용해 결정론적으로 만든다.
        return sorted(metas, key=lambda m: (-m["updated"], str(m["repo"]), str(m["pr"])))

    def load_report_html(self, repo: str, pr: int) -> str | None:
        path = self._report_dir(repo, pr) / "latest.html"
        return path.read_text(encoding="utf-8") if path.exists() else None
