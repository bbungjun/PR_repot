# PR 이해 리포트 & 살아있는 아키텍처 맵 — 작업 인수인계

> 작성일: 2026-07-17 · 상태: 설계(스펙) 확정, 구현 계획 착수 직전
> 이 폴더는 이어서 작업하기 위한 **자립형 맥락 번들**입니다. 새 세션/새 담당자가
> 이 문서만 읽어도 지금까지의 결정과 그 이유, 다음 할 일을 알 수 있게 정리했습니다.

---

## 0. 이 폴더에 뭐가 있나

| 파일 | 내용 |
| --- | --- |
| `README.md` (이 문서) | 전체 맥락·결정·이유·다음 단계 |
| `spec-pr-comprehension-report.md` | 확정된 설계 스펙 (canonical 사본) |
| `mockup-module-architecture-map.html` | 전체 아키텍처 맵 목업 (브라우저로 열기) |
| `mockup-pr-report-120.html` | PR 이해 리포트 목업 — 실제 PR #120 데이터 |

**canonical 원본 위치**(Autoresearch 저장소):
- 스펙: `Autoresearch/docs/specs/2026-07-16-pr-comprehension-report.md`
- 맵 목업: `Autoresearch/docs/module_architecture_map.html`
- 리포트 목업: `Autoresearch/docs/pr_comprehension_report_mockup.html`

---

## 1. 문제와 목적

**병목**: 에이전트가 단시간에 대량의 코드를 짜면, 그걸 리뷰 시점에 **이해·검증하는
일**이 병목이 된다. 리뷰어는 "이 PR이 무엇을·어디에·왜 바꿨고, 어떤 계약을
건드렸으며, 어디까지 영향이 번지는가"를 코드 전체를 읽어 역추적해야 한다.

**목적**: "코드 전부 읽기"를 "**의도와 변경을 나란히 놓고 대조하기**"로 바꾼다.
이슈(=의도)에 연결된 PR(=변경)이 열릴 때, 변경을 아키텍처 맵 위에 얹어 자동으로
이해 가능한 리포트를 만든다.

- **이슈 = 의도** ("무엇을 왜 하려 했나")
- **PR/diff = 실제 변경** ("코드가 실제로 뭘 바꿨나")
- **리포트 = 그 둘을 잇는, 자동 생성된 이해 가능한 뷰**

---

## 2. 무엇을 만드는가

한 줄 요약:
> 이슈에 연결된 PR이 열리면 → CI가 변경을 아키텍처 맵 위에 얹어
> "무엇을/어디에/왜/흐름 위치/담당 경계"를 자동 서술하고, 모든 문장을
> `file:line`에 앵커한 이해 리포트를 만든다. 머지되면 전체 살아있는 맵이 갱신된다.

**핵심 개념 — 하나의 데이터 모델, 두 개의 줌**: 이해 리포트는 별도 산출물이 아니라
**전체 아키텍처 맵의 "PR 줌" 뷰**다. 같은 스테이지 분류·모듈 신원·의존 그래프를
공유하고, PR 뷰는 그 위에 이 PR의 델타를 하이라이트한다.

**리포트 유형은 "이해·맥락형"으로 확정** (대안: 리뷰 판단 지원형 / 이슈 이행
검증형). 즉 "이 변경이 시스템 전체에서 무슨 의미인가"를 이해시키는 게 1차 임무.

---

## 3. 확정된 설계 결정 (전체)

