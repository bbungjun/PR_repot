import json
import time
from pathlib import Path

import pytest

from archmap.storage import Store

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_manifest_roundtrip(tmp_path):
    store = Store(tmp_path)
    arch = _load("architecture_120.json")
    store.save_manifest(arch)
    assert store.load_manifests()["Autoresearch"]["revision"] == "3be5fae"


def test_manifest_history_kept(tmp_path):
    store = Store(tmp_path)
    arch = _load("architecture_120.json")
    store.save_manifest(arch)
    arch2 = dict(arch, revision="bbbbbbb")
    store.save_manifest(arch2)
    assert store.load_manifests()["Autoresearch"]["revision"] == "bbbbbbb"
    history = tmp_path / "manifests" / "history" / "Autoresearch"
    assert {p.stem for p in history.glob("*.json")} == {"3be5fae", "bbbbbbb"}


def test_report_roundtrip_and_feed(tmp_path):
    store = Store(tmp_path)
    store.save_report(_load("pr_delta_120.json"), "<html>report</html>")
    assert store.load_report_html("Autoresearch", 120) == "<html>report</html>"
    feed = store.list_reports()
    assert feed[0]["repo"] == "Autoresearch" and feed[0]["pr"] == 120
    assert feed[0]["issue_title"] == "후보 목록을 프롬프트에 명시"


def test_missing_report_returns_none(tmp_path):
    assert Store(tmp_path).load_report_html("Autoresearch", 999) is None


# --- Critical 1: 경로 주입(Path Traversal) 회귀 테스트 ------------------

def test_save_manifest_rejects_relative_traversal(tmp_path):
    store = Store(tmp_path)
    arch = dict(_load("architecture_120.json"), repo="../../../../tmp/evil_manifest")
    with pytest.raises(ValueError):
        store.save_manifest(arch)
    # 저장소 루트 밖에는 어떤 파일도 새로 생성되지 않아야 한다.
    assert list(tmp_path.iterdir()) == []


def test_save_manifest_rejects_traversal_in_revision(tmp_path):
    store = Store(tmp_path)
    arch = dict(_load("architecture_120.json"), revision="../../evil_rev")
    with pytest.raises(ValueError):
        store.save_manifest(arch)


def test_save_report_rejects_absolute_path_repo(tmp_path):
    store = Store(tmp_path)
    pr_delta = dict(_load("pr_delta_120.json"), repo="/tmp/abs_escape")
    with pytest.raises(ValueError):
        store.save_report(pr_delta, "<html>evil</html>")
    assert not Path("/tmp/abs_escape").exists()


def test_save_report_rejects_relative_traversal_repo(tmp_path):
    store = Store(tmp_path)
    pr_delta = dict(_load("pr_delta_120.json"), repo="../../../../tmp/evil_report")
    with pytest.raises(ValueError):
        store.save_report(pr_delta, "<html>evil</html>")
    assert list(tmp_path.iterdir()) == []


def test_save_report_rejects_traversal_in_head_sha(tmp_path):
    store = Store(tmp_path)
    pr_delta = dict(_load("pr_delta_120.json"), head_sha="../../evil_sha")
    with pytest.raises(ValueError):
        store.save_report(pr_delta, "<html>evil</html>")


def test_save_report_rejects_traversal_in_pr(tmp_path):
    store = Store(tmp_path)
    pr_delta = dict(_load("pr_delta_120.json"), pr="../../evil_pr")
    with pytest.raises(ValueError):
        store.save_report(pr_delta, "<html>evil</html>")


