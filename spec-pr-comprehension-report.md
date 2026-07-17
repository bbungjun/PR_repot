# PR 이해 리포트 & 살아있는 아키텍처 맵

- **상태**: Proposed
- **날짜**: 2026-07-16
- **관련 문서**: `docs/specs/2026-07-13-public-batch-execution-contract.md`,
  `docs/adr/0002-repository-responsibility-boundaries.md`
- **참고 산출물(목업)**: `docs/module_architecture_map.html`(전체 맵),
  `docs/pr_comprehension_report_mockup.html`(PR 줌 뷰)

## 1. 배경과 문제

에이전트가 단시간에 대량의 코드를 작성하면서, **변경을 이해·검증하는 리뷰
단계가 병목**이 되었다. 리뷰어는 "이 PR이 무엇을, 어디에, 왜 바꿨고, 어떤 계약을
건드렸으며, 어디까지 영향이 번지는가"를 코드 전체를 읽어 역추적해야 한다.

이 프로젝트는 3개 저장소로 분리되어 있어(`Autoresearch` = application,
`Autoresearch-airflow` = orchestration, `Autoresearch-infra` = infra) 변경의
영향이 레포 경계를 넘는 경우 이해 비용이 더 커진다.

**목표는 "코드 전부 읽기"를 "의도와 변경을 나란히 놓고 대조하기"로 바꾸는
것**이다. 이슈(의도)에 연결된 PR(변경)이 열릴 때, 변경을 아키텍처 맵 위에 얹어
자동으로 이해 가능한 리포트를 만든다.

## 2. 목표 / 비목표

### 목표
- 이슈에 연결된 PR이 열리거나 갱신되면, **이해·맥락형 리포트**를 자동 생성한다
  (무엇을 / 어디에 / 왜 / 흐름 위치 / 담당 경계 / 계약·영향).
- 리포트의 모든 주장을 `file:line` 원본에 **앵커**하고, 자동 검증 가능한 사실과
  LLM 서술을 시각적으로 구분한다(trust-but-verify).
- **중립 라이브 서버**가 GLM 서술기·조립 템플릿·저장소·웹 UI를 호스팅한다. UI는
  전체 프로젝트 맵 탭과, PR 리포트가 갱신되며 누적되는 피드 탭을 제공한다.
- PR에는 요약+링크 **코멘트**를 남겨 리뷰 진입점을 PR 안에 둔다(서버 탭은 깊은
  뷰이지 유일한 뷰가 아니다).
- 3개 레포를 집계한 **전체 살아있는 맵**을 유지하고, 교차 레포 계약
  (`batch-contract-v1`, OCI 라벨) 영향을 1급으로 표시한다.

### 비목표 (이번 범위 밖)
- 코드 품질·버그 리뷰(정적 분석/린트/리뷰 봇의 영역). 이 리포트는 **이해**가
  목적이며 승인 판단을 대체하지 않는다.
- 서버가 레포를 체크아웃/빌드하는 것. 소스 분석(추출)은 각 레포 CI에서 수행하고
  서버는 그 산출 JSON만 받는다(§4).
- `Autoresearch-infra`의 Terraform/설정 추출기(별도 생태계). 초기엔 수동 매니페스트
  기여로 대체하고, 전용 추출기는 후속 과제(Phase 4)로 둔다.

## 3. 핵심 개념: 하나의 데이터 모델, 두 개의 줌

이해 리포트는 별도 산출물이 아니라 **아키텍처 맵의 "PR 줌" 뷰**다.

| | 전체 맵 (온보딩) | PR 이해 리포트 (리뷰) |
| --- | --- | --- |
| 트리거 | main 머지 | PR open/synchronize |
| 초점 | 시스템 전체 | 이 PR이 만진 영역 |
| 데이터 | `architecture.json` | `architecture.json` + `pr-delta.json` |

같은 스테이지 분류·모듈 신원·의존 그래프를 공유하고, PR 뷰는 그 위에 델타를
하이라이트한다.

## 4. 아키텍처: CI(추출) + 라이브 서버(조립·저장·표시)

경계 원칙: **소스가 필요한 일(추출)은 각 레포 CI에서, 소스가 필요 없는 일
(서술·조립·저장·UI)은 중립 서버에서.** 서버는 레포를 체크아웃하지 않고 CI가
보낸 JSON만 받는다.

