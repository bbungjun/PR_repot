"""archmap.ui의 순수 함수(streamlit 비의존)에 대한 단위 테스트.

streamlit 호출부(st.tabs, st.markdown 등)는 여기서 테스트하지 않는다 — 그것은
수동 스모크(브리프 Step 6-4)로 확인한다.
"""
import json
from pathlib import Path

from archmap.ui import (
    format_report_label,
    format_version_consts,
    group_modules_by_stage,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- group_modules_by_stage ---------------------------------------------

def test_group_modules_by_stage_groups_fixture_modules():
    arch = _load("architecture_120.json")
    by_stage = group_modules_by_stage(arch["modules"])
    assert list(by_stage.keys()) == ["action_logs"]
    assert [m["id"] for m in by_stage["action_logs"]] == [
        "action_logs.schema", "action_logs.llm_generator", "action_logs.daily",
    ]


def test_group_modules_by_stage_preserves_first_seen_stage_order():
    modules = [
        {"id": "a", "stage": "s2"},
        {"id": "b", "stage": "s1"},
        {"id": "c", "stage": "s2"},
    ]
    by_stage = group_modules_by_stage(modules)
    assert list(by_stage.keys()) == ["s2", "s1"]
    assert [m["id"] for m in by_stage["s2"]] == ["a", "c"]
    assert [m["id"] for m in by_stage["s1"]] == ["b"]


def test_group_modules_by_stage_empty_list_returns_empty_dict():
    assert group_modules_by_stage([]) == {}


# --- format_version_consts ------------------------------------------------

def test_format_version_consts_joins_key_value_pairs_from_fixture():
    arch = _load("architecture_120.json")
    schema_module = next(m for m in arch["modules"] if m["id"] == "action_logs.schema")
    assert format_version_consts(schema_module["version_consts"]) == (
        "ACTION_LOG_SCHEMA_VERSION=action_log_schema_v1, PROMPT_VERSION=action_log_ctr_v4"
    )


def test_format_version_consts_empty_dict_returns_empty_string():
    assert format_version_consts({}) == ""


def test_format_version_consts_single_entry_has_no_trailing_comma():
    assert format_version_consts({"X": {"value": "v1", "line": 1}}) == "X=v1"


# --- format_report_label --------------------------------------------------

def test_format_report_label_matches_expected_shape():
    meta = {"repo": "Autoresearch", "pr": 120, "head_sha": "3be5fae",
             "issue_title": "후보 목록을 프롬프트에 명시", "updated": 123.0}
    assert format_report_label(meta) == "Autoresearch PR #120 · 후보 목록을 프롬프트에 명시"


def test_format_report_label_empty_issue_title():
    meta = {"repo": "RepoX", "pr": 7, "head_sha": "abc", "issue_title": "", "updated": 1.0}
    assert format_report_label(meta) == "RepoX PR #7 · "
