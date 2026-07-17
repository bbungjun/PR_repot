"""CI가 보낸 JSON을 받아 리포트를 조립·저장하는 수신 API."""
from __future__ import annotations

import os
from pathlib import Path

import jsonschema
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from archmap.contracts import validate_architecture, validate_pr_delta
from archmap.render import render_report
from archmap.storage import Store


def _store() -> Store:
    return Store(Path(os.environ.get("ARCHMAP_DATA_DIR", "data")))


def _check_token(request: Request) -> None:
    expected = os.environ.get("ARCHMAP_TOKEN")
    if not expected or request.headers.get("X-Archmap-Token") != expected:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")


def create_app() -> FastAPI:
    app = FastAPI(title="archmap")

    @app.post("/api/pr-report")
    async def pr_report(request: Request):
        _check_token(request)
        body = await request.json()
        try:
            architecture, pr_delta = body["architecture"], body["pr_delta"]
            validate_architecture(architecture)
            validate_pr_delta(pr_delta)
        except (KeyError, jsonschema.ValidationError) as exc:
            raise HTTPException(status_code=400, detail=f"계약 위반: {exc}") from exc
        html = render_report(architecture, pr_delta)
        try:
            _store().save_report(pr_delta, html)
        except ValueError as exc:
            # Store는 repo/head_sha/pr 같은 경로 구성요소를 화이트리스트로
            # 검증하며 위반 시 ValueError를 던진다(경로 주입 방어). 스키마는
            # 통과했지만 값 자체가 안전하지 않은 입력이므로 이는 서버 오류가
            # 아니라 잘못된 클라이언트 입력으로 취급해 400으로 응답한다.
            raise HTTPException(status_code=400, detail=f"허용되지 않는 값입니다: {exc}") from exc
        base = os.environ.get("ARCHMAP_BASE_URL", "http://localhost:8000")
        return {"report_url": f'{base}/reports/{pr_delta["repo"]}/{pr_delta["pr"]}'}

    @app.post("/api/manifest")
    async def manifest(request: Request):
        _check_token(request)
        doc = await request.json()
        try:
            validate_architecture(doc)
        except jsonschema.ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"계약 위반: {exc}") from exc
        try:
            _store().save_manifest(doc)
        except ValueError as exc:
            # pr-report와 동일한 이유로 경로 주입 방어 예외를 400으로 변환한다.
            raise HTTPException(status_code=400, detail=f"허용되지 않는 값입니다: {exc}") from exc
        return {"ok": True}

    @app.get("/reports/{repo}/{pr}", response_class=HTMLResponse)
    async def report(repo: str, pr: int):
        try:
            html = _store().load_report_html(repo, pr)
        except ValueError as exc:
            # 경로 파라미터(repo)가 화이트리스트를 벗어난 경우로, 이는 존재하지
            # 않는 리소스에 대한 요청이 아니라 애초에 유효하지 않은 요청이므로
            # 404가 아닌 400으로 구분해 응답한다.
            raise HTTPException(status_code=400, detail=f"허용되지 않는 값입니다: {exc}") from exc
        if html is None:
            raise HTTPException(status_code=404, detail="리포트가 없습니다")
        return html

    return app


app = create_app()