```
각 레포 CI (PR open/synchronize, main 머지)
  ├─ ① 추출기(결정론) ─ architecture.json + pr-delta.json
  ├─ ② sidecar staleness 게이트 (실패 시 __arch__ 갱신 요구)
  └─(POST) 서버 API로 JSON 전송  +  PR에 요약·링크 코멘트 upsert
───────────────────────────────────────────────
중립 라이브 서버 (Streamlit)
  ├─ ③ GLM 서술기      ─ system prompt·하네스 (한 곳에서 iterate)
  ├─ ④ 템플릿 조립 렌더러 ─ 고정 HTML/CSS + facts(JSON) + 서술 슬롯
  ├─ ⑤ 저장소           ─ 리포트·매니페스트 누적
  └─ ⑥ 웹 UI            ─ [전체 맵] 탭 · [PR 리포트 피드] 탭
```

### ① 추출기 (deterministic, CI)
소스 트리 + PR diff + 연결 이슈를 입력받아 `architecture.json`·`pr-delta.json`을
생성한다. **LLM 없이 순수 정적 분석**이며, 가장 값어치 있는 부분(계약·영향, 흐름
위치)은 전부 여기서 결정론적으로 나온다.

- AST로 모듈별 public 심볼·시그니처, 모듈 레벨 버전 상수(`*_VERSION` 등),
  import 그래프를 추출한다(모듈을 **import 하지 않고** AST만 파싱 — 부작용 회피).
- pydantic/pyarrow 스키마 정의의 필드 집합을 추출한다.
- 공개 CLI 인자(`jobs/*.py`의 argparse)를 추출해 `batch-contract` 표면을 구성한다.
- 산출 JSON을 서버 API(§5.4)로 POST하고, PR에는 서버 뷰 링크가 담긴 요약 코멘트를
  upsert한다.

### ② sidecar staleness 게이트 (CI 강제)
하이브리드 배경 유지의 톱니. 모듈의 **public 표면 또는 버전 상수가 바뀐 PR인데
그 모듈의 `__arch__`가 같은 PR에서 갱신되지 않았으면** 체크를 실패시키고, 갱신이
필요한 모듈 목록을 제시한다. 이로써 "에이전트가 자기 변경의 서술을 같은 PR에서
유지"가 강제된다.

### ③ GLM 서술기 (서버, PR당 1회)
`pr-delta` + 관련 모듈 `__arch__` + **연결 이슈 본문**으로 평이한 "무엇을 / 왜"를
작성해 **템플릿의 서술 슬롯만** 채운다. 구조·검증된 사실 슬롯은 건드리지 않는다.

- **모델·클라이언트**: GLM(`glm-5.2`, Z.ai OpenAI-compatible endpoint). 기존
  `autoresearch/virtual_users/glm_generator.py`의
  `_OpenAICompatibleVirtualUserGenerator` 패턴을 재사용하고 **system harness만
  교체**한다. 한국어 격식체 출력(CLAUDE.md)에 유리하다.
- **인증/설정**: `ZAI_API_KEY` · `ZAI_BASE_URL`(기본
  `https://api.z.ai/api/coding/paas/v4`).
- 제약: 각 문장은 `pr-delta`의 앵커(파일·심볼)를 인용해야 하고, **자기 자신을
  "검증됨"으로 표기할 수 없다**(§7).

### ④ 템플릿 조립 렌더러 (서버)
**고정 HTML/CSS 템플릿**(목업 `docs/pr_comprehension_report_mockup.html` 계열)의
슬롯을 채워 리포트를 조립한다. 슬롯 종류:
- **구조·사실 슬롯**: `pr-delta`/`architecture.json`에서 채움(흐름 위치, 계약
  스트립, 검증 표기).
- **서술 슬롯**: GLM 출력으로 채움(왜/무엇을).

템플릿은 **UI 비종속**이라 Streamlit `components.html`로 임베드하고, 추후 React로
전환해도 재사용한다.

### ⑤ 저장소 (서버)
PR 리포트와 레포별 `architecture.json`을 누적 저장한다(리포트 피드·이력·전체 맵
집계의 소스). 초기 스토리지는 경량(파일/SQLite)에서 시작.

### ⑥ 웹 UI (서버, Streamlit)
- **[전체 맵] 탭**: 3개 레포 매니페스트를 집계한 살아있는 아키텍처 맵.
- **[PR 리포트 피드] 탭**: PR별 이해 리포트가 갱신되며 누적. 레포·스테이지·계약
  변경 여부로 필터.
- 내부 아키텍처를 노출하므로 **접근제어**가 필요하다(§12).

## 5. 데이터 모델

