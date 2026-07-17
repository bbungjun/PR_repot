"""CI가 보낸 JSON을 받아 리포트를 조립·저장하는 수신 API."""
from __future__ import annotations

import hmac
import json
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
    provided = request.headers.get("X-Archmap-Token")
    # expected가 없으면 무조건 fail-closed(401). provided가 None일 수 있으므로
    # hmac.compare_digest에 넘기기 전에 반드시 걸러낸다(넘기면 TypeError).
    # 토큰은 CI-서버 공유 시크릿이므로 타이밍 사이드채널을 막기 위해
    # 상수 시간 비교를 사용한다.
    #
    # Starlette는 헤더 값을 latin-1로 디코딩하므로, 상위 바이트(0x80 이상)가
    # 든 원시 헤더도 디코딩에 성공해 non-ASCII 문자가 든 str이 될 수 있다.
    # hmac.compare_digest는 non-ASCII str 비교를 지원하지 않아 TypeError를
    # 던지므로, 비교 전에 양쪽을 바이트로 인코딩해 상수 시간 비교 성질을
    # 유지한 채 이 경우도 정상적으로 401로 처리되게 한다.
    if not expected or provided is None:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")
    provided_bytes = provided.encode("utf-8", "surrogateescape")
    expected_bytes = expected.encode("utf-8")
    if not hmac.compare_digest(provided_bytes, expected_bytes):
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다")


async def _read_json_object(request: Request) -> dict:
    """요청 바디를 JSON으로 파싱하고 최상위가 객체인지 확인한다.

    CI 쪽 버그나 손상된 요청이 잘못된 JSON 구문·빈 바디·비-객체 최상위 값을
    보낼 수 있다. 이런 입력은 서버 결함(500)이 아니라 잘못된 클라이언트
    요청(400)으로 다뤄야 하는 신뢰 경계이므로 여기서 한 번에 검증한다.
    """
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # request.json()은 내부적으로 json.loads(body)를 호출하며, body가
        # 유효한 UTF-8이 아니면 UnicodeDecodeError를 던진다. 이는
        # JSONDecodeError의 서브클래스가 아닌 별개 예외(공통 조상은
        # ValueError)이므로 함께 잡아 400으로 처리한다.
        raise HTTPException(status_code=400, detail=f"잘못된 JSON입니다: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="요청 본문은 JSON 객체여야 합니다")
    return body


def create_app() -> FastAPI:
    app = FastAPI(title="archmap")

    @app.post("/api/pr-report")
    async def pr_report(request: Request):
        _check_token(request)
        body = await _read_json_object(request)
        try:
            architecture, pr_delta = body["architecture"], body["pr_delta"]
            validate_architecture(architecture)
            validate_pr_delta(pr_delta)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"계약 위반: 누락된 필드 {exc}") from exc
        except jsonschema.ValidationError as exc:
            # exc를 그대로 문자열화(str(exc))하면 스키마 전문($schema, 모든
            # required/properties)까지 응답에 포함돼 비대해진다. 실패 사유만
            # 담은 exc.message만 노출한다.
            raise HTTPException(status_code=400, detail=f"계약 위반: {exc.message}") from exc
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
        doc = await _read_json_object(request)
        try:
            validate_architecture(doc)
        except jsonschema.ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"계약 위반: {exc.message}") from exc
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
