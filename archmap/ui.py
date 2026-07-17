"""Streamlit 웹 UI — [전체 맵] · [PR 리포트 피드]. 템플릿은 UI 비종속(§4-④).

streamlit에 의존하지 않는 순수 함수(group_modules_by_stage, format_version_consts,
format_report_label)는 tests/test_ui.py에서 실제 입력·출력으로 단위 테스트한다.
streamlit 호출부(st.tabs, st.markdown 등)는 수동 스모크로 확인한다(브리프 Step 6-4).

main()은 모듈 레벨에서 즉시 실행하지 않는다 — import 시 UI 전체가 실행되는 것을
막기 위해 `if __name__ == "__main__":` 가드 안에 둔다. streamlit은 대상 스크립트를
`__main__`으로 실행하므로 `uv run streamlit run archmap/ui.py`는 이 가드를 그대로
통과해 정상 동작한다(수동 검증으로 실측 확인).
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from archmap.storage import Store


def group_modules_by_stage(modules: list[dict]) -> dict[str, list[dict]]:
    """모듈 리스트를 stage 필드 기준으로 묶는다.

    스테이지 키의 순서는 modules 리스트에서 처음 등장한 순서를 보존한다
    (dict는 삽입 순서를 유지하므로 별도 정렬이 필요 없다).
    """
    by_stage: dict[str, list[dict]] = {}
    for m in modules:
        by_stage.setdefault(m["stage"], []).append(m)
    return by_stage


def format_version_consts(version_consts: dict) -> str:
    """모듈의 version_consts(이름 → {"value", "line"})를 표시 문자열로 변환한다.

    예: {"PROMPT_VERSION": {"value": "v4", "line": 17}} -> "PROMPT_VERSION=v4"
    비어 있으면 빈 문자열을 반환한다.
    """
    return ", ".join(f'{k}={v["value"]}' for k, v in version_consts.items())


def format_report_label(meta: dict) -> str:
    """피드의 리포트 선택 라벨을 만든다.

    예: {"repo": "Autoresearch", "pr": 120, "issue_title": "후보 목록을 프롬프트에 명시", ...}
        -> "Autoresearch PR #120 · 후보 목록을 프롬프트에 명시"
    """
    return f'{meta["repo"]} PR #{meta["pr"]} · {meta["issue_title"]}'


def _render_map_tab(store: Store) -> None:
    manifests = store.load_manifests()
    if not manifests:
        st.info("아직 수신된 매니페스트가 없습니다. CI가 POST /api/manifest 를 호출하면 채워집니다.")
    for repo, arch in manifests.items():
        st.subheader(f'{repo} @ {arch["revision"][:7]}')
        st.caption(" → ".join(arch["stages"]))
        by_stage = group_modules_by_stage(arch["modules"])
        cols = st.columns(max(len(by_stage), 1))
        for col, (stage, modules) in zip(cols, by_stage.items()):
            with col:
                st.markdown(f"**{stage}** ({len(modules)})")
                for m in modules:
                    consts = format_version_consts(m["version_consts"])
                    st.markdown(f'- `{m["id"]}`' + (f" — {consts}" if consts else ""))


def _render_feed_tab(store: Store) -> None:
    reports = store.list_reports()
    if not reports:
        st.info("아직 수신된 PR 리포트가 없습니다.")
        return
    labels = [format_report_label(r) for r in reports]
    picked = st.selectbox(
        "리포트 선택 (최신 갱신순)", range(len(labels)), format_func=lambda i: labels[i]
    )
    meta = reports[picked]
    html = store.load_report_html(meta["repo"], meta["pr"])
    if html:
        # 템플릿은 UI 비종속 — 완성된 리포트 HTML을 그대로 임베드만 하고
        # UI가 리포트 내용을 재가공하거나 검증 판정에 개입하지 않는다.
        components.html(html, height=1400, scrolling=True)


def main() -> None:
    st.set_page_config(page_title="Autoresearch archmap", layout="wide")
    store = Store(Path(os.environ.get("ARCHMAP_DATA_DIR", "data")))
    tab_map, tab_feed = st.tabs(["전체 맵", "PR 리포트 피드"])

    with tab_map:
        _render_map_tab(store)

    with tab_feed:
        _render_feed_tab(store)


if __name__ == "__main__":
    main()