### 5.1 모듈 신원 sidecar — `__arch__`
모듈 최상단에 모듈 레벨 dict로 선언한다(AST로 실행 없이 추출 가능). **얇게**
유지하며, 구조 정보(시그니처·그래프·버전)는 넣지 않는다(자동 추출).

```python
__arch__ = {
    "stage": "action_logs",
    "role": "판단을 실제 이벤트 로그로 만드는 합성 본체",
    "owns": ["격리 생성", "전역 CTR 정규화", "이벤트 확장", "parquet·checkpoint 저장"],
    "not_owns": ["clicked 라벨 저장", "CTR 학습셋 빌더"],
}
```

- **위치 결정**: 모듈 레벨 `__arch__` dict (docstring frontmatter 대비 파싱이
  단순하고 grep 가능). `stage`는 열거형(수집/가상유저/액션로그/오케스트레이션/학습).

### 5.2 `architecture.json` (레포·리비전당)
```json
{
  "repo": "Autoresearch",
  "revision": "<git-sha>",
  "contract_version": "batch-contract-v1",
  "stages": ["youtube_collection", "virtual_users", "action_logs", "orchestration", "training"],
  "modules": [
    {
      "id": "action_logs.pipeline",
      "stage": "action_logs",
      "role": "...", "owns": ["..."], "not_owns": ["..."],
      "public_symbols": [{"name": "generate_action_log_batch", "sig": "(request, virtual_users, videos, generator, progress_callback=None)"}],
      "version_consts": {"ACTION_LOG_SCHEMA_VERSION": "action_log_schema_v1", "PROMPT_VERSION": "action_log_ctr_v4"},
      "schema_fields": {"EventLog": ["event_id", "event_timestamp", "..."]},
      "imports": ["action_logs.candidate", "action_logs.schema"]
    }
  ],
  "contracts": [
    {"name": "batch-contract-v1", "cli_args": ["--mode", "--max-users", "..."], "consumed_by": ["Autoresearch-airflow"]}
  ]
}
```

### 5.3 `pr-delta.json` (PR당)
```json
{
  "pr": 120, "base_sha": "...", "head_sha": "3be5fae",
  "issue": {"number": 118, "title": "...", "body_excerpt": "..."},
  "changed_modules": [
    {"id": "action_logs.llm_generator",
     "symbols_changed": ["CANDIDATE_COLUMNS", "_candidate_block"],
     "public_surface_changed": true}
  ],
  "version_changes": [
    {"const": "PROMPT_VERSION", "from": "action_log_ctr_v3", "to": "action_log_ctr_v4", "breaking": false}
  ],
  "unchanged_contracts": ["ACTION_LOG_SCHEMA_VERSION"],
  "schema_changes": [],
  "cross_repo": [{"contract": "batch-contract-v1", "impact": "optional-arg-added", "breaking": false}],
  "tests": {"files": ["tests/test_action_logs_daily.py", "..."], "lines_added": 52},
  "sidecar_stale": []
}
```

### 5.4 서버 API 계약
CI가 산출 JSON을 서버로 보내는 경계. 서버는 이것만 신뢰 입력으로 받는다.

- `POST /api/pr-report` — body: `pr-delta.json` + 해당 리비전 `architecture.json`.
  서버가 GLM 서술 → 템플릿 조립 → 저장 → 렌더 URL 반환. CI는 이 URL을 PR 코멘트에
  넣는다.
- `POST /api/manifest` — body: `architecture.json`(머지 시). 전체 맵 갱신.
- 인증: 레포 CI → 서버는 공유 토큰/서명 헤더. 페이로드는 **결정론 사실**이므로
  서버는 이를 재검증 없이 신뢰하되, 검증 표기는 페이로드의 `pr-delta` 필드로만
  부여한다(§7 불변식).

## 6. 계약 영향 판정 규칙 (결정론)

추출기가 `pr-delta`를 만들 때 적용한다.

- **버전 상수 변경**: 모듈 레벨 `*_VERSION` 문자열이 바뀌면 `version_changes`에
  기록. breaking 여부는 §8 규칙으로 판정.
- **스키마 변경**: pydantic/pyarrow 스키마의 필드 추가/삭제/타입변경 →
  `schema_changes`. 필드 무변경이면 `unchanged_contracts`에 해당 버전 상수 기록.
- **공개 API 변경**: public 심볼(밑줄 없는 이름)의 시그니처 변경. 선택 인자 추가는
  하위호환, 필수 인자 추가·인자 제거·rename·반환 변경은 breaking.
- **교차 레포**: 변경된 심볼이 `contracts[].cli_args` 또는 OCI 라벨 표면에
  속하면 `cross_repo` 기록. 판정 기준은 `public-batch-execution-contract` 스펙.

