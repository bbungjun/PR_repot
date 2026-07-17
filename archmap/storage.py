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

# 경로 구성요소 하나의 최대 바이트 길이.
#
# 화이트리스트는 "허용된 문자"만 검사하고 "길이"는 검사하지 않았다. 그 결과
# 문자는 안전하지만 파일시스템 컴포넌트 한도를 넘는 값이 검증을 통과한 뒤,
# Path.resolve()/Path.exists()/os.stat()이나 _atomic_write_text가 쓰는
# tempfile.mkstemp에서 OSError(Errno 36, "File name too long")를 던졌다.
# OSError는 ValueError가 아니므로 api.py의 `except ValueError` 방어를 그대로
# 통과해 500으로 유출됐다.
#
# Linux의 파일명 컴포넌트 한도(NAME_MAX)는 255바이트다. 하지만 이 컴포넌트는
# 그대로 파일명이 되지 않고 ".json"/".html" 접미사(최대 5바이트)가 붙거나,
# _atomic_write_text가 만드는 임시 파일명(".{name}.{8자 난수}.tmp", 실행으로
# 실측한 오버헤드 14바이트)의 일부가 된다. 실측 결과 이 오버헤드까지 반영한
# 실제 안전 한계는 255 - 5 - 14 = 236바이트였다(예: manifest의 repo가 236바이트면
# 저장에 성공하고 237바이트면 OSError가 발생함을 실행으로 확인). 여기에 안전
# 마진을 두어 200바이트로 제한한다 — 정당한 입력(저장소 이름, 커밋 SHA 등)은
# 이 한계에 한참 못 미치므로 영향이 없다.
_MAX_COMPONENT_BYTES = 200


def _validate_component(value, field_name: str) -> str:
    """외부 입력을 경로 구성요소로 쓰기 전에 검증한다.

    화이트리스트(영문/숫자/밑줄/점/하이픈)를 벗어나거나 "."·".."인 경우,
    또는 파일시스템 컴포넌트 한도에 근접할 만큼 긴 경우 경로 주입(디렉터리
    탈출) 혹은 파일시스템 오류 유발로 간주하고 ValueError를 던진다.
    """
    s = str(value)
    if s in ("", ".", "..") or not _SAFE_COMPONENT.match(s):
        raise ValueError(f"허용되지 않는 {field_name} 값입니다: {value!r}")
    # 화이트리스트가 ASCII만 허용하므로 문자 수와 바이트 수가 같지만, 의도를
    # 명확히 하고 방어적으로 두기 위해 바이트 길이로 잰다.
    byte_len = len(s.encode("utf-8"))
    if byte_len > _MAX_COMPONENT_BYTES:
        raise ValueError(
            f"{field_name} 값이 너무 깁니다(최대 {_MAX_COMPONENT_BYTES}바이트, "
            f"실제 {byte_len}바이트)"
        )
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
        # JSON Schema draft 2020-12의 "integer" 타입은 소수부가 0인 숫자(예:
        # 3.0)도 통과시킨다. 그래서 pr-delta 스키마가 "pr": {"type": "integer"}
        # 여도 pr: 3.0이 계약 검증을 통과해 여기까지 도달할 수 있고, json.loads는
        # 이를 파이썬 float 3.0으로 역직렬화한다. 이 값을 그대로 받아들이면
        # 리포트가 "pr-3.0" 디렉터리에 저장되는데, API가 반환하는 report_url과
        # GET /reports/{repo}/{pr}(파라미터를 int로 선언)은 둘 다 정수 형식을
        # 기대하므로 "3.0"에 영영 도달하지 못한다 — 서버가 스스로 반환한 링크가
        # 깨지는 최악의 실패 모드. bool은 int의 서브클래스라 isinstance(pr, int)
        # 만으로는 True/False가 통과해버리므로 별도로 배제한다.
        if isinstance(pr, bool) or not isinstance(pr, int):
            raise ValueError(f"pr은 정수여야 합니다(실제 {pr!r})")
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
