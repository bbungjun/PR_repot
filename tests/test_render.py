import copy
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


def test_issue_title_is_escaped_against_xss():
    # issue.title은 GitHub 이슈 메타데이터에서 온 외부 입력이다. 원본 픽스처는
    # 변경하지 않고 렌더 직전 dict 복사본에서만 페이로드를 주입한다.
    pr_delta = copy.deepcopy(_load("pr_delta_120.json"))
    payload = "<script>alert(1)</script>"
    pr_delta["issue"]["title"] = payload

    html = render_report(_load("architecture_120.json"), pr_delta)

    assert payload not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_changed_module_anchor_omitted_without_repo_url():
    # repo_url이 없는 architecture로 렌더하면 changed_modules 앵커도 claims와
    # 동일하게 링크를 숨겨야 한다. 무조건 anchor_url을 호출하면
    # href="/blob/<sha>/<path>#L<line>" 같은 깨진 상대 링크가 생긴다.
    architecture = copy.deepcopy(_load("architecture_120.json"))
    architecture["repo_url"] = ""

    html = render_report(architecture, _load("pr_delta_120.json"))

    assert 'href="/blob/' not in html
    assert "autoresearch/action_logs/daily.py" in html  # 경로 텍스트는 그대로 노출


# --- Minor: 빈 섹션이 "깨진 리포트"로 보이지 않게 명시적 안내를 표시한다 ------

def test_empty_claims_section_shows_explicit_notice():
    # 계약 변경이 전혀 없는 PR(모든 claim 소스 리스트가 빔)에서는 섹션이
    # 텅 비어 "깨진 건가?"로 보이지 않게, 없다는 사실을 명시해야 한다.
    pr_delta = copy.deepcopy(_load("pr_delta_120.json"))
    pr_delta["unchanged_contracts"] = []
    pr_delta["version_changes"] = []
    pr_delta["schema_changes"] = []
    pr_delta["cross_repo"] = []
    pr_delta["breaking_signatures"] = []
    for m in pr_delta["changed_modules"]:
        m["public_surface_changed"] = False

    html = render_report(_load("architecture_120.json"), pr_delta)

    assert "이 PR에서 감지된 계약 변경이 없습니다." in html
    # 없는 사실을 지어내지 않는다 — 실제 변경 모듈 표는 여전히 채워져 있어야 한다.
    assert "이 PR에서 감지된 변경 모듈이 없습니다." not in html


def test_empty_changed_modules_section_shows_explicit_notice():
    pr_delta = copy.deepcopy(_load("pr_delta_120.json"))
    pr_delta["changed_modules"] = []

    html = render_report(_load("architecture_120.json"), pr_delta)

    assert "이 PR에서 감지된 변경 모듈이 없습니다." in html


def test_warning_badge_renders_for_breaking_change():
    # 원본 pr_delta_120 픽스처는 breaking 변경이 전혀 없어 warning 배지 렌더
    # 경로가 한 번도 검증되지 않는다. version_changes의 breaking 플래그만 뒤집은
    # 복사본으로 verified/warning이 섞인 케이스를 만든다.
    pr_delta = copy.deepcopy(_load("pr_delta_120.json"))
    pr_delta["version_changes"][0]["breaking"] = True

    html = render_report(_load("architecture_120.json"), pr_delta)

    assert 'class="claim warning"' in html
    assert 'class="badge badge-warning"' in html
    assert "주의" in html
    assert 'class="badge badge-verified"' in html  # unchanged_contracts는 여전히 verified