| # | 항목 | 결정 | 이유 |
| --- | --- | --- | --- |
| 1 | 리포트 1차 임무 | **이해·맥락형** | "빨리 이해"가 병목이므로 |
| 2 | 배경 맥락 유지 | **하이브리드** | 구조는 자동추출, 역할·담당/비담당은 얇은 sidecar, 서술은 LLM |
| 3 | 신뢰 모델 | **trust-but-verify** | 검증 표기는 렌더러가 사실로만 부여, LLM은 자기 검증 불가 |
| 4 | 트리거 | **PR 시점 리포트 + 머지 시점 맵 갱신** | 리뷰 병목은 머지 전에 걸림 |
| 5 | 사실/의미 분담 | 계약·흐름=결정론, 왜·무엇을=LLM | LLM을 사실 판정에 쓰면 오류만 늘어남 |
| 6 | 서술기 LLM | **GLM `glm-5.2` (Z.ai)** | 기존 `glm_generator.py` 패턴 재사용, 한국어 자연스러움 |
| 7 | 호스팅 | **라이브 서버 (Streamlit)** | 사용자가 운영 의향 확정. GLM·조립·저장·UI 중앙화 |
| 8 | 조립 방식 | **고정 HTML/CSS 템플릿 슬롯 채움** | GLM은 서술 슬롯만, 사실 슬롯은 JSON. 템플릿 UI 비종속 |
| 9 | 레포 배치 | **서버는 day-0부터 별도 중립 레포** | 경계 위생(ADR-0002) + 라이브 서버 이전 비용 회피 |
| 10 | UI | Streamlit 먼저, React는 제품화 시 | 팀이 Python·내부 도구. 템플릿 재사용 가능 |
| 11 | 출시 순서 | 결정론 골격 먼저 → GLM 얇게 나중 | GLM/서버 죽어도 사실은 CI 코멘트로 최소 보장 |

---

## 4. 최종 아키텍처 (CI + 서버, 두 레포)

**경계 원칙: 소스가 필요한 일(추출)은 각 레포 CI, 소스가 필요 없는 일
(서술·조립·저장·UI)은 중립 서버.** 서버는 레포를 체크아웃하지 않고 CI가 보낸
JSON만 받는다.

```
각 레포 CI (PR open/synchronize, main 머지)   ← Autoresearch (application)
  ├─ ① 추출기(결정론, AST) ─ architecture.json + pr-delta.json
  ├─ ② sidecar staleness 게이트 (public 표면 바뀌면 __arch__ 갱신 강제)
  └─ POST → 서버 API  +  PR에 요약·링크 코멘트 upsert
─────────────────────────────────────────────────
중립 라이브 서버 (Streamlit)                   ← Autoresearch-archmap (신규)
  ├─ ③ GLM 서술기      ─ system prompt·하네스 (한 곳에서 iterate)
  ├─ ④ 템플릿 조립 렌더러 ─ 고정 HTML/CSS + facts(JSON) + 서술 슬롯
  ├─ ⑤ 저장소           ─ 리포트·매니페스트 누적 (파일/SQLite→관리형)
  └─ ⑥ 웹 UI            ─ [전체 맵] 탭 · [PR 리포트 피드] 탭
```

**두 레포의 역할**:
- **`Autoresearch` (이 repo)**: 추출기(AST) + CI 워크플로우 + PR 코멘트만. 소스가
  여기 있으니 여기.
- **`Autoresearch-archmap` (신규 중립 repo, day-0부터)**: 서버 전체 + JSON 스키마
  소유.
- 둘은 `architecture.json`/`pr-delta` **HTTP JSON 스키마로만** 연결(서버 코드
  import 없음 — batch-contract처럼 스키마만 공유).

**왜 서버가 별도 레포인가 (중요)**: 서버를 application에 두면 orchestration/infra의
CI가 application 소유 서버에 의존 → ADR-0002가 끊으려던 결합을 되살림. 또 라이브
서버의 후속 이전은 비용이 크다. 서버는 소스를 안 읽고 JSON만 받으므로 day-0
분리가 오히려 깔끔하다.

---

## 5. 데이터 모델 & 계약 (요약 — 상세는 스펙 §5)

**① `__arch__` sidecar** (모듈 신원, 얇게 유지, AST로 실행 없이 추출):
```python
__arch__ = {
    "stage": "action_logs",
    "role": "판단을 실제 이벤트 로그로 만드는 합성 본체",
    "owns": ["격리 생성", "전역 CTR 정규화", "이벤트 확장", "parquet·checkpoint 저장"],
    "not_owns": ["clicked 라벨 저장", "CTR 학습셋 빌더"],
}
```

**② `architecture.json`** (레포·리비전당): repo, revision, contract_version, stages,
modules(id·stage·role·owns·not_owns·public_symbols·version_consts·schema_fields·
imports), contracts(name·cli_args·consumed_by).

**③ `pr-delta.json`** (PR당): pr, base/head_sha, issue(number·title·body_excerpt),
changed_modules, version_changes, unchanged_contracts, schema_changes, cross_repo,
tests, sidecar_stale.