## 7. Trust-but-verify: 앵커와 검증

리포트의 각 주장은 세 상태 중 하나로 렌더된다.

- **검증됨(verified, 초록)**: 추출기 사실로 뒷받침됨. 아래 조건에서만 부여한다.
  - `"X 계약/스키마 불변"` ⟺ X의 버전 상수가 `unchanged_contracts`에 있고,
    해당 모듈 `schema_changes`에 X 관련 필드 변경이 없다.
  - `"하위호환"` ⟺ 공개 심볼 변경이 선택 인자 추가로만 구성된다.
  - `"테스트 커버됨"` ⟺ `changed_modules` 중 public 변경 모듈에 대응하는 테스트
    파일 변경이 `tests`에 있다.
- **서술(narrated, 회색)**: LLM이 diff·이슈로 작성한 문장("왜", 평이한 "무엇을").
  근거 앵커는 있으나 자동 검증은 안 됨.
- **앵커(⚓)**: 모든 상태 공통. `file:line`으로 원본에 연결.

**핵심 불변식**: 검증 표기는 **렌더러가 `pr-delta`에서 부여**한다. 서술기(LLM)는
검증 상태를 스스로 주장할 수 없다 → "자신 있게 틀린 검증"을 구조적으로 차단.

## 8. Breaking change 판정

`public-batch-execution-contract`의 규칙을 재사용한다.

- 호환: 선택 인자 추가, 새 명령 추가, 비공개 심볼 변경.
- Breaking: 기존 인자 제거/의미 변경, exit code 변경, 필수 인자 추가, 공개
  스키마 필드 제거/타입 변경.
- Breaking이면 리포트에 경고를 띄우고, 교차 레포 소비자(airflow)가 있으면 전환
  PR 필요를 명시한다.

## 9. 다중 레포 집계

- **서버가 곧 허브**다. 각 레포 CI가 `POST /api/manifest`로 `architecture.json`을
  보내면 서버가 집계해 [전체 맵] 탭을 갱신한다.
- 각 레포는 동일한 `architecture.json` 스키마(§5.2)를 산출하는 추출기를 CI에
  둔다(application이 레퍼런스 구현·스키마 소유).
- 추출기 생태계별 차이: application·airflow는 Python AST 추출기(재사용), infra는
  Terraform/설정이라 별도 추출기 또는 수동 매니페스트(§2 비목표, Phase 4).
- **서버는 처음부터 별도 중립 레포**(`Autoresearch-archmap`)에서 만든다.
  application 레포에 두면 orchestration/infra가 application에 의존하게 되어
  ADR-0002 경계 취지에 어긋나고, 라이브 서버의 후속 이전은 비용이 크다. 서버는
  소스를 읽지 않고 API로 JSON만 받으므로(§5.4) day-0 분리가 오히려 깔끔하다.
- **이 저장소(application)에는 추출기 + CI 워크플로우 + PR 코멘트만** 둔다(그 소스가
  여기 있으므로). 추출기와 서버는 `architecture.json`/`pr-delta` **JSON 스키마만
  공유**하고(HTTP 경계, 서버 코드 import 없음), 스키마는 서버 레포가 소유·버전한다.
- 교차 레포 계약은 `contracts[].consumed_by`로 엣지를 구성한다.

## 10. 트리거

- **PR `opened` / `synchronize`**: CI 추출 → `POST /api/pr-report` → 서버가 리포트
  조립·저장 → PR 코멘트 upsert(서버 뷰 링크). 갱신마다 디바운스(§12).
- **main `push`(머지)**: CI 추출 → `POST /api/manifest` → 서버 전체 맵 갱신 +
  해당 PR 리포트 최종본 아카이브.

## 11. 결정 사항 (기본값 — 스펙 리뷰에서 변경 가능)

1. **범위**: `Autoresearch` 레포를 레퍼런스로 먼저 구현하되, `architecture.json`
   스키마와 추출기 인터페이스는 repo-agnostic하게 설계(추후 제품화 여지).
2. **트리거**: PR 이벤트(리포트) + 머지(맵 갱신) 둘 다.
3. **sidecar 위치**: 모듈 레벨 `__arch__` dict.
4. **표면**: PR 코멘트(진입점) + 라이브 서버 UI(맵 탭 + PR 피드 탭, 깊은 뷰).
5. **LLM 의존 최소화**: 추출기·계약·흐름은 결정론. LLM은 "무엇을/왜" 서술 슬롯에만.
6. **서술기 LLM**: GLM(`glm-5.2`, Z.ai). 기존 `glm_generator.py` 클라이언트 패턴
   재사용, system harness만 교체(§4-③).
