import json
from pathlib import Path

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
