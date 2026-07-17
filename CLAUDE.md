# CLAUDE.md — PR 이해 리포트 & 살아있는 아키텍처 맵

> 이 문서는 이 디렉터리(`C:\PR_report`, 장차 `Autoresearch-archmap` 레포)에서
> 작업하는 AI 코딩 에이전트의 기본 진입점입니다. 먼저 `README.md`(전체 맥락)와
> `spec-pr-comprehension-report.md`(확정 설계)를 읽으세요.

## Language Preference

에이전트 응답, PR 코멘트, 리뷰 요약, 구현 노트, 문서는 **한국어 격식체**를
사용합니다. 사용자가 명시적으로 요청할 때만 다른 언어를 씁니다.

## 프로젝트 정체성

이 프로젝트는 **"agent가 단시간에 짠 코드를 리뷰 시점에 이해하는 병목"**을
해소합니다. 이슈(=의도)에 연결된 PR(=변경)이 열리면, 변경을 아키텍처 맵 위에 얹어
"무엇을/어디에/왜/흐름 위치/담당 경계/계약·영향"을 자동 서술한 **이해 리포트**를
만들고, 머지되면 **전체 살아있는 맵**을 갱신합니다.

핵심 개념: 이해 리포트는 별도 산출물이 아니라 **전체 아키텍처 맵의 "PR 줌" 뷰**.

## 이 저장소의 책임 (중요 — 경계)

이 저장소(`Autoresearch-archmap`)는 **중립 라이브 서버**입니다.

**담당**:
- 수신 API (`POST /api/pr-report`, `POST /api/manifest`)
- GLM 서술기 (system prompt·하네스)
- 템플릿 조립 렌더러 (고정 HTML/CSS + facts + 서술 슬롯)
- 저장소 (리포트·매니페스트 누적)
- 웹 UI (Streamlit: [전체 맵] 탭 · [PR 리포트 피드] 탭)
- `architecture.json` / `pr-delta.json` **JSON 스키마 소유·버전**

**비담당** (다른 곳에 있음):
- **소스 추출기** — 각 소스 레포(`Autoresearch` 등)의 CI에 있습니다. 소스를 읽는
  일은 소스가 있는 레포에서. 이 서버는 **레포를 체크아웃하지 않고** CI가 보낸
  JSON만 받습니다.
- 코드 품질·버그 리뷰 (이 프로젝트는 "이해"가 목적, 승인 판단 대체 아님).

> 경계 근거: 서버를 application 레포에 두면 orchestration/infra가 application에
> 의존하게 되어 `Autoresearch` 저장소의 ADR-0002(repository-responsibility-
> boundaries) 취지에 어긋납니다. 그래서 서버는 처음부터 별도 중립 레포입니다.

## 기술 스택

- **Python** (Autoresearch 생태계와 동일, 3.12 기준)
- **Streamlit** — 웹 UI (Phase 0). 템플릿은 UI 비종속이라 추후 React 전환 가능.
- **GLM** (`glm-5.2`, Z.ai OpenAI-compatible) — 서술기. 기존
  `Autoresearch/autoresearch/virtual_users/glm_generator.py`의
  `_OpenAICompatibleVirtualUserGenerator` 패턴을 재사용하고 **system harness만
  교체**. env `ZAI_API_KEY`, `ZAI_BASE_URL`(기본
  `https://api.z.ai/api/coding/paas/v4`).
- **저장**: 파일/SQLite에서 시작 → 필요 시 관리형.

## Core Rules

- **Trust-but-verify 불변식**: 리포트의 "검증됨(초록)" 표기는 **렌더러가
  `pr-delta` 사실로만** 부여합니다. GLM(서술기)은 자기 서술을 "검증됨"으로 표기할
  수 없습니다. → "자신 있게 틀린 검증"을 구조적으로 차단.
- **역할 분담**: 계약·영향·흐름 위치 등 **사실 슬롯은 JSON(결정론)**으로, "왜/무엇을"
  **서술 슬롯만 GLM**으로 채웁니다. LLM을 사실 판정에 쓰지 마세요.
- **결정론 우선**: 골격(사실 조립·저장·UI)을 먼저 세우고 GLM 서술을 얇게 얹습니다.
  GLM/서버가 죽어도 사실은 소스 레포 CI의 PR 코멘트로 최소 보장됩니다.
- **모든 주장은 앵커**: 리포트의 각 줄은 `file:line`으로 원본에 연결합니다.
- **스키마는 계약**: `architecture.json`/`pr-delta.json`/서버 API는 소스 레포 CI가
  의존하는 공개 계약입니다. 변경 시 버전을 올리고 소비자(추출기)와 조율하세요
  (`Autoresearch`의 `batch-contract` 관례를 따름).
- 시크릿(`ZAI_API_KEY` 등), 생성 데이터, `.env`를 커밋하지 않습니다.

## 데이터 계약 (요약 — 상세는 `spec-...md` §5)

- `__arch__` sidecar (소스 레포 모듈에 위치): `stage`, `role`, `owns`, `not_owns`.
- `architecture.json` (레포·리비전당): modules(public_symbols·version_consts·
  schema_fields·imports), contracts(cli_args·consumed_by).
- `pr-delta.json` (PR당): changed_modules, version_changes, unchanged_contracts,
  schema_changes, cross_repo, tests, sidecar_stale.
- 서버 API: `POST /api/pr-report`(→ 렌더 URL 반환), `POST /api/manifest`.

## Documentation Navigation

| 필요 | 문서 |
| --- | --- |
| 전체 맥락·결정·이유·다음 단계 | `README.md` |
| 확정 설계 (아키텍처·데이터 모델·검증 규칙·Phase) | `spec-pr-comprehension-report.md` |
| 전체 맵 시각 레퍼런스 | `mockup-module-architecture-map.html` |
| PR 리포트 시각 레퍼런스 (실데이터 PR #120) | `mockup-pr-report-120.html` |

## 현재 상태 / 다음 단계

- **상태**: Phase 0 구현 완료.
  - 이 레포(서버): 수신 API + 템플릿 조립(사실 슬롯) + 저장 + Streamlit 맵/피드
    탭 구현 완료, 테스트 101개 통과.
  - 추출기: `SKYAHO/Autoresearch` 이슈 #165 / 브랜치 `feat/165-archmap-extractor`
    에서 구현 완료(테스트 381개 통과). **아직 PR 미생성·미머지.**
  - E2E 확인: 실제 추출기 산출물(`architecture.json`/`pr-delta.json`)이 이
    서버의 스키마 검증을 통과해 리포트로 렌더됨을 확인함.
- **다음**: Phase 1(sidecar `__arch__` + CI 게이트) → Phase 2(GLM 서술) →
  Phase 3(airflow) → Phase 4(infra).
- **미결**: 서버 호스팅·배포 미확정(현재는 로컬 실행만 가능). `GET
  /reports/{repo}/{pr}` 접근제어 미확정 — 스펙 §12는 "Phase 0에서 확정"이라
  했으나 호스팅이 정해지지 않아 Phase 1로 이월.

## 참조 (원본 Autoresearch 저장소)

- `docs/specs/2026-07-13-public-batch-execution-contract.md` — 교차 레포 계약 판정
  근거(`batch-contract-v1`, OCI 라벨, breaking 규칙).
- `docs/adr/0002-repository-responsibility-boundaries.md` — 레포 경계 근거.
- `autoresearch/virtual_users/glm_generator.py` — GLM 클라이언트 재사용 패턴.