**④ 서버 API 계약**:
- `POST /api/pr-report` — body: `pr-delta` + `architecture.json`. 서버가 GLM 서술
  → 조립 → 저장 → 렌더 URL 반환. CI가 URL을 PR 코멘트에 넣음.
- `POST /api/manifest` — body: `architecture.json`(머지 시). 전체 맵 갱신.
- 인증: CI→서버 공유 토큰/서명 헤더.

---

## 6. Trust-but-verify (검증 규칙)

리포트 각 주장은 세 상태:
- **검증됨(초록)** — 추출기 사실로 뒷받침. 조건:
  - "X 계약/스키마 불변" ⟺ X 버전 상수가 `unchanged_contracts`에 있고 필드 변경 없음
  - "하위호환" ⟺ 공개 심볼 변경이 선택 인자 추가로만 구성
  - "테스트 커버됨" ⟺ public 변경 모듈에 대응 테스트 파일 변경 존재
- **서술(회색)** — LLM이 diff·이슈로 작성 (왜, 평이한 무엇을). 앵커는 있으나
  자동 검증 안 됨.
- **앵커(⚓)** — 모든 상태 공통. `file:line`으로 원본 연결.

**핵심 불변식**: 검증 표기는 **렌더러가 `pr-delta`에서 부여**. LLM은 검증 상태를
스스로 주장 못함 → "자신 있게 틀린 검증" 구조적 차단.

---

## 7. 근거 예시: PR #120 (목업의 실제 데이터)