7. **호스팅**: 라이브 서버(Streamlit)가 GLM·조립·저장·UI를 호스팅. CI는 추출·전송만.
8. **조립**: 고정 HTML/CSS 템플릿을 슬롯 채움으로 조립. GLM은 서술 슬롯만, 사실
   슬롯은 JSON. 템플릿은 UI 비종속(Streamlit→React 전환 시 재사용).
9. **레포 배치**: 서버는 처음부터 별도 중립 레포(`Autoresearch-archmap`). 이
   저장소엔 추출기·CI·PR 코멘트만. 둘은 JSON 스키마만 공유(HTTP 경계).

## 12. 미결 / 리스크

- **미결 — 서버 배포·호스팅**: Streamlit 서버를 어디에 띄울지(Cloud Run 등 기존
  GCP 스택 재사용 후보), 스토리지(파일/SQLite→관리형). (Phase 0에서 확정)
- **미결 — 접근제어**: 내부 아키텍처 노출. 서버 인증(SSO/토큰)과 CI→서버 전송
  인증 방식. (Phase 0에서 확정)
- **미결 — 연결 이슈 파싱**: PR-이슈 링크를 GitHub API(closes #N, PR body,
  branch명 `<num>-...`) 중 무엇으로 확정할지.
- **미결 — LLM 비용/레이트리밋**: PR 갱신마다 GLM 호출 시 디바운스·캐시 정책.
- **리스크 — 이슈 품질이 상한**: "왜"의 1차 소스가 연결 이슈 본문이라, 이슈가
  부실하면 서술이 약해진다. 완화: issue-first 규칙(CLAUDE.md), 본문 부재 시 커밋
  메시지 폴백하고 그 사실을 표기.
- **리스크 — 서버 운영 부담**: 라이브 서버는 배포·가동·보안 책임을 수반. 완화:
  경량 스택으로 시작, 결정론 리포트는 서버 장애와 무관하게 CI 코멘트로 최소 보장.
- **리스크 — sidecar 유지 실패**: §4-② CI 게이트로 강제. 초기 백필 필요.
- **리스크 — 벽지화**: PR 코멘트로 진입점을 PR 안에 두어 완화.

## 13. 단계적 구현 개요 (상세는 plan 문서)

원칙: **결정론 골격을 먼저 세우고 GLM 서술을 얇게 얹는다.** 서버는 Phase 0부터
세우되(사용자 확정), GLM은 뒤 단계에서 슬롯을 채운다.

- **Phase 0 — 결정론 리포트 + 서버 골격 (두 레포)**:
  - *application 레포*: CI 추출기(`architecture.json`/`pr-delta.json`) + 서버로
    POST + PR 코멘트.
  - *`Autoresearch-archmap` 레포*: 수신 API → **고정 템플릿 조립(사실 슬롯만, GLM
    없이)** → 저장 → Streamlit [맵]·[PR 피드] 탭.
  - 둘은 JSON 스키마로만 연결. 이 단계만으로 계약·영향·흐름 위치를 리뷰에 제공한다.
  - (선택) 착수 전 단일 위치 로컬 스파이크로 루프 검증 후 두 레포로 분리.
- **Phase 1 — sidecar & 게이트**: `__arch__` 규약 도입, 기존 모듈 백필, CI
  staleness 게이트 → 배경 맥락(역할·담당/비담당) 채움.
- **Phase 2 — GLM 서술**: 서버에 GLM 서술기 탑재, 서술 슬롯("왜/무엇을") 채움 +
  trust-but-verify 렌더 최종화 + 디바운스/캐시.
- **Phase 3 — 다중 레포**: airflow 레포에 추출기 추가 + `POST /api/manifest`로
  같은 서버에 집계 + 교차 레포 엣지 렌더. 접근제어 강화.
- **Phase 4 — infra**: Terraform/설정 추출기 또는 수동 매니페스트 통합.

## 14. 성공 기준

- 리뷰어가 코드를 열기 전에 "이 PR이 어떤 계약을 어디까지 바꿨는가"를 리포트만으로
  파악한다(계약·영향 스트립).
- 모든 검증됨 주장이 추출기 사실과 1:1로 대응한다(허위 초록 0).
- public 표면을 바꾼 PR은 sidecar 갱신 없이 머지되지 않는다(게이트 100%).
- Phase 0 리포트가 LLM 없이도 유용하다(결정론 부분만으로 스캔 가능).
