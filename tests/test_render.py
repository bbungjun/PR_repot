import json
from pathlib import Path

from archmap.render import anchor_url, render_report

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_anchor_url():
    assert anchor_url("https://github.com/SKYAHO/Autoresearch", "3be5fae",
                      "autoresearch/action_logs/schema.py", 16) == \
        "https://github.com/SKYAHO/Autoresearch/blob/3be5fae/autoresearch/action_logs/schema.py#L16"


def test_report_contains_facts_and_anchors():
    html = render_report(_load("architecture_120.json"), _load("pr_delta_120.json"))
    assert "PR #120" in html
    assert "후보 목록을 프롬프트에 명시" in html          # 이슈 제목
    assert "ACTION_LOG_SCHEMA_VERSION" in html            # 검증됨 주장
    assert "schema.py#L16" in html                        # file:line 앵커
    assert "action_log_ctr_v4" in html                    # 버전 변경 사실
    assert 'badge badge-verified' in html
    assert 'badge badge-warning' not in html   # CSS 클래스 정의가 아니라 렌더된 배지를 검사


def test_flow_strip_highlights_hit_stages():
    html = render_report(_load("architecture_120.json"), _load("pr_delta_120.json"))
    assert 'class="stage hit">action_logs' in html
    assert 'class="stage hit">virtual_users' not in html


def test_narration_slot_is_placeholder_in_phase0():
    html = render_report(_load("architecture_120.json"), _load("pr_delta_120.json"))
    assert "narration-slot" in html and "Phase 2" in html