`mockup-pr-report-120.html`은 실제 커밋 `3be5fae`("후보 24행과 인덱스를 프롬프트에
명시", @bbungjun)에서 추출한 데이터로 구성. 이 PR이 검증 규칙을 잘 보여줌:

- `PROMPT_VERSION: action_log_ctr_v3 → v4` (schema.py:17) — **변경·비파괴** (프롬프트 계약)
- `ACTION_LOG_SCHEMA_VERSION: v1` 무변경 (schema.py:16) → **"저장 스키마 불변" = 자동 검증됨(초록)**
- `run_daily_action_log(..., max_users=None)` 선택 인자 추가 (daily.py:722) — **하위호환**
- `CANDIDATE_COLUMNS`에 `index` 추가 + `_candidate_block` enumerate (llm_generator.py:72)
- 테스트 2개 파일 +52줄 — **커버됨**
- 흐름 위치: `[영상]+[유저] → ●action_logs → [학습]`, action_logs 내부 llm_generator·daily·schema만 hit

---

## 8. 저장소 컨텍스트

**3개 레포 구조** (CLAUDE.md 기준):
- `Autoresearch` (= application): 런타임 패키지 `autoresearch/`(youtube_collection,
  virtual_users, action_logs, jobs) + `proxy/` + CTR 학습 `src/`(models/features/
  pipeline) + `Dockerfile.app`(공개 CLI 이미지). **이 repo에 추출기+CI가 붙음.**
- `Autoresearch-airflow` (= orchestration): DAG·schedule·KPO·배포 소유. application
  image와 공개 CLI만 소비. **Phase 3에서 추출기 추가.**
- `Autoresearch-infra` (= infra): GCP 인프라(추정 Terraform/설정). **Phase 4에서
  별도 추출기 또는 수동 매니페스트.**

**관련 기존 문서**(근거·재사용):
- `docs/specs/2026-07-13-public-batch-execution-contract.md` — `batch-contract-v1`,
  OCI 라벨, breaking 규칙. **교차 레포 계약 판정의 근거.**
- `docs/adr/0002-repository-responsibility-boundaries.md` — 레포 경계. **서버를
  중립 레포에 두는 근거.**

**GLM 재사용 패턴** (`autoresearch/virtual_users/glm_generator.py`):
- `_OpenAICompatibleVirtualUserGenerator` — provider별 api_key·base_url·model만
  다르고 system harness/파싱 공유. **서술기는 이 클래스에서 harness만 교체.**
- `DEFAULT_GLM_MODEL = "glm-5.2"`, `DEFAULT_ZAI_BASE_URL =
  "https://api.z.ai/api/coding/paas/v4"`, env `ZAI_API_KEY`. OpenAI-compatible
  (`from openai import OpenAI`).

**추출 시드**(이미 존재하는 계약 소스):
- 버전 상수: `youtube_collection/schema.py`(`SCHEMA_VERSION`, `TARGET_COUNTRY`),
  `virtual_users/schema.py`(`GENERATION_SCHEMA_VERSION`, `PROMPT_VERSION`),
  `action_logs/schema.py`(`ACTION_LOG_SCHEMA_VERSION`, `PROMPT_VERSION`)
- CLI 계약: `autoresearch/jobs/action_log.py`(`BATCH_CONTRACT_VERSION`, argparse)

---

## 9. 미결 사항 (전부 Phase 0/2/3 착수 시 확정)

- **서버 배포·호스팅**: Streamlit 서버 위치(Cloud Run 등 기존 GCP 스택 후보),
  스토리지(파일/SQLite→관리형).
- **접근제어**: 내부 아키텍처 노출 → 서버 인증(SSO/토큰), CI→서버 전송 인증.
- **연결 이슈 파싱**: PR-이슈 링크를 `closes #N` / PR body / 브랜치명 `<num>-...`
  중 무엇으로 확정할지.
- **LLM 비용/레이트리밋**: PR 갱신마다 GLM 호출 시 디바운스·캐시 정책.

**주요 리스크**: 이슈 품질이 "왜"의 상한(부실 시 커밋 메시지 폴백+표기) · 서버 운영
부담(경량 시작) · sidecar 유지 실패(CI 게이트로 강제) · 벽지화(PR 코멘트로 진입점
유지).

---

## 10. 다음 단계 — 구현 계획 (Phase 0)

**아직 안 한 것**: `docs/plans/2026-07-16-pr-comprehension-report.md` 작성.

**선행**:
- 이 프로젝트용 GitHub 이슈 발행 (CLAUDE.md: 코드 변경은 이슈-브랜치 먼저)
- `Autoresearch-archmap` 레포 생성

**Phase 0 작업 덩어리** (결정론 골격, GLM 없이):
- *application repo*: (1) 추출기(AST) → `architecture.json`/`pr-delta.json`
  (2) CI 워크플로우(PR/머지 트리거) (3) 서버 POST + PR 코멘트 upsert
- *archmap repo*: (4) 수신 API(`/api/pr-report`, `/api/manifest`) (5) 템플릿 조립
  (사실 슬롯만) (6) 저장(파일/SQLite) (7) Streamlit [맵]·[PR 피드] 탭
- *공통*: 두 레포를 잇는 JSON 스키마를 계약으로 먼저 고정
- (선택) 착수 전 단일 위치 로컬 스파이크로 end-to-end 루프 검증 후 분리

**이후 Phase**: 1(sidecar `__arch__`+게이트) → 2(GLM 서술 슬롯+디바운스/캐시) →
3(airflow 추출기+집계) → 4(infra).

**성공 기준**: 리뷰어가 코드를 열기 전에 계약·영향을 리포트만으로 파악 · 검증됨
주장이 추출기 사실과 1:1(허위 초록 0) · public 표면 바꾼 PR은 sidecar 갱신 없이
머지 불가 · Phase 0이 LLM 없이도 유용.

---

## 로컬 실행 (Phase 0)

```bash
uv sync
ARCHMAP_TOKEN=dev uv run uvicorn archmap.api:app --port 8000   # 수신 API
uv run streamlit run archmap/ui.py                              # 웹 UI (맵·피드 탭)
uv run python -m pytest                                         # 테스트
```

CI 연동 환경변수: `ARCHMAP_TOKEN`(공유 토큰), `ARCHMAP_BASE_URL`(리포트 링크 베이스), `ARCHMAP_DATA_DIR`(저장 위치, 기본 `data/`).

---

## 11. 다음 세션 재개용 프롬프트 (복붙)

```
C:\PR_report\README.md 와 spec-pr-comprehension-report.md 를 읽어줘.
"PR 이해 리포트 & 살아있는 아키텍처 맵" 프로젝트를 이어서 진행할 거야.
설계는 확정됐고, 다음 할 일은 Phase 0 구현 계획(docs/plans/...)을 쓰는 것.
두 레포(Autoresearch = 추출기+CI, Autoresearch-archmap = 서버)에 걸친
Phase 0 작업 분해와 검증 체크리스트부터 만들어줘.
```