def test_load_report_html_rejects_traversal_repo(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(ValueError):
        store.load_report_html("../../../../etc", 1)


def test_load_report_html_rejects_absolute_repo(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(ValueError):
        store.load_report_html("/etc", 1)


def test_valid_inputs_still_work_after_validation(tmp_path):
    # 정당한 입력(브리프의 정상 fixture 값)이 계속 통과해야 한다.
    store = Store(tmp_path)
    store.save_manifest(_load("architecture_120.json"))
    store.save_report(_load("pr_delta_120.json"), "<html>ok</html>")
    assert store.load_manifests()["Autoresearch"]["revision"] == "3be5fae"
    assert store.load_report_html("Autoresearch", 120) == "<html>ok</html>"


# --- Important 2: list_reports 정렬 테스트 -------------------------------

def test_list_reports_sorted_by_updated_desc(tmp_path, monkeypatch):
    store = Store(tmp_path)
    base = _load("pr_delta_120.json")

    clock = {"t": 100.0}
    monkeypatch.setattr(time, "time", lambda: clock["t"])

    clock["t"] = 100.0
    store.save_report(dict(base, repo="RepoA", pr=1), "<html>a1</html>")
    clock["t"] = 300.0
    store.save_report(dict(base, repo="RepoB", pr=2), "<html>b2</html>")
    clock["t"] = 200.0
    store.save_report(dict(base, repo="RepoC", pr=3), "<html>c3</html>")

    feed = store.list_reports()
    ordered = [(m["repo"], m["pr"]) for m in feed]
    assert ordered == [("RepoB", 2), ("RepoC", 3), ("RepoA", 1)]
    assert [m["updated"] for m in feed] == [300.0, 200.0, 100.0]


def test_list_reports_tie_break_deterministic(tmp_path, monkeypatch):
    store = Store(tmp_path)
    base = _load("pr_delta_120.json")

    monkeypatch.setattr(time, "time", lambda: 500.0)
    # 동점(같은 updated) 상황을 만들되, 저장 순서는 정렬 순서와 반대로 한다.
    store.save_report(dict(base, repo="Zeta", pr=9), "<html>z9</html>")
    store.save_report(dict(base, repo="Alpha", pr=5), "<html>a5</html>")
    store.save_report(dict(base, repo="Alpha", pr=1), "<html>a1</html>")

    feed = store.list_reports()
    ordered = [(m["repo"], m["pr"]) for m in feed]
    # updated가 모두 같으므로 보조 키(repo, pr) 오름차순으로 결정론적이어야 한다.
    assert ordered == [("Alpha", 1), ("Alpha", 5), ("Zeta", 9)]


# --- Important 3: 원자적 쓰기 -------------------------------------------

def test_save_report_leaves_no_temp_files_on_success(tmp_path):
    store = Store(tmp_path)
    store.save_report(_load("pr_delta_120.json"), "<html>ok</html>")
    d = tmp_path / "reports" / "Autoresearch" / "pr-120"
    leftovers = [p for p in d.iterdir() if p.name.startswith(".") or p.suffix == ".tmp"]
    assert leftovers == []


def test_meta_json_untouched_when_write_fails_midway(tmp_path, monkeypatch):
    store = Store(tmp_path)
    base = _load("pr_delta_120.json")
    store.save_report(base, "<html>first</html>")
    meta_path = tmp_path / "reports" / "Autoresearch" / "pr-120" / "meta.json"
    original_meta = meta_path.read_text(encoding="utf-8")

    import os as os_module
    real_replace = os_module.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        # meta.json 치환 시점에서 실패를 흉내내 중단시킨다.
        if str(dst).endswith("meta.json"):
            raise OSError("시뮬레이션된 쓰기 실패")
        return real_replace(src, dst)

    monkeypatch.setattr(os_module, "replace", flaky_replace)
    with pytest.raises(OSError):
        store.save_report(dict(base, head_sha="deadbee"), "<html>second</html>")

    # 실패 이후에도 기존 meta.json은 이전의 유효한 내용을 그대로 유지해야 한다.
    assert meta_path.read_text(encoding="utf-8") == original_meta
    parsed = json.loads(meta_path.read_text(encoding="utf-8"))
    assert parsed["head_sha"] == "3be5fae"
    # 실패한 쓰기가 임시 파일을 남기지 않아야 한다.
    leftovers = [p for p in meta_path.parent.iterdir()
                 if p.name.startswith(".") and "meta.json" in p.name]
    assert leftovers == []
