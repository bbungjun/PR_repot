# Phase 0 — 결정론 골격 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이슈에 연결된 PR이 열리면 CI가 결정론 추출(AST)로 `architecture.json`/`pr-delta.json`을 만들어 서버에 보내고, 서버가 사실 슬롯만으로 이해 리포트를 조립·저장·표시한다 (GLM 없이).

**Architecture:** 두 레포 분담 — `Autoresearch`(로컬: `/mnt/c/Autoresarch`)에는 stdlib-only AST 추출기 + CI 워크플로우 + PR 코멘트, `Autoresearch-archmap`(로컬: `/mnt/c/PR_report`, 원격 `bbungjun/PR_repot`)에는 수신 API(FastAPI) + 검증 배지 판정 + 템플릿 렌더러(Jinja2) + 파일 저장소 + Streamlit UI. 둘은 이 레포가 소유한 JSON 스키마로만 연결된다(HTTP 경계, 코드 import 없음).

**Tech Stack:** Python 3.12 · uv · pytest · ruff / 서버: FastAPI, Jinja2, jsonschema, Streamlit / 추출기: 표준 라이브러리만(ast, json, pathlib)

## Global Constraints

- 언어: 에이전트 응답·PR 코멘트·문서·리포트 문면은 **한국어 격식체**.
- Autoresearch 커밋: `<type>: <설명>` (한국어, 현재형, ≤50자, 1커밋 1논리변경). types: feat/fix/refactor/docs/chore/exp/test.
- Autoresearch는 **issue-first**: 코드 변경 전 이슈 발행, 브랜치명 `feat/<issue번호>-<slug>`, PR 본문에 `Closes #<issue>`, Squash merge only.
- Autoresearch 추출기는 **런타임 의존성 추가 금지** — 표준 라이브러리만 사용. 위치는 `tools/archmap/` (런타임 패키지 `autoresearch/`·이미지 밖).
- 서버는 소스 레포를 체크아웃하지 않는다. 신뢰 입력은 CI가 보낸 JSON뿐.
- **Trust-but-verify 불변식**: "검증됨(verified)" 상태는 서버 렌더러(`archmap/verify.py`)만 `pr-delta` 사실로 부여한다. 이 경로 밖에서 verified를 만들 수 없게 유지한다.
- 모든 리포트 주장에는 `file:line` 앵커(GitHub blob URL)를 단다.
- JSON 스키마(`schemas/*.schema.json`)는 이 레포(archmap)가 소유·버전(`archmap-v0`)한다. 변경 시 버전을 올리고 추출기와 조율.
- 시크릿(`ARCHMAP_TOKEN` 등)·생성 데이터(`data/`)·`.env` 커밋 금지.
- Python `>=3.12`, 패키지 관리는 uv (`package = false`, Autoresearch와 동일 스타일).
- `/mnt/c/Autoresarch` 작업 트리의 기존 미커밋 파일(`.claude/docs/agent-workflow-reference.md`, `CONTRIBUTING.md`, `docs/*.html`, `output/`)은 **절대 건드리거나 커밋하지 않는다**.

---

## 사전 조건 (Task 0): 이슈 발행 + 브랜치 준비

Autoresearch는 issue-first 규칙이 있으므로 코드 변경 전에 이슈를 만든다.

- [ ] **Step 0-1: Autoresearch에 이슈 발행**

```bash
cd /mnt/c/Autoresarch
gh issue create --repo SKYAHO/Autoresearch \
  --title "[FEAT] archmap 결정론 추출기 + CI 리포트 (Phase 0)" \
  --label feature \
  --body "PR 이해 리포트 & 살아있는 아키텍처 맵 Phase 0.
- tools/archmap/ AST 추출기: architecture.json / pr-delta.json 생성
- CI 워크플로우: PR 시 추출→서버 POST→PR 코멘트 upsert, main 머지 시 매니페스트 POST
- 스펙: bbungjun/PR_repot의 spec-pr-comprehension-report.md (결정론 골격, GLM 없음)"
```

출력된 이슈 번호를 `<N>`으로 기록한다 (이후 브랜치명·PR 본문에 사용).

- [ ] **Step 0-2: main 기준 새 브랜치 생성 (기존 feat/160 작업과 미커밋 파일은 그대로 둠)**

```bash
cd /mnt/c/Autoresarch
git fetch origin main
git switch -c feat/<N>-archmap-extractor origin/main
git status --short   # 기존 미커밋 파일 목록 확인 — 이 파일들은 스테이징 금지
```

주의: `git add -A` 를 절대 쓰지 않는다. 이후 모든 커밋은 파일을 명시해 `git add <경로>` 로만 스테이징한다.

---

# Part A — 서버 레포 (`/mnt/c/PR_report`, archmap)

### Task 1: 프로젝트 스캐폴딩 + JSON 스키마 계약 + PR #120 픽스처

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `archmap/__init__.py`
- Create: `schemas/architecture.schema.json`, `schemas/pr-delta.schema.json`
- Create: `archmap/contracts.py`
- Create: `tests/__init__.py`, `tests/fixtures/architecture_120.json`, `tests/fixtures/pr_delta_120.json`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Produces: `archmap.contracts.validate_architecture(doc: dict) -> None` (스키마 위반 시 `jsonschema.ValidationError`), `archmap.contracts.validate_pr_delta(doc: dict) -> None`, 상수 `SCHEMA_VERSION = "archmap-v0"`. 픽스처 2개는 이후 모든 태스크의 테스트 입력.

- [ ] **Step 1-1: 스캐폴딩 파일 작성**

`pyproject.toml`:

```toml
[project]
name = "archmap"
version = "0.1.0"
description = "PR 이해 리포트 & 살아있는 아키텍처 맵 — 중립 라이브 서버"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "jsonschema>=4.21",
    "streamlit>=1.36",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "httpx>=0.27",
    {include-group = "lint"},
]
lint = ["ruff==0.15.18"]

[tool.uv]
package = false
default-groups = ["dev"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.env
data/
.pytest_cache/
.ruff_cache/
```

`archmap/__init__.py`, `tests/__init__.py`: 빈 파일.

- [ ] **Step 1-2: JSON 스키마 2개 작성**

`schemas/architecture.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "architecture",
  "type": "object",
  "required": ["schema_version", "repo", "revision", "stages", "modules", "contracts"],
  "properties": {
    "schema_version": {"const": "archmap-v0"},
    "repo": {"type": "string"},
    "repo_url": {"type": "string"},
    "revision": {"type": "string"},
    "contract_version": {"type": "string"},
    "stages": {"type": "array", "items": {"type": "string"}},
    "modules": {"type": "array", "items": {"$ref": "#/$defs/module"}},
    "contracts": {"type": "array", "items": {"$ref": "#/$defs/contract"}}
  },
  "$defs": {
    "module": {
      "type": "object",
      "required": ["id", "stage", "path", "public_symbols", "version_consts", "schema_fields", "imports"],
      "properties": {
        "id": {"type": "string"},
        "stage": {"type": "string"},
        "path": {"type": "string"},
        "role": {"type": ["string", "null"]},
        "owns": {"type": "array", "items": {"type": "string"}},
        "not_owns": {"type": "array", "items": {"type": "string"}},
        "public_symbols": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "kind", "line"],
            "properties": {
              "name": {"type": "string"},
              "kind": {"enum": ["function", "class", "const"]},
              "sig": {"type": ["string", "null"]},
              "line": {"type": "integer"}
            }
          }
        },
        "version_consts": {
          "type": "object",
          "additionalProperties": {
            "type": "object",
            "required": ["value", "line"],
            "properties": {"value": {"type": "string"}, "line": {"type": "integer"}}
          }
        },
        "schema_fields": {
          "type": "object",
          "additionalProperties": {"type": "array", "items": {"type": "string"}}
        },
        "imports": {"type": "array", "items": {"type": "string"}}
      }
    },
    "contract": {
      "type": "object",
      "required": ["name", "cli_args"],
      "properties": {
        "name": {"type": "string"},
        "module": {"type": "string"},
        "cli_args": {"type": "array", "items": {"type": "string"}},
        "consumed_by": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

`schemas/pr-delta.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "pr-delta",
  "type": "object",
  "required": ["schema_version", "repo", "pr", "base_sha", "head_sha", "changed_modules",
               "version_changes", "unchanged_contracts", "schema_changes", "cross_repo",
               "tests", "sidecar_stale"],
  "properties": {
    "schema_version": {"const": "archmap-v0"},
    "repo": {"type": "string"},
    "pr": {"type": "integer"},
    "base_sha": {"type": "string"},
    "head_sha": {"type": "string"},
    "issue": {
      "type": ["object", "null"],
      "properties": {
        "number": {"type": "integer"},
        "title": {"type": "string"},
        "body_excerpt": {"type": "string"}
      }
    },
    "changed_modules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "path", "stage", "symbols_changed", "public_surface_changed"],
        "properties": {
          "id": {"type": "string"},
          "path": {"type": "string"},
          "stage": {"type": "string"},
          "symbols_changed": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["name", "change"],
              "properties": {
                "name": {"type": "string"},
                "change": {"enum": ["added", "removed", "signature"]},
                "line": {"type": ["integer", "null"]}
              }
            }
          },
          "public_surface_changed": {"type": "boolean"}
        }
      }
    },
    "version_changes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["const", "module", "from", "to", "breaking"],
        "properties": {
          "const": {"type": "string"},
          "module": {"type": "string"},
          "from": {"type": ["string", "null"]},
          "to": {"type": ["string", "null"]},
          "line": {"type": ["integer", "null"]},
          "breaking": {"type": "boolean"}
        }
      }
    },
    "unchanged_contracts": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["const", "module", "value"],
        "properties": {
          "const": {"type": "string"},
          "module": {"type": "string"},
          "value": {"type": "string"},
          "line": {"type": ["integer", "null"]}
        }
      }
    },
    "schema_changes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["model", "module", "field", "change", "breaking"],
        "properties": {
          "model": {"type": "string"},
          "module": {"type": "string"},
          "field": {"type": "string"},
          "change": {"enum": ["added", "removed"]},
          "breaking": {"type": "boolean"}
        }
      }
    },
    "cross_repo": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["contract", "impact", "breaking"],
        "properties": {
          "contract": {"type": "string"},
          "impact": {"type": "string"},
          "breaking": {"type": "boolean"},
          "details": {"type": "string"}
        }
      }
    },
    "tests": {
      "type": "object",
      "required": ["files", "lines_added"],
      "properties": {
        "files": {"type": "array", "items": {"type": "string"}},
        "lines_added": {"type": "integer"}
      }
    },
    "sidecar_stale": {"type": "array", "items": {"type": "string"}}
  }
}
```

- [ ] **Step 1-3: PR #120 픽스처 작성** (README §7의 실데이터 — 커밋 `3be5fae`)

`tests/fixtures/architecture_120.json`:

```json
{
  "schema_version": "archmap-v0",
  "repo": "Autoresearch",
  "repo_url": "https://github.com/SKYAHO/Autoresearch",
  "revision": "3be5fae",
  "contract_version": "batch-contract-v1",
  "stages": ["youtube_collection", "virtual_users", "action_logs", "orchestration", "training"],
  "modules": [
    {
      "id": "action_logs.schema",
      "stage": "action_logs",
      "path": "autoresearch/action_logs/schema.py",
      "role": null,
      "owns": [],
      "not_owns": [],
      "public_symbols": [
        {"name": "EventLog", "kind": "class", "sig": null, "line": 36},
        {"name": "EventLogBatch", "kind": "class", "sig": null, "line": 223}
      ],
      "version_consts": {
        "ACTION_LOG_SCHEMA_VERSION": {"value": "action_log_schema_v1", "line": 16},
        "PROMPT_VERSION": {"value": "action_log_ctr_v4", "line": 17}
      },
      "schema_fields": {"EventLog": ["event_id", "event_timestamp", "clicked"]},
      "imports": []
    },
    {
      "id": "action_logs.llm_generator",
      "stage": "action_logs",
      "path": "autoresearch/action_logs/llm_generator.py",
      "role": null,
      "owns": [],
      "not_owns": [],
      "public_symbols": [
        {"name": "CANDIDATE_COLUMNS", "kind": "const", "sig": null, "line": 72}
      ],
      "version_consts": {},
      "schema_fields": {},
      "imports": ["action_logs.schema"]
    },
    {
      "id": "action_logs.daily",
      "stage": "action_logs",
      "path": "autoresearch/action_logs/daily.py",
      "role": null,
      "owns": [],
      "not_owns": [],
      "public_symbols": [
        {"name": "run_daily_action_log", "kind": "function",
         "sig": "(request, generator, max_users=None)", "line": 722}
      ],
      "version_consts": {},
      "schema_fields": {},
      "imports": ["action_logs.llm_generator", "action_logs.schema"]
    }
  ],
  "contracts": [
    {"name": "batch-contract-v1", "module": "jobs.action_log",
     "cli_args": ["--mode", "--partition-date", "--max-users", "--generator-name"],
     "consumed_by": ["Autoresearch-airflow"]}
  ]
}
```

`tests/fixtures/pr_delta_120.json`:

```json
{
  "schema_version": "archmap-v0",
  "repo": "Autoresearch",
  "pr": 120,
  "base_sha": "aaaaaaa",
  "head_sha": "3be5fae",
  "issue": {"number": 118, "title": "후보 목록을 프롬프트에 명시", "body_excerpt": "LLM이 후보 인덱스를 혼동하는 문제를 고친다"},
  "changed_modules": [
    {"id": "action_logs.schema", "path": "autoresearch/action_logs/schema.py", "stage": "action_logs",
     "symbols_changed": [], "public_surface_changed": false},
    {"id": "action_logs.llm_generator", "path": "autoresearch/action_logs/llm_generator.py", "stage": "action_logs",
     "symbols_changed": [{"name": "CANDIDATE_COLUMNS", "change": "signature", "line": 72}],
     "public_surface_changed": true},
    {"id": "action_logs.daily", "path": "autoresearch/action_logs/daily.py", "stage": "action_logs",
     "symbols_changed": [{"name": "run_daily_action_log", "change": "signature", "line": 722}],
     "public_surface_changed": true}
  ],
  "version_changes": [
    {"const": "PROMPT_VERSION", "module": "action_logs.schema",
     "from": "action_log_ctr_v3", "to": "action_log_ctr_v4", "line": 17, "breaking": false}
  ],
  "unchanged_contracts": [
    {"const": "ACTION_LOG_SCHEMA_VERSION", "module": "action_logs.schema",
     "value": "action_log_schema_v1", "line": 16}
  ],
  "schema_changes": [],
  "cross_repo": [
    {"contract": "batch-contract-v1", "impact": "optional-arg-added", "breaking": false,
     "details": "--max-users 선택 인자 추가"}
  ],
  "tests": {"files": ["tests/test_action_logs_daily.py", "tests/test_action_log_llm_generator.py"], "lines_added": 52},
  "sidecar_stale": []
}
```

- [ ] **Step 1-4: 실패하는 테스트 작성** — `tests/test_contracts.py`

```python
import json
from pathlib import Path

import jsonschema
import pytest

from archmap.contracts import SCHEMA_VERSION, validate_architecture, validate_pr_delta

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_schema_version_const():
    assert SCHEMA_VERSION == "archmap-v0"


def test_architecture_fixture_is_valid():
    validate_architecture(_load("architecture_120.json"))


def test_pr_delta_fixture_is_valid():
    validate_pr_delta(_load("pr_delta_120.json"))


def test_architecture_missing_required_field_rejected():
    doc = _load("architecture_120.json")
    del doc["modules"]
    with pytest.raises(jsonschema.ValidationError):
        validate_architecture(doc)


def test_pr_delta_wrong_schema_version_rejected():
    doc = _load("pr_delta_120.json")
    doc["schema_version"] = "archmap-v999"
    with pytest.raises(jsonschema.ValidationError):
        validate_pr_delta(doc)
```

- [ ] **Step 1-5: 실패 확인**

```bash
cd /mnt/c/PR_report && uv sync && uv run python -m pytest tests/test_contracts.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'archmap.contracts'`

- [ ] **Step 1-6: 구현** — `archmap/contracts.py`

```python
"""두 레포를 잇는 JSON 계약. 이 레포가 스키마를 소유·버전한다."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import jsonschema

SCHEMA_VERSION = "archmap-v0"
_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


@lru_cache
def _load_schema(name: str) -> dict:
    return json.loads((_SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validate_architecture(doc: dict) -> None:
    jsonschema.validate(doc, _load_schema("architecture.schema.json"))


def validate_pr_delta(doc: dict) -> None:
    jsonschema.validate(doc, _load_schema("pr-delta.schema.json"))
```

- [ ] **Step 1-7: 통과 확인**

```bash
uv run python -m pytest tests/test_contracts.py -v
```

Expected: 5 PASS

- [ ] **Step 1-8: 린트 + 커밋**

```bash
uv run ruff check archmap tests
git add pyproject.toml uv.lock .gitignore archmap tests schemas
git commit -m "feat: archmap 서버 스캐폴딩과 JSON 스키마 계약 추가"
```

### Task 2: 검증 배지 판정기 (`archmap/verify.py`)

**Files:**
- Create: `archmap/verify.py`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: pr-delta dict (Task 1 스키마).
- Produces: `build_claims(pr_delta: dict) -> list[dict]` — 각 claim은 `{"status": "verified"|"warning"|"narrated", "text": str, "module": str|None, "line": int|None}`. 상수 `VERIFIED = "verified"`, `WARNING = "warning"`, `NARRATED = "narrated"`. Task 3 렌더러가 사용.

**판정 규칙 (스펙 §7 — 이 모듈만 verified를 부여할 수 있다):**
- `unchanged_contracts` 항목 → verified "X 불변".
- `version_changes` 항목 → breaking=false면 verified "비파괴 변경", true면 warning.
- `schema_changes` 항목 → breaking 여부에 따라 warning/verified.
- `cross_repo` 항목 → breaking=false면 verified, true면 warning (+ "소비자 전환 PR 필요").
- public_surface_changed=true인 각 changed_module → `tests.files` 중 대응 테스트 파일이 있으면 verified "테스트 커버됨", 없으면 warning "테스트 없음". 대응 규칙: 테스트 파일 이름(`test_` 제거·`.py` 제거)에 **모듈 id의 마지막 구성요소(모듈명)** 가 포함되면 대응 (패키지명 매칭은 같은 패키지의 무관한 테스트까지 커버로 오판하므로 쓰지 않는다).

- [ ] **Step 2-1: 실패하는 테스트 작성** — `tests/test_verify.py`

```python
import json
from pathlib import Path

from archmap.verify import NARRATED, VERIFIED, WARNING, build_claims

FIXTURES = Path(__file__).parent / "fixtures"


def _delta():
    return json.loads((FIXTURES / "pr_delta_120.json").read_text(encoding="utf-8"))


def test_unchanged_contract_is_verified():
    claims = build_claims(_delta())
    hit = [c for c in claims if "ACTION_LOG_SCHEMA_VERSION" in c["text"] and "불변" in c["text"]]
    assert hit and hit[0]["status"] == VERIFIED
    assert hit[0]["module"] == "action_logs.schema" and hit[0]["line"] == 16


def test_nonbreaking_version_change_is_verified():
    claims = build_claims(_delta())
    hit = [c for c in claims if "PROMPT_VERSION" in c["text"]]
    assert hit and hit[0]["status"] == VERIFIED and "action_log_ctr_v4" in hit[0]["text"]


def test_breaking_version_change_is_warning():
    d = _delta()
    d["version_changes"][0]["breaking"] = True
    claims = build_claims(d)
    hit = [c for c in claims if "PROMPT_VERSION" in c["text"]]
    assert hit[0]["status"] == WARNING


def test_tests_covered_module_verified_and_uncovered_warned():
    d = _delta()
    d["tests"]["files"] = ["tests/test_action_logs_daily.py"]
    claims = build_claims(d)
    daily = [c for c in claims if c["module"] == "action_logs.daily" and "테스트" in c["text"]]
    llm = [c for c in claims if c["module"] == "action_logs.llm_generator" and "테스트" in c["text"]]
    assert daily[0]["status"] == VERIFIED
    assert llm[0]["status"] == WARNING


def test_breaking_cross_repo_is_warning():
    d = _delta()
    d["cross_repo"][0]["breaking"] = True
    claims = build_claims(d)
    hit = [c for c in claims if "batch-contract-v1" in c["text"]]
    assert hit[0]["status"] == WARNING


def test_no_claim_is_narrated_by_default():
    assert all(c["status"] != NARRATED for c in build_claims(_delta()))
```

- [ ] **Step 2-2: 실패 확인** — `uv run python -m pytest tests/test_verify.py -v` → `ModuleNotFoundError`

- [ ] **Step 2-3: 구현** — `archmap/verify.py`

```python
"""pr-delta 사실로부터 검증 배지를 결정론적으로 부여한다.

핵심 불변식: verified 상태는 이 모듈만 부여한다. 서술기(LLM) 출력은
어떤 경로로도 여기를 거치지 않으므로 "자신 있게 틀린 검증"이 구조적으로 불가능하다.
"""
from __future__ import annotations

VERIFIED = "verified"
WARNING = "warning"
NARRATED = "narrated"


def _claim(status: str, text: str, module: str | None = None, line: int | None = None) -> dict:
    return {"status": status, "text": text, "module": module, "line": line}


def _test_file_covers(module_id: str, test_files: list[str]) -> bool:
    # 모듈 id의 마지막 구성요소만 대조한다 — 패키지명 대조는 같은 패키지의
    # 무관한 테스트 변경을 "커버됨"으로 오판한다(허위 초록 금지).
    mod_name = module_id.rsplit(".", 1)[-1]
    for f in test_files:
        stem = f.rsplit("/", 1)[-1].removeprefix("test_").removesuffix(".py")
        if mod_name in stem:
            return True
    return False


def build_claims(pr_delta: dict) -> list[dict]:
    claims: list[dict] = []
    for c in pr_delta["unchanged_contracts"]:
        claims.append(_claim(
            VERIFIED, f'{c["const"]} = "{c["value"]}" 불변 — 저장·생성 계약이 바뀌지 않았습니다',
            c["module"], c.get("line")))
    for v in pr_delta["version_changes"]:
        status = WARNING if v["breaking"] else VERIFIED
        label = "파괴적 변경" if v["breaking"] else "비파괴 변경"
        claims.append(_claim(
            status, f'{v["const"]}: {v["from"]} → {v["to"]} ({label})',
            v["module"], v.get("line")))
    for s in pr_delta["schema_changes"]:
        status = WARNING if s["breaking"] else VERIFIED
        kind = {"added": "필드 추가", "removed": "필드 제거"}[s["change"]]
        claims.append(_claim(status, f'{s["model"]}.{s["field"]} {kind}', s["module"]))
    for x in pr_delta["cross_repo"]:
        if x["breaking"]:
            claims.append(_claim(
                WARNING, f'{x["contract"]} 파괴적 영향({x["impact"]}) — 소비자 전환 PR 필요'))
        else:
            claims.append(_claim(VERIFIED, f'{x["contract"]} 하위호환 영향({x["impact"]})'))
    test_files = pr_delta["tests"]["files"]
    for m in pr_delta["changed_modules"]:
        if not m["public_surface_changed"]:
            continue
        if _test_file_covers(m["id"], test_files):
            claims.append(_claim(VERIFIED, "테스트 커버됨 — 대응 테스트 파일이 함께 변경되었습니다", m["id"]))
        else:
            claims.append(_claim(WARNING, "테스트 없음 — public 표면이 바뀌었으나 대응 테스트 변경이 없습니다", m["id"]))
    return claims
```

- [ ] **Step 2-4: 통과 확인** — `uv run python -m pytest tests/test_verify.py -v` → 6 PASS

- [ ] **Step 2-5: 커밋**

```bash
uv run ruff check archmap tests
git add archmap/verify.py tests/test_verify.py
git commit -m "feat: pr-delta 사실 기반 검증 배지 판정기 추가"
```

### Task 3: 템플릿 조립 렌더러 (`archmap/render.py`)

**Files:**
- Create: `archmap/render.py`, `templates/pr_report.html.j2`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `archmap.verify.build_claims`, Task 1 픽스처.
- Produces: `render_report(architecture: dict, pr_delta: dict) -> str` (완결 HTML 문자열), `anchor_url(repo_url: str, sha: str, path: str, line: int | None) -> str`. Task 5 API가 사용.

- [ ] **Step 3-1: 실패하는 테스트 작성** — `tests/test_render.py`

```python
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
```

- [ ] **Step 3-2: 실패 확인** — `uv run python -m pytest tests/test_render.py -v` → `ModuleNotFoundError`

- [ ] **Step 3-3: 템플릿 작성** — `templates/pr_report.html.j2`

```html
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>PR #{{ pr_delta.pr }} · 이해 리포트</title>
<style>
  body { font-family: 'Segoe UI', 'Malgun Gothic', sans-serif; max-width: 960px;
         margin: 2rem auto; padding: 0 1rem; color: #1a1a2e; }
  h1 { font-size: 1.3rem; } h2 { font-size: 1.05rem; margin-top: 2rem;
       border-bottom: 2px solid #eee; padding-bottom: .3rem; }
  .flow { display: flex; gap: .5rem; flex-wrap: wrap; margin: 1rem 0; }
  .stage { padding: .4rem .8rem; border-radius: 6px; background: #f0f0f5; color: #888; }
  .stage.hit { background: #2d6cdf; color: #fff; font-weight: 600; }
  .claim { display: flex; gap: .6rem; align-items: baseline; padding: .45rem .6rem;
           border-radius: 6px; margin: .3rem 0; }
  .claim.verified { background: #e8f5ec; } .claim.warning { background: #fdeaea; }
  .badge { font-size: .75rem; padding: .1rem .5rem; border-radius: 999px; white-space: nowrap; }
  .badge-verified { background: #1f8a4c; color: #fff; }
  .badge-warning  { background: #c53030; color: #fff; }
  .anchor { font-size: .8rem; color: #2d6cdf; text-decoration: none; margin-left: auto; }
  .narration-slot { background: #f4f4f7; color: #777; border: 1px dashed #ccc;
                    border-radius: 8px; padding: 1rem; margin: 1rem 0; }
  table { border-collapse: collapse; width: 100%; font-size: .9rem; }
  td, th { border: 1px solid #e5e5ee; padding: .4rem .6rem; text-align: left; }
  .meta { color: #666; font-size: .85rem; }
</style>
</head>
<body>
<h1>PR #{{ pr_delta.pr }}{% if pr_delta.issue %} · {{ pr_delta.issue.title }}{% endif %}</h1>
<p class="meta">{{ pr_delta.repo }} · {{ pr_delta.base_sha[:7] }} → {{ pr_delta.head_sha[:7] }}
{% if pr_delta.issue %} · 이슈 #{{ pr_delta.issue.number }}{% endif %}</p>

<h2>어디에 · 흐름 위치</h2>
<div class="flow">
{% for stage in architecture.stages %}
  <span class="stage{% if stage in hit_stages %} hit{% endif %}">{{ stage }}</span>{% if not loop.last %}<span>→</span>{% endif %}
{% endfor %}
</div>

<h2>계약 &amp; 영향 (검증은 렌더러가 pr-delta 사실로만 부여)</h2>
{% for c in claims %}
<div class="claim {{ c.status }}">
  <span class="badge badge-{{ c.status }}">{{ "검증됨" if c.status == "verified" else "주의" }}</span>
  <span>{{ c.text }}</span>
  {% if c.anchor %}<a class="anchor" href="{{ c.anchor }}">⚓ {{ c.anchor_label }}</a>{% endif %}
</div>
{% endfor %}

<h2>무엇을 · 변경 모듈</h2>
<table>
<tr><th>모듈</th><th>스테이지</th><th>public 표면</th><th>변경 심볼</th><th>앵커</th></tr>
{% for m in changed_modules %}
<tr>
  <td>{{ m.id }}</td><td>{{ m.stage }}</td>
  <td>{{ "변경" if m.public_surface_changed else "유지" }}</td>
  <td>{% for s in m.symbols_changed %}{{ s.name }}({{ s.change }}){% if not loop.last %}, {% endif %}{% endfor %}</td>
  <td><a class="anchor" href="{{ m.anchor }}">⚓ {{ m.path }}</a></td>
</tr>
{% endfor %}
</table>

<h2>테스트</h2>
<p>{{ pr_delta.tests.files | length }}개 파일 변경, +{{ pr_delta.tests.lines_added }}줄:
{% for f in pr_delta.tests.files %}<code>{{ f }}</code>{% if not loop.last %}, {% endif %}{% endfor %}</p>

<h2>왜 (서술)</h2>
<div class="narration-slot">
  서술 슬롯 — Phase 2에서 GLM이 이슈·diff 기반 "무엇을/왜"를 채웁니다.
  {% if pr_delta.issue %}현재는 이슈 발췌만 표시합니다: “{{ pr_delta.issue.body_excerpt }}”{% endif %}
</div>
</body>
</html>
```

- [ ] **Step 3-4: 구현** — `archmap/render.py`

```python
"""고정 HTML 템플릿의 사실 슬롯을 채워 리포트를 조립한다. UI 비종속."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from archmap.verify import build_claims

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(_TEMPLATE_DIR),
                   autoescape=select_autoescape(["html"]))


def anchor_url(repo_url: str, sha: str, path: str, line: int | None) -> str:
    url = f"{repo_url}/blob/{sha}/{path}"
    return f"{url}#L{line}" if line else url


def render_report(architecture: dict, pr_delta: dict) -> str:
    repo_url = architecture.get("repo_url", "")
    sha = pr_delta["head_sha"]
    path_by_module = {m["id"]: m["path"] for m in architecture["modules"]}

    claims = build_claims(pr_delta)
    for c in claims:
        path = path_by_module.get(c["module"]) if c["module"] else None
        if repo_url and path:
            c["anchor"] = anchor_url(repo_url, sha, path, c["line"])
            c["anchor_label"] = f'{path.rsplit("/", 1)[-1]}#L{c["line"]}' if c["line"] else path
        else:
            c["anchor"] = None

    changed_modules = []
    for m in pr_delta["changed_modules"]:
        line = next((s.get("line") for s in m["symbols_changed"] if s.get("line")), None)
        changed_modules.append({**m, "anchor": anchor_url(repo_url, sha, m["path"], line)})

    hit_stages = {m["stage"] for m in pr_delta["changed_modules"]}
    template = _env.get_template("pr_report.html.j2")
    return template.render(architecture=architecture, pr_delta=pr_delta,
                           claims=claims, changed_modules=changed_modules,
                           hit_stages=hit_stages)
```

- [ ] **Step 3-5: 통과 확인** — `uv run python -m pytest tests/test_render.py -v` → 4 PASS

- [ ] **Step 3-6: 커밋**

```bash
uv run ruff check archmap tests
git add archmap/render.py templates tests/test_render.py
git commit -m "feat: 사실 슬롯 템플릿 조립 렌더러 추가"
```

### Task 4: 저장소 (`archmap/storage.py`)

**Files:**
- Create: `archmap/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Produces: `Store(root: Path)` —
  - `save_manifest(arch: dict) -> None` (repo별 latest + revision 이력)
  - `load_manifests() -> dict[str, dict]` (repo명 → 최신 architecture)
  - `save_report(pr_delta: dict, html: str) -> None`
  - `list_reports() -> list[dict]` (최신 갱신순 메타: repo, pr, head_sha, issue_title, updated)
  - `load_report_html(repo: str, pr: int) -> str | None`
- Task 5 API·Task 6 UI가 사용.

- [ ] **Step 4-1: 실패하는 테스트 작성** — `tests/test_storage.py`

```python
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
```

- [ ] **Step 4-2: 실패 확인** — `uv run python -m pytest tests/test_storage.py -v` → `ModuleNotFoundError`

- [ ] **Step 4-3: 구현** — `archmap/storage.py`

```python
"""파일 기반 저장소. Phase 0은 로컬 디렉터리, 필요 시 관리형으로 교체한다."""
from __future__ import annotations

import json
import time
from pathlib import Path


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    # --- manifests -------------------------------------------------
    def save_manifest(self, arch: dict) -> None:
        repo = arch["repo"]
        latest = self.root / "manifests" / f"{repo}.json"
        history = self.root / "manifests" / "history" / repo / f'{arch["revision"]}.json'
        for path in (latest, history):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(arch, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_manifests(self) -> dict[str, dict]:
        result = {}
        for path in sorted((self.root / "manifests").glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            result[doc["repo"]] = doc
        return result

    # --- reports ---------------------------------------------------
    def _report_dir(self, repo: str, pr: int) -> Path:
        return self.root / "reports" / repo / f"pr-{pr}"

    def save_report(self, pr_delta: dict, html: str) -> None:
        d = self._report_dir(pr_delta["repo"], pr_delta["pr"])
        d.mkdir(parents=True, exist_ok=True)
        (d / f'{pr_delta["head_sha"]}.html').write_text(html, encoding="utf-8")
        (d / "latest.html").write_text(html, encoding="utf-8")
        issue = pr_delta.get("issue") or {}
        meta = {"repo": pr_delta["repo"], "pr": pr_delta["pr"],
                "head_sha": pr_delta["head_sha"],
                "issue_title": issue.get("title", ""), "updated": time.time()}
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        (d / "pr-delta.json").write_text(
            json.dumps(pr_delta, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_reports(self) -> list[dict]:
        metas = [json.loads(p.read_text(encoding="utf-8"))
                 for p in (self.root / "reports").glob("*/pr-*/meta.json")]
        return sorted(metas, key=lambda m: m["updated"], reverse=True)

    def load_report_html(self, repo: str, pr: int) -> str | None:
        path = self._report_dir(repo, pr) / "latest.html"
        return path.read_text(encoding="utf-8") if path.exists() else None
```

`glob`이 빈 디렉터리에서 조용히 빈 결과를 내도록 `list_reports`/`load_manifests`는 루트 부재 시에도 동작해야 한다 — `Path.glob`은 부모가 없으면 빈 iterator를 반환하므로 별도 처리 불필요.

- [ ] **Step 4-4: 통과 확인** — `uv run python -m pytest tests/test_storage.py -v` → 4 PASS

- [ ] **Step 4-5: 커밋**

```bash
uv run ruff check archmap tests
git add archmap/storage.py tests/test_storage.py
git commit -m "feat: 리포트·매니페스트 파일 저장소 추가"
```

### Task 5: 수신 API (`archmap/api.py`)

**Files:**
- Create: `archmap/api.py`, `.env.example`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `contracts.validate_*`, `render.render_report`, `storage.Store`.
- Produces: `create_app() -> fastapi.FastAPI`. 엔드포인트:
  - `POST /api/pr-report` body `{"architecture": {...}, "pr_delta": {...}}` → `{"report_url": str}` (검증 실패 400, 토큰 불일치 401)
  - `POST /api/manifest` body `architecture.json` → `{"ok": true}`
  - `GET /reports/{repo}/{pr}` → 렌더된 HTML
- 환경변수: `ARCHMAP_TOKEN`(필수, 헤더 `X-Archmap-Token` 대조), `ARCHMAP_DATA_DIR`(기본 `./data`), `ARCHMAP_BASE_URL`(기본 `http://localhost:8000`).

- [ ] **Step 5-1: 실패하는 테스트 작성** — `tests/test_api.py`

```python
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archmap.api import create_app

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = {"X-Archmap-Token": "test-token"}


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHMAP_TOKEN", "test-token")
    monkeypatch.setenv("ARCHMAP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ARCHMAP_BASE_URL", "http://testserver")
    return TestClient(create_app())


def test_pr_report_roundtrip(client):
    body = {"architecture": _load("architecture_120.json"), "pr_delta": _load("pr_delta_120.json")}
    res = client.post("/api/pr-report", json=body, headers=TOKEN)
    assert res.status_code == 200
    assert res.json()["report_url"] == "http://testserver/reports/Autoresearch/120"
    page = client.get("/reports/Autoresearch/120")
    assert page.status_code == 200 and "PR #120" in page.text


def test_manifest_accepted(client):
    res = client.post("/api/manifest", json=_load("architecture_120.json"), headers=TOKEN)
    assert res.status_code == 200 and res.json() == {"ok": True}


def test_invalid_payload_rejected(client):
    bad = _load("pr_delta_120.json")
    del bad["changed_modules"]
    body = {"architecture": _load("architecture_120.json"), "pr_delta": bad}
    assert client.post("/api/pr-report", json=body, headers=TOKEN).status_code == 400


def test_missing_token_rejected(client):
    assert client.post("/api/manifest", json=_load("architecture_120.json")).status_code == 401


def test_unknown_report_404(client):
    assert client.get("/reports/Autoresearch/999").status_code == 404
```

- [ ] **Step 5-2: 실패 확인** — `uv run python -m pytest tests/test_api.py -v` → `ModuleNotFoundError`

- [ ] **Step 5-3: 구현** — `archmap/api.py`

```python
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
        _store().save_report(pr_delta, html)
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
        _store().save_manifest(doc)
        return {"ok": True}

    @app.get("/reports/{repo}/{pr}", response_class=HTMLResponse)
    async def report(repo: str, pr: int):
        html = _store().load_report_html(repo, pr)
        if html is None:
            raise HTTPException(status_code=404, detail="리포트가 없습니다")
        return html

    return app


app = create_app()
```

`.env.example`:

```
ARCHMAP_TOKEN=change-me
ARCHMAP_DATA_DIR=data
ARCHMAP_BASE_URL=http://localhost:8000
```

- [ ] **Step 5-4: 통과 확인** — `uv run python -m pytest tests/test_api.py -v` → 5 PASS

- [ ] **Step 5-5: 커밋**

```bash
uv run ruff check archmap tests
git add archmap/api.py tests/test_api.py .env.example
git commit -m "feat: pr-report·manifest 수신 API 추가"
```

### Task 6: Streamlit UI + 실행 문서

**Files:**
- Create: `archmap/ui.py`
- Modify: `README.md` (기존 인수인계 문서 하단에 "로컬 실행" 섹션 추가)
- Test: `tests/test_ui_import.py` (스모크)

**Interfaces:**
- Consumes: `storage.Store`.
- Produces: `uv run streamlit run archmap/ui.py`로 뜨는 2탭 UI — [전체 맵](매니페스트 집계), [PR 리포트 피드](저장된 리포트 임베드).

- [ ] **Step 6-1: 스모크 테스트 작성** — `tests/test_ui_import.py`

```python
import importlib


def test_ui_module_imports():
    importlib.import_module("archmap.ui")
```

- [ ] **Step 6-2: 실패 확인** — `uv run python -m pytest tests/test_ui_import.py -v` → `ModuleNotFoundError`

- [ ] **Step 6-3: 구현** — `archmap/ui.py`

```python
"""Streamlit 웹 UI — [전체 맵] · [PR 리포트 피드]. 템플릿은 UI 비종속(§4-④)."""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from archmap.storage import Store


def main() -> None:
    st.set_page_config(page_title="Autoresearch archmap", layout="wide")
    store = Store(Path(os.environ.get("ARCHMAP_DATA_DIR", "data")))
    tab_map, tab_feed = st.tabs(["전체 맵", "PR 리포트 피드"])

    with tab_map:
        manifests = store.load_manifests()
        if not manifests:
            st.info("아직 수신된 매니페스트가 없습니다. CI가 POST /api/manifest 를 호출하면 채워집니다.")
        for repo, arch in manifests.items():
            st.subheader(f'{repo} @ {arch["revision"][:7]}')
            st.caption(" → ".join(arch["stages"]))
            by_stage: dict[str, list[dict]] = {}
            for m in arch["modules"]:
                by_stage.setdefault(m["stage"], []).append(m)
            cols = st.columns(max(len(by_stage), 1))
            for col, (stage, modules) in zip(cols, by_stage.items()):
                with col:
                    st.markdown(f"**{stage}** ({len(modules)})")
                    for m in modules:
                        consts = ", ".join(f'{k}={v["value"]}' for k, v in m["version_consts"].items())
                        st.markdown(f'- `{m["id"]}`' + (f" — {consts}" if consts else ""))

    with tab_feed:
        reports = store.list_reports()
        if not reports:
            st.info("아직 수신된 PR 리포트가 없습니다.")
        else:
            labels = [f'{r["repo"]} PR #{r["pr"]} · {r["issue_title"]}' for r in reports]
            picked = st.selectbox("리포트 선택 (최신 갱신순)", range(len(labels)),
                                  format_func=lambda i: labels[i])
            meta = reports[picked]
            html = store.load_report_html(meta["repo"], meta["pr"])
            if html:
                components.html(html, height=1400, scrolling=True)


main()
```

- [ ] **Step 6-4: 통과 확인 + 수동 스모크**

```bash
uv run python -m pytest -v          # 전체 스위트 통과 확인
uv run ruff check archmap tests
```

수동 스모크 (터미널 2개):

```bash
# 터미널 1 — API
ARCHMAP_TOKEN=dev uv run uvicorn archmap.api:app --port 8000
# 터미널 2 — 픽스처 주입 후 UI
cd /mnt/c/PR_report
curl -s -X POST localhost:8000/api/manifest -H 'X-Archmap-Token: dev' \
  -H 'Content-Type: application/json' --data @tests/fixtures/architecture_120.json
python - <<'EOF'
import json, urllib.request
body = {"architecture": json.load(open("tests/fixtures/architecture_120.json", encoding="utf-8")),
        "pr_delta": json.load(open("tests/fixtures/pr_delta_120.json", encoding="utf-8"))}
req = urllib.request.Request("http://localhost:8000/api/pr-report",
    data=json.dumps(body).encode(), headers={"X-Archmap-Token": "dev", "Content-Type": "application/json"})
print(urllib.request.urlopen(req).read().decode())
EOF
uv run streamlit run archmap/ui.py   # 브라우저에서 두 탭 확인
```

Expected: 맵 탭에 Autoresearch 스테이지·모듈, 피드 탭에 PR #120 리포트가 보인다.

- [ ] **Step 6-5: README에 실행 섹션 추가 후 커밋**

`README.md` 말미(§11 앞)에 추가:

````markdown
## 로컬 실행 (Phase 0)

```bash
uv sync
ARCHMAP_TOKEN=dev uv run uvicorn archmap.api:app --port 8000   # 수신 API
uv run streamlit run archmap/ui.py                              # 웹 UI (맵·피드 탭)
uv run python -m pytest                                         # 테스트
```

CI 연동 환경변수: `ARCHMAP_TOKEN`(공유 토큰), `ARCHMAP_BASE_URL`(리포트 링크 베이스), `ARCHMAP_DATA_DIR`(저장 위치, 기본 `data/`).
````

```bash
git add archmap/ui.py tests/test_ui_import.py README.md
git commit -m "feat: Streamlit 맵·피드 탭 UI와 실행 문서 추가"
git push origin main
```

---

# Part B — 추출기 (`/mnt/c/Autoresarch`, tools/archmap)

> Task 0에서 만든 `feat/<N>-archmap-extractor` 브랜치에서 진행한다.
> 기존 미커밋 파일이 있으므로 **항상 파일을 명시해 `git add`** 한다.

### Task 7: 추출기 스캐폴딩 + 린트 커버 확장

**Files:**
- Create: `tools/__init__.py`, `tools/archmap/__init__.py`
- Modify: `.github/workflows/lint.yml` (ruff 대상에 `tools` 추가)

**Interfaces:**
- Produces: `tools.archmap` 패키지 (이후 태스크의 모듈이 들어감). 테스트는 기존 관례대로 `tests/test_archmap_*.py` 평면 배치, `uv run python -m pytest`로 실행(레포 루트가 sys.path에 오르므로 `tools.*` import 가능).

- [ ] **Step 7-1: 빈 패키지 생성**

```bash
cd /mnt/c/Autoresarch
mkdir -p tools/archmap && touch tools/__init__.py tools/archmap/__init__.py
```

- [ ] **Step 7-2: lint.yml의 ruff 명령 수정**

`.github/workflows/lint.yml`에서 `uv run --no-sync ruff check autoresearch tests` → `uv run --no-sync ruff check autoresearch tests tools` 로 변경.

- [ ] **Step 7-3: 확인 + 커밋**

```bash
uv run --no-sync ruff check autoresearch tests tools
git add tools .github/workflows/lint.yml
git commit -m "chore: archmap 추출기 패키지 골격과 린트 대상 추가"
```

### Task 8: 모듈 정보 추출 (`tools/archmap/module_info.py`)

**Files:**
- Create: `tools/archmap/module_info.py`
- Test: `tests/test_archmap_module_info.py`

**Interfaces:**
- Produces: `extract_module_info(source: str, module_id: str, stage: str, path: str) -> dict` — architecture.json의 module 항목(스키마 `archmap-v0`)을 반환. 내부 함수 `_format_sig(fn) -> str`.
- 규칙: public 심볼 = 모듈 최상위의 밑줄 없는 def/class/대입. 버전 상수 = 대문자 이름이 `_VERSION`으로 끝나거나 허용목록(`TARGET_COUNTRY`)에 있고 값이 문자열 리터럴. 스키마 필드 = `BaseModel`을 상속한 클래스의 어노테이션 필드(밑줄·`model_config` 제외). imports = `autoresearch.` 내부 import만, 접두사 제거.
- **모듈을 import 하지 않는다** — `ast.parse`만 사용(부작용 회피, 스펙 §4-①).

- [ ] **Step 8-1: 실패하는 테스트 작성** — `tests/test_archmap_module_info.py`

```python
import textwrap

from tools.archmap.module_info import extract_module_info

SAMPLE = textwrap.dedent('''
    """예시 모듈."""
    from pydantic import BaseModel
    from autoresearch.action_logs import candidate
    import autoresearch.action_logs.schema
    import json

    ACTION_LOG_SCHEMA_VERSION = "action_log_schema_v1"
    PROMPT_VERSION = "action_log_ctr_v4"
    TARGET_COUNTRY = "KR"
    MAX_RETRY = 3
    _PRIVATE = "x"

    CANDIDATE_COLUMNS = ["index", "title"]


    class EventLog(BaseModel):
        event_id: str
        clicked: bool
        model_config = {"frozen": True}
        _cache: dict = {}


    class Helper:
        pass


    def run_daily(request, generator, max_users=None, *, seed=42):
        pass


    def _hidden():
        pass
''')


def _info():
    return extract_module_info(SAMPLE, "action_logs.schema", "action_logs",
                               "autoresearch/action_logs/schema.py")


def test_identity_fields():
    info = _info()
    assert info["id"] == "action_logs.schema"
    assert info["stage"] == "action_logs"
    assert info["path"] == "autoresearch/action_logs/schema.py"
    assert info["role"] is None and info["owns"] == [] and info["not_owns"] == []


def test_public_symbols_exclude_private():
    names = {s["name"]: s for s in _info()["public_symbols"]}
    assert "run_daily" in names and "_hidden" not in names and "_PRIVATE" not in names
    assert names["EventLog"]["kind"] == "class"
    assert names["CANDIDATE_COLUMNS"]["kind"] == "const"
    assert names["run_daily"]["sig"] == "(request, generator, max_users=None, *, seed=42)"
    assert names["run_daily"]["line"] > 0


def test_version_consts_rule():
    consts = _info()["version_consts"]
    assert consts["ACTION_LOG_SCHEMA_VERSION"]["value"] == "action_log_schema_v1"
    assert consts["PROMPT_VERSION"]["value"] == "action_log_ctr_v4"
    assert consts["TARGET_COUNTRY"]["value"] == "KR"      # 허용목록
    assert "MAX_RETRY" not in consts                       # 문자열 아님 + _VERSION 아님
    assert consts["PROMPT_VERSION"]["line"] > 0


def test_schema_fields_only_from_basemodel():
    fields = _info()["schema_fields"]
    assert fields == {"EventLog": ["event_id", "clicked"]}   # Helper 제외, model_config·_cache 제외


def test_imports_internal_only_prefix_stripped():
    assert _info()["imports"] == ["action_logs", "action_logs.schema"]
```

- [ ] **Step 8-2: 실패 확인**

```bash
uv run --no-sync python -m pytest tests/test_archmap_module_info.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tools.archmap.module_info'`

- [ ] **Step 8-3: 구현** — `tools/archmap/module_info.py`

```python
"""AST 기반 모듈 정보 추출 — 모듈을 import 하지 않는다 (부작용 회피)."""
from __future__ import annotations

import ast

VERSION_CONST_ALLOWLIST = {"TARGET_COUNTRY"}
INTERNAL_ROOT = "autoresearch"


def _is_version_const(name: str) -> bool:
    return name.isupper() and (name.endswith("_VERSION") or name in VERSION_CONST_ALLOWLIST)


def _format_sig(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    a = fn.args
    parts: list[str] = []
    pos = list(a.posonlyargs) + list(a.args)
    defaults = [None] * (len(pos) - len(a.defaults)) + list(a.defaults)
    for arg, default in zip(pos, defaults):
        parts.append(arg.arg if default is None else f"{arg.arg}={ast.unparse(default)}")
    if a.vararg:
        parts.append(f"*{a.vararg.arg}")
    elif a.kwonlyargs:
        parts.append("*")
    for arg, default in zip(a.kwonlyargs, a.kw_defaults):
        parts.append(arg.arg if default is None else f"{arg.arg}={ast.unparse(default)}")
    if a.kwarg:
        parts.append(f"**{a.kwarg.arg}")
    return f"({', '.join(parts)})"


def _is_basemodel(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "BaseModel":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
            return True
    return False


def _class_fields(node: ast.ClassDef) -> list[str]:
    fields = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            if not stmt.target.id.startswith("_") and stmt.target.id != "model_config":
                fields.append(stmt.target.id)
    return fields


def _normalize_import(module: str) -> str | None:
    if module == INTERNAL_ROOT:
        return None
    if module.startswith(INTERNAL_ROOT + "."):
        return module.removeprefix(INTERNAL_ROOT + ".")
    return None


def extract_module_info(source: str, module_id: str, stage: str, path: str) -> dict:
    tree = ast.parse(source)
    public_symbols: list[dict] = []
    version_consts: dict[str, dict] = {}
    schema_fields: dict[str, list[str]] = {}
    imports: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                public_symbols.append({"name": node.name, "kind": "function",
                                       "sig": _format_sig(node), "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                public_symbols.append({"name": node.name, "kind": "class",
                                       "sig": None, "line": node.lineno})
            if _is_basemodel(node):
                schema_fields[node.name] = _class_fields(node)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if not name.startswith("_"):
                public_symbols.append({"name": name, "kind": "const",
                                       "sig": None, "line": node.lineno})
            if _is_version_const(name) and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                version_consts[name] = {"value": node.value.value, "line": node.lineno}
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if (norm := _normalize_import(alias.name)) is not None:
                    imports.add(norm)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if (norm := _normalize_import(node.module)) is not None:
                imports.add(norm)

    return {"id": module_id, "stage": stage, "path": path,
            "role": None, "owns": [], "not_owns": [],
            "public_symbols": public_symbols, "version_consts": version_consts,
            "schema_fields": schema_fields, "imports": sorted(imports)}
```

- [ ] **Step 8-4: 통과 확인** — `uv run --no-sync python -m pytest tests/test_archmap_module_info.py -v` → 5 PASS

- [ ] **Step 8-5: 커밋**

```bash
uv run --no-sync ruff check autoresearch tests tools
git add tools/archmap/module_info.py tests/test_archmap_module_info.py
git commit -m "feat: AST 기반 모듈 정보 추출기 추가"
```

### Task 9: CLI 계약 추출 (`tools/archmap/cli_contract.py`)

**Files:**
- Create: `tools/archmap/cli_contract.py`
- Test: `tests/test_archmap_cli_contract.py`

**Interfaces:**
- Produces: `extract_cli_args(source: str) -> list[str]` — 모듈 소스에서 `*.add_argument("--flag", ...)` 호출의 플래그를 소스 순서대로(중복 제거) 반환.

- [ ] **Step 9-1: 실패하는 테스트 작성** — `tests/test_archmap_cli_contract.py`

```python
import textwrap

from tools.archmap.cli_contract import extract_cli_args

SAMPLE = textwrap.dedent('''
    import argparse

    def _build_parser():
        p = argparse.ArgumentParser()
        p.add_argument("--mode", choices=["single", "shard"], required=True)
        p.add_argument("--partition-date", required=True)
        p.add_argument("--max-users", type=int)
        p.add_argument("positional_arg")
        group = p.add_argument_group("etc")
        group.add_argument("--seed", type=int, default=42)
        p.add_argument("--mode", help="중복은 한 번만")
        return p
''')


def test_extracts_flags_in_source_order_dedup():
    assert extract_cli_args(SAMPLE) == ["--mode", "--partition-date", "--max-users", "--seed"]


def test_no_parser_returns_empty():
    assert extract_cli_args("x = 1\n") == []
```

- [ ] **Step 9-2: 실패 확인** — `uv run --no-sync python -m pytest tests/test_archmap_cli_contract.py -v` → `ModuleNotFoundError`

- [ ] **Step 9-3: 구현** — `tools/archmap/cli_contract.py`

```python
"""argparse add_argument 호출에서 공개 CLI 인자 표면을 추출한다 (batch-contract)."""
from __future__ import annotations

import ast


def extract_cli_args(source: str) -> list[str]:
    flags: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument" and node.args):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) \
                and first.value.startswith("--") and first.value not in flags:
            flags.append(first.value)
    return flags
```

- [ ] **Step 9-4: 통과 확인** — 2 PASS

- [ ] **Step 9-5: 커밋**

```bash
uv run --no-sync ruff check autoresearch tests tools
git add tools/archmap/cli_contract.py tests/test_archmap_cli_contract.py
git commit -m "feat: argparse 기반 CLI 계약 추출기 추가"
```

### Task 10: architecture.json 빌더 (`tools/archmap/build.py` + `__main__.py`)

**Files:**
- Create: `tools/archmap/build.py`, `tools/archmap/__main__.py`
- Test: `tests/test_archmap_build.py`

**Interfaces:**
- Consumes: `extract_module_info`, `extract_cli_args`.
- Produces:
  - `build_architecture(repo_root: Path, repo: str, revision: str, repo_url: str) -> dict` — 스키마 `archmap-v0`의 architecture 문서.
  - CLI: `python -m tools.archmap build --repo-root . --repo Autoresearch --repo-url <url> --revision <sha> --out architecture.json`
- 스캔 규칙: `autoresearch/<subpackage>/**.py` — stage 매핑 `{youtube_collection, virtual_users, action_logs → 그대로, jobs → orchestration}`; `src/**.py` → stage `training`. `__init__.py`는 버전 상수나 public 심볼이 있을 때만 포함하고 모듈 id는 패키지 경로(예: `jobs`). 모듈 id는 `autoresearch.` 접두사 제거한 점 표기(`action_logs.schema`), src는 `src.` 유지(`src.features.build`).
- 계약: `autoresearch/jobs/__init__.py`의 `BATCH_CONTRACT_VERSION` 값을 이름으로, `autoresearch/jobs/*.py`(밑줄 제외)의 CLI 인자 합집합을 표면으로, `consumed_by=["Autoresearch-airflow"]`.

- [ ] **Step 10-1: 실패하는 테스트 작성** — `tests/test_archmap_build.py`

```python
import json
from pathlib import Path

from tools.archmap.build import STAGES, build_architecture


def _make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "autoresearch" / "action_logs").mkdir(parents=True)
    (root / "autoresearch" / "jobs").mkdir(parents=True)
    (root / "src" / "features").mkdir(parents=True)
    (root / "autoresearch" / "__init__.py").write_text("", encoding="utf-8")
    (root / "autoresearch" / "action_logs" / "__init__.py").write_text("", encoding="utf-8")
    (root / "autoresearch" / "action_logs" / "schema.py").write_text(
        'ACTION_LOG_SCHEMA_VERSION = "action_log_schema_v1"\n', encoding="utf-8")
    (root / "autoresearch" / "jobs" / "__init__.py").write_text(
        'BATCH_CONTRACT_VERSION = "batch-contract-v1"\n__all__ = ["BATCH_CONTRACT_VERSION"]\n',
        encoding="utf-8")
    (root / "autoresearch" / "jobs" / "action_log.py").write_text(
        'import argparse\n\ndef _p():\n    p = argparse.ArgumentParser()\n'
        '    p.add_argument("--mode")\n    p.add_argument("--max-users")\n    return p\n',
        encoding="utf-8")
    (root / "src" / "features" / "build.py").write_text(
        "def build_features(df):\n    return df\n", encoding="utf-8")
    return root


def test_build_architecture(tmp_path):
    arch = build_architecture(_make_repo(tmp_path), "Autoresearch", "abc1234",
                              "https://github.com/SKYAHO/Autoresearch")
    assert arch["schema_version"] == "archmap-v0"
    assert arch["repo"] == "Autoresearch" and arch["revision"] == "abc1234"
    assert arch["stages"] == STAGES
    ids = {m["id"]: m for m in arch["modules"]}
    assert ids["action_logs.schema"]["stage"] == "action_logs"
    assert ids["action_logs.schema"]["version_consts"]["ACTION_LOG_SCHEMA_VERSION"]["value"] \
        == "action_log_schema_v1"
    assert ids["jobs"]["stage"] == "orchestration"          # jobs/__init__.py — 상수 보유
    assert "action_logs" not in ids                          # 빈 __init__.py 제외
    assert ids["src.features.build"]["stage"] == "training"
    assert arch["contracts"] == [{
        "name": "batch-contract-v1", "module": "jobs",
        "cli_args": ["--mode", "--max-users"], "consumed_by": ["Autoresearch-airflow"]}]
    json.dumps(arch)  # 직렬화 가능해야 한다


def test_real_repo_smoke():
    repo_root = Path(__file__).resolve().parent.parent
    arch = build_architecture(repo_root, "Autoresearch", "HEAD", "")
    ids = {m["id"] for m in arch["modules"]}
    assert {"action_logs.schema", "virtual_users.schema", "youtube_collection.schema",
            "jobs.action_log"} <= ids
    consts = {m["id"]: m["version_consts"] for m in arch["modules"]}
    assert "ACTION_LOG_SCHEMA_VERSION" in consts["action_logs.schema"]
    contract = arch["contracts"][0]
    assert contract["name"] == "batch-contract-v1" and "--mode" in contract["cli_args"]
```

- [ ] **Step 10-2: 실패 확인** — `uv run --no-sync python -m pytest tests/test_archmap_build.py -v` → `ModuleNotFoundError`

- [ ] **Step 10-3: 구현** — `tools/archmap/build.py`

```python
"""소스 트리를 걸어 architecture.json 문서를 조립한다."""
from __future__ import annotations

import ast
from pathlib import Path

from tools.archmap.cli_contract import extract_cli_args
from tools.archmap.module_info import extract_module_info

SCHEMA_VERSION = "archmap-v0"
STAGES = ["youtube_collection", "virtual_users", "action_logs", "orchestration", "training"]
STAGE_BY_SUBPACKAGE = {
    "youtube_collection": "youtube_collection",
    "virtual_users": "virtual_users",
    "action_logs": "action_logs",
    "jobs": "orchestration",
}
CONSUMED_BY = ["Autoresearch-airflow"]


def _module_id(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if parts and parts[0] == "autoresearch":
        parts = parts[1:]
    return ".".join(parts)


def _stage_for(rel: Path) -> str | None:
    if rel.parts[0] == "autoresearch" and len(rel.parts) > 1:
        return STAGE_BY_SUBPACKAGE.get(rel.parts[1])
    if rel.parts[0] == "src":
        return "training"
    return None


def _iter_py_files(repo_root: Path):
    for base in ("autoresearch", "src"):
        root = repo_root / base
        if root.is_dir():
            yield from sorted(root.rglob("*.py"))


def _batch_contract(repo_root: Path) -> list[dict]:
    jobs_init = repo_root / "autoresearch" / "jobs" / "__init__.py"
    if not jobs_init.exists():
        return []
    name = None
    for node in ast.parse(jobs_init.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == "BATCH_CONTRACT_VERSION" \
                and isinstance(node.value, ast.Constant):
            name = node.value.value
    if name is None:
        return []
    cli_args: list[str] = []
    for path in sorted((repo_root / "autoresearch" / "jobs").glob("*.py")):
        if path.name.startswith("_"):
            continue
        for flag in extract_cli_args(path.read_text(encoding="utf-8")):
            if flag not in cli_args:
                cli_args.append(flag)
    return [{"name": name, "module": "jobs", "cli_args": cli_args, "consumed_by": CONSUMED_BY}]


def build_architecture(repo_root: Path, repo: str, revision: str, repo_url: str) -> dict:
    repo_root = Path(repo_root)
    modules = []
    for path in _iter_py_files(repo_root):
        rel = path.relative_to(repo_root)
        stage = _stage_for(rel)
        if stage is None:
            continue
        info = extract_module_info(path.read_text(encoding="utf-8"),
                                   _module_id(rel), stage, str(rel).replace("\\", "/"))
        if rel.name == "__init__.py" and not info["public_symbols"] \
                and not info["version_consts"]:
            continue
        modules.append(info)
    return {"schema_version": SCHEMA_VERSION, "repo": repo, "repo_url": repo_url,
            "revision": revision, "contract_version": "batch-contract-v1",
            "stages": STAGES, "modules": modules,
            "contracts": _batch_contract(repo_root)}
```

`tools/archmap/__main__.py` (build 서브커맨드만 우선 — delta·comment는 Task 11·12에서 추가):

```python
"""archmap 추출기 CLI: build / delta / comment."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.archmap.build import build_architecture


def _write(doc: dict, out: str) -> None:
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    if out == "-":
        sys.stdout.write(text)
    else:
        Path(out).write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tools.archmap")
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="architecture.json 생성")
    p_build.add_argument("--repo-root", default=".")
    p_build.add_argument("--repo", required=True)
    p_build.add_argument("--repo-url", default="")
    p_build.add_argument("--revision", required=True)
    p_build.add_argument("--out", default="-")

    args = parser.parse_args(argv)
    if args.command == "build":
        _write(build_architecture(Path(args.repo_root), args.repo,
                                  args.revision, args.repo_url), args.out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 10-4: 통과 확인 + 실 레포 실행**

```bash
uv run --no-sync python -m pytest tests/test_archmap_build.py -v
python -m tools.archmap build --repo Autoresearch --revision $(git rev-parse HEAD) \
  --repo-url https://github.com/SKYAHO/Autoresearch --out /tmp/arch.json && head -30 /tmp/arch.json
```

Expected: 2 PASS + JSON에 실제 모듈들이 보인다.

- [ ] **Step 10-5: 커밋**

```bash
uv run --no-sync ruff check autoresearch tests tools
git add tools/archmap/build.py tools/archmap/__main__.py tests/test_archmap_build.py
git commit -m "feat: architecture.json 빌더와 추출기 CLI 추가"
```

### Task 11: pr-delta 빌더 (`tools/archmap/delta.py`)

**Files:**
- Create: `tools/archmap/delta.py`
- Modify: `tools/archmap/__main__.py` (delta 서브커맨드 추가)
- Test: `tests/test_archmap_delta.py`

**Interfaces:**
- Consumes: base/head architecture dict (Task 10 산출).
- Produces:
  - `parse_numstat(text: str) -> dict[str, int]` — `git diff --numstat` 출력 → {경로: 추가줄수}.
  - `build_delta(base: dict, head: dict, changed: dict[str, int], pr: int, issue: dict | None) -> dict` — 스키마 `archmap-v0`의 pr-delta 문서.
  - CLI: `python -m tools.archmap delta --base base.json --head head.json --numstat diff.txt --pr 120 [--issue-json issue.json] --out pr-delta.json` (base/head SHA는 두 JSON의 `revision` 필드에서 취한다)
- 판정 규칙(스펙 §6·§8):
  - changed_modules: 경로가 changed에 있는 head 모듈(+base에만 있는 삭제 모듈). symbols_changed는 이름별 added/removed/sig 비교.
  - 시그니처 하위호환: 기존 파라미터 열이 그대로 보존되고 새 파라미터가 전부 기본값(`=`) 또는 `*` 계열이면 비파괴, 아니면 파괴.
  - version_changes: 값이 바뀐 버전 상수(버전 문자열 bump 자체는 비파괴). 상수 제거는 파괴.
  - unchanged_contracts: **변경된 모듈 안에서** 값이 유지된 버전 상수.
  - schema_changes: BaseModel 필드 added(비파괴)/removed(파괴).
  - cross_repo: 계약 cli_args의 추가(`optional-arg-added`, 비파괴)/제거(`arg-removed`, 파괴), 계약 이름 변경(파괴).
  - tests: changed 중 `tests/` 경로와 추가 줄수 합.
  - sidecar_stale: Phase 0에서는 항상 `[]`.

- [ ] **Step 11-1: 실패하는 테스트 작성** — `tests/test_archmap_delta.py`

```python
import copy

from tools.archmap.delta import build_delta, parse_numstat

BASE = {
    "schema_version": "archmap-v0", "repo": "Autoresearch", "repo_url": "",
    "revision": "base000", "contract_version": "batch-contract-v1",
    "stages": ["action_logs"],
    "modules": [{
        "id": "action_logs.schema", "stage": "action_logs",
        "path": "autoresearch/action_logs/schema.py",
        "role": None, "owns": [], "not_owns": [],
        "public_symbols": [
            {"name": "run_daily", "kind": "function", "sig": "(request, generator)", "line": 10},
            {"name": "EventLog", "kind": "class", "sig": None, "line": 30},
        ],
        "version_consts": {
            "ACTION_LOG_SCHEMA_VERSION": {"value": "action_log_schema_v1", "line": 16},
            "PROMPT_VERSION": {"value": "action_log_ctr_v3", "line": 17},
        },
        "schema_fields": {"EventLog": ["event_id", "clicked"]},
        "imports": [],
    }],
    "contracts": [{"name": "batch-contract-v1", "module": "jobs",
                   "cli_args": ["--mode"], "consumed_by": ["Autoresearch-airflow"]}],
}


def _head():
    head = copy.deepcopy(BASE)
    head["revision"] = "head000"
    m = head["modules"][0]
    m["public_symbols"][0]["sig"] = "(request, generator, max_users=None)"
    m["version_consts"]["PROMPT_VERSION"]["value"] = "action_log_ctr_v4"
    m["schema_fields"]["EventLog"] = ["event_id", "clicked", "position"]
    head["contracts"][0]["cli_args"] = ["--mode", "--max-users"]
    return head


CHANGED = {"autoresearch/action_logs/schema.py": 12, "tests/test_action_logs_daily.py": 52}


def _delta(head=None):
    return build_delta(BASE, head or _head(), CHANGED, pr=120,
                       issue={"number": 118, "title": "t", "body_excerpt": "b"})


def test_parse_numstat():
    text = "12\t3\tautoresearch/action_logs/schema.py\n52\t0\ttests/test_action_logs_daily.py\n-\t-\tdata/blob.bin\n"
    assert parse_numstat(text) == {"autoresearch/action_logs/schema.py": 12,
                                   "tests/test_action_logs_daily.py": 52,
                                   "data/blob.bin": 0}


def test_changed_modules_and_compatible_signature():
    d = _delta()
    (m,) = d["changed_modules"]
    assert m["id"] == "action_logs.schema" and m["public_surface_changed"]
    assert {"name": "run_daily", "change": "signature", "line": 10} in m["symbols_changed"]


def test_version_change_nonbreaking_and_unchanged_contract():
    d = _delta()
    (v,) = d["version_changes"]
    assert v["const"] == "PROMPT_VERSION" and v["from"].endswith("v3") \
        and v["to"].endswith("v4") and v["breaking"] is False
    (u,) = d["unchanged_contracts"]
    assert u["const"] == "ACTION_LOG_SCHEMA_VERSION" and u["value"] == "action_log_schema_v1"


def test_schema_field_added_nonbreaking_removed_breaking():
    d = _delta()
    (s,) = d["schema_changes"]
    assert s == {"model": "EventLog", "module": "action_logs.schema",
                 "field": "position", "change": "added", "breaking": False}
    head = _head()
    head["modules"][0]["schema_fields"]["EventLog"] = ["event_id"]
    removed = [s for s in _delta(head)["schema_changes"] if s["change"] == "removed"]
    assert removed and all(s["breaking"] for s in removed)


def test_breaking_signature_when_required_param_added():
    head = _head()
    head["modules"][0]["public_symbols"][0]["sig"] = "(request, generator, must_have)"
    d = _delta(head)
    assert any(v["breaking"] for v in d["version_changes"]) is False  # 버전은 그대로 비파괴
    (m,) = d["changed_modules"]
    assert m["public_surface_changed"]
    # 파괴적 시그니처는 cross_repo가 아니라 배지 근거인 breaking_signatures로 남는다
    assert d["breaking_signatures"] == [{"module": "action_logs.schema", "name": "run_daily"}]


def test_cross_repo_arg_added_and_removed():
    d = _delta()
    (x,) = d["cross_repo"]
    assert x["contract"] == "batch-contract-v1" and x["impact"] == "optional-arg-added" \
        and x["breaking"] is False
    head = _head()
    head["contracts"][0]["cli_args"] = []
    removed = [x for x in _delta(head)["cross_repo"] if x["impact"] == "arg-removed"]
    assert removed and removed[0]["breaking"] is True


def test_tests_section():
    d = _delta()
    assert d["tests"] == {"files": ["tests/test_action_logs_daily.py"], "lines_added": 52}
    assert d["sidecar_stale"] == []
```

주의: `breaking_signatures`는 pr-delta 스키마의 `required`에 없는 추가 필드다. JSON Schema는 미정의 프로퍼티를 허용하므로(additionalProperties 미지정) 계약 위반이 아니다. 서버 Phase 0 렌더는 이 필드를 아직 쓰지 않는다.

- [ ] **Step 11-2: 실패 확인** — `uv run --no-sync python -m pytest tests/test_archmap_delta.py -v` → `ModuleNotFoundError`

- [ ] **Step 11-3: 구현** — `tools/archmap/delta.py`

```python
"""base/head architecture.json 비교 + git 사실로 pr-delta.json을 만든다."""
from __future__ import annotations

SCHEMA_VERSION = "archmap-v0"


def parse_numstat(text: str) -> dict[str, int]:
    changed: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, _, path = parts
        changed[path] = int(added) if added.isdigit() else 0
    return changed


def _sig_params(sig: str | None) -> list[str]:
    if not sig:
        return []
    inner = sig.strip()[1:-1].strip()
    return [p.strip() for p in inner.split(",")] if inner else []


def _sig_backward_compatible(old: str | None, new: str | None) -> bool:
    """기존 파라미터 열 보존 + 추가분은 전부 기본값/가변 인자면 하위호환.

    쉼표 단순 분할이라 기본값 안에 쉼표가 있으면(예: default=(1, 2)) 보수적으로
    파괴로 판정될 수 있다 — Phase 0 한계로 허용(허위 초록보다 허위 경고가 낫다).
    """
    old_p, new_p = _sig_params(old), _sig_params(new)
    if new_p[:len(old_p)] != old_p:
        return False
    return all("=" in p or p.startswith("*") for p in new_p[len(old_p):])


def _symbols_changed(base_m: dict, head_m: dict) -> tuple[list[dict], list[dict]]:
    base_syms = {s["name"]: s for s in base_m["public_symbols"]}
    head_syms = {s["name"]: s for s in head_m["public_symbols"]}
    changes, breaking = [], []
    for name, s in head_syms.items():
        if name not in base_syms:
            changes.append({"name": name, "change": "added", "line": s["line"]})
        elif s.get("sig") != base_syms[name].get("sig"):
            changes.append({"name": name, "change": "signature", "line": s["line"]})
            if not _sig_backward_compatible(base_syms[name].get("sig"), s.get("sig")):
                breaking.append({"module": head_m["id"], "name": name})
    for name, s in base_syms.items():
        if name not in head_syms:
            changes.append({"name": name, "change": "removed", "line": None})
            breaking.append({"module": base_m["id"], "name": name})
    return changes, breaking


def build_delta(base: dict, head: dict, changed: dict[str, int],
                pr: int, issue: dict | None) -> dict:
    base_mods = {m["id"]: m for m in base["modules"]}
    head_mods = {m["id"]: m for m in head["modules"]}

    changed_modules, version_changes, unchanged_contracts = [], [], []
    schema_changes, breaking_signatures = [], []

    for mid, hm in head_mods.items():
        bm = base_mods.get(mid)
        if hm["path"] not in changed:
            continue
        if bm is None:
            changed_modules.append({"id": mid, "path": hm["path"], "stage": hm["stage"],
                                    "symbols_changed": [{"name": s["name"], "change": "added",
                                                          "line": s["line"]}
                                                         for s in hm["public_symbols"]],
                                    "public_surface_changed": bool(hm["public_symbols"])})
            continue
        symbols, breaking = _symbols_changed(bm, hm)
        breaking_signatures.extend(breaking)
        changed_modules.append({"id": mid, "path": hm["path"], "stage": hm["stage"],
                                "symbols_changed": symbols,
                                "public_surface_changed": bool(symbols)})
        for const, info in hm["version_consts"].items():
            old = bm["version_consts"].get(const)
            if old is None:
                version_changes.append({"const": const, "module": mid, "from": None,
                                        "to": info["value"], "line": info["line"],
                                        "breaking": False})
            elif old["value"] != info["value"]:
                version_changes.append({"const": const, "module": mid,
                                        "from": old["value"], "to": info["value"],
                                        "line": info["line"], "breaking": False})
            else:
                unchanged_contracts.append({"const": const, "module": mid,
                                            "value": info["value"], "line": info["line"]})
        for const, old in bm["version_consts"].items():
            if const not in hm["version_consts"]:
                version_changes.append({"const": const, "module": mid, "from": old["value"],
                                        "to": None, "line": None, "breaking": True})
        for model in set(bm["schema_fields"]) | set(hm["schema_fields"]):
            old_f = set(bm["schema_fields"].get(model, []))
            new_f = set(hm["schema_fields"].get(model, []))
            for f in sorted(new_f - old_f):
                schema_changes.append({"model": model, "module": mid, "field": f,
                                       "change": "added", "breaking": False})
            for f in sorted(old_f - new_f):
                schema_changes.append({"model": model, "module": mid, "field": f,
                                       "change": "removed", "breaking": True})

    for mid, bm in base_mods.items():
        if mid not in head_mods and bm["path"] in changed:
            changed_modules.append({"id": mid, "path": bm["path"], "stage": bm["stage"],
                                    "symbols_changed": [{"name": s["name"], "change": "removed",
                                                          "line": None}
                                                         for s in bm["public_symbols"]],
                                    "public_surface_changed": bool(bm["public_symbols"])})
            breaking_signatures.extend({"module": mid, "name": s["name"]}
                                       for s in bm["public_symbols"])

    cross_repo = []
    base_contracts = {c["name"]: c for c in base["contracts"]}
    for c in head["contracts"]:
        old = base_contracts.get(c["name"])
        if old is None:
            cross_repo.append({"contract": c["name"], "impact": "contract-renamed",
                               "breaking": True,
                               "details": "base에 없는 계약 이름 — 이름 변경 여부를 확인하십시오"})
            continue
        added = [a for a in c["cli_args"] if a not in old["cli_args"]]
        removed = [a for a in old["cli_args"] if a not in c["cli_args"]]
        if added:
            cross_repo.append({"contract": c["name"], "impact": "optional-arg-added",
                               "breaking": False, "details": ", ".join(added) + " 인자 추가"})
        if removed:
            cross_repo.append({"contract": c["name"], "impact": "arg-removed",
                               "breaking": True, "details": ", ".join(removed) + " 인자 제거"})

    test_files = sorted(p for p in changed if p.startswith("tests/"))
    return {"schema_version": SCHEMA_VERSION, "repo": head["repo"], "pr": pr,
            "base_sha": base["revision"], "head_sha": head["revision"], "issue": issue,
            "changed_modules": changed_modules, "version_changes": version_changes,
            "unchanged_contracts": unchanged_contracts, "schema_changes": schema_changes,
            "cross_repo": cross_repo,
            "tests": {"files": test_files,
                      "lines_added": sum(changed[p] for p in test_files)},
            "sidecar_stale": [], "breaking_signatures": breaking_signatures}
```

- [ ] **Step 11-4: `__main__.py`에 delta 서브커맨드 추가**

`tools/archmap/__main__.py`의 import에 `from tools.archmap.delta import build_delta, parse_numstat` 추가, `main()`의 서브파서 정의부에 아래를 추가:

```python
    p_delta = sub.add_parser("delta", help="pr-delta.json 생성")
    p_delta.add_argument("--base", required=True, help="base architecture.json 경로")
    p_delta.add_argument("--head", required=True, help="head architecture.json 경로")
    p_delta.add_argument("--numstat", required=True, help="git diff --numstat 출력 파일")
    p_delta.add_argument("--pr", type=int, required=True)
    p_delta.add_argument("--issue-json", default=None, help="이슈 정보 JSON 파일(선택)")
    p_delta.add_argument("--out", default="-")
```

분기 처리(`if args.command == "build": ...` 아래):

```python
    elif args.command == "delta":
        base = json.loads(Path(args.base).read_text(encoding="utf-8"))
        head = json.loads(Path(args.head).read_text(encoding="utf-8"))
        changed = parse_numstat(Path(args.numstat).read_text(encoding="utf-8"))
        issue = None
        if args.issue_json:
            issue = json.loads(Path(args.issue_json).read_text(encoding="utf-8"))
        _write(build_delta(base, head, changed, args.pr, issue), args.out)
```

- [ ] **Step 11-5: 통과 확인** — `uv run --no-sync python -m pytest tests/test_archmap_delta.py -v` → 7 PASS

- [ ] **Step 11-6: 커밋**

```bash
uv run --no-sync ruff check autoresearch tests tools
git add tools/archmap/delta.py tools/archmap/__main__.py tests/test_archmap_delta.py
git commit -m "feat: pr-delta 빌더와 breaking 판정 규칙 추가"
```

### Task 12: PR 코멘트 생성기 (`tools/archmap/comment.py`)

**Files:**
- Create: `tools/archmap/comment.py`
- Modify: `tools/archmap/__main__.py` (comment 서브커맨드 추가)
- Test: `tests/test_archmap_comment.py`

**Interfaces:**
- Consumes: pr-delta dict (Task 11 산출).
- Produces: `render_comment(delta: dict, report_url: str | None) -> str` — 첫 줄이 upsert 마커 `<!-- archmap-report -->`인 마크다운. 서버가 죽어도 이 코멘트만으로 사실이 전달되어야 한다(스펙: 결정론 사실은 CI 코멘트로 최소 보장).
- CLI: `python -m tools.archmap comment --delta pr-delta.json [--report-url URL] --out comment.md`

- [ ] **Step 12-1: 실패하는 테스트 작성** — `tests/test_archmap_comment.py`

```python
from tools.archmap.comment import MARKER, render_comment

DELTA = {
    "schema_version": "archmap-v0", "repo": "Autoresearch", "pr": 120,
    "base_sha": "aaaaaaa", "head_sha": "3be5fae",
    "issue": {"number": 118, "title": "후보 목록을 프롬프트에 명시", "body_excerpt": "b"},
    "changed_modules": [
        {"id": "action_logs.daily", "path": "autoresearch/action_logs/daily.py",
         "stage": "action_logs",
         "symbols_changed": [{"name": "run_daily_action_log", "change": "signature", "line": 722}],
         "public_surface_changed": True}],
    "version_changes": [
        {"const": "PROMPT_VERSION", "module": "action_logs.schema",
         "from": "action_log_ctr_v3", "to": "action_log_ctr_v4", "line": 17, "breaking": False}],
    "unchanged_contracts": [
        {"const": "ACTION_LOG_SCHEMA_VERSION", "module": "action_logs.schema",
         "value": "action_log_schema_v1", "line": 16}],
    "schema_changes": [],
    "cross_repo": [{"contract": "batch-contract-v1", "impact": "optional-arg-added",
                    "breaking": False, "details": "--max-users 인자 추가"}],
    "tests": {"files": ["tests/test_action_logs_daily.py"], "lines_added": 52},
    "sidecar_stale": [], "breaking_signatures": [],
}


def test_comment_starts_with_marker():
    assert render_comment(DELTA, "http://srv/reports/Autoresearch/120").startswith(MARKER)


def test_comment_contains_facts():
    md = render_comment(DELTA, "http://srv/reports/Autoresearch/120")
    assert "action_logs" in md
    assert "PROMPT_VERSION" in md and "action_log_ctr_v4" in md
    assert "ACTION_LOG_SCHEMA_VERSION" in md and "✅" in md
    assert "batch-contract-v1" in md
    assert "+52줄" in md
    assert "http://srv/reports/Autoresearch/120" in md


def test_comment_without_server_url_notes_it():
    md = render_comment(DELTA, None)
    assert "서버 미연결" in md and "http" not in md


def test_breaking_rows_are_flagged():
    import copy
    d = copy.deepcopy(DELTA)
    d["cross_repo"][0]["breaking"] = True
    assert "⚠️" in render_comment(d, None)
```

- [ ] **Step 12-2: 실패 확인** — `uv run --no-sync python -m pytest tests/test_archmap_comment.py -v` → `ModuleNotFoundError`

- [ ] **Step 12-3: 구현** — `tools/archmap/comment.py`

```python
"""pr-delta 사실만으로 PR 요약 코멘트(마크다운)를 만든다 — 서버 없이도 성립."""
from __future__ import annotations

MARKER = "<!-- archmap-report -->"


def render_comment(delta: dict, report_url: str | None) -> str:
    lines = [MARKER, "## 🗺️ PR 이해 리포트 — 결정론 사실 요약", ""]

    stages = sorted({m["stage"] for m in delta["changed_modules"]})
    if stages:
        lines.append(f'**흐름 위치**: `{" · ".join(stages)}` 스테이지를 변경합니다.')
    mods = ", ".join(f'`{m["id"]}`' for m in delta["changed_modules"])
    if mods:
        lines.append(f"**변경 모듈**: {mods}")
    lines.append("")

    rows = []
    for u in delta["unchanged_contracts"]:
        rows.append(f'| ✅ 검증됨 | `{u["const"]}` = `{u["value"]}` 불변 |')
    for v in delta["version_changes"]:
        mark = "⚠️ 파괴적" if v["breaking"] else "🔵 비파괴"
        rows.append(f'| {mark} | `{v["const"]}`: `{v["from"]}` → `{v["to"]}` |')
    for s in delta["schema_changes"]:
        mark = "⚠️ 파괴적" if s["breaking"] else "🔵 비파괴"
        rows.append(f'| {mark} | `{s["model"]}.{s["field"]}` {s["change"]} |')
    for x in delta["cross_repo"]:
        mark = "⚠️ 파괴적" if x["breaking"] else "🔵 비파괴"
        rows.append(f'| {mark} | `{x["contract"]}` {x["impact"]} — {x.get("details", "")} |')
    if rows:
        lines += ["| 판정 | 계약 · 영향 |", "| --- | --- |", *rows, ""]

    t = delta["tests"]
    lines.append(f'**테스트**: {len(t["files"])}개 파일 변경, +{t["lines_added"]}줄')
    lines.append("")
    if report_url:
        lines.append(f"[전체 이해 리포트 보기]({report_url})")
    else:
        lines.append("_아카이브 서버 미연결 — 위 결정론 사실 요약만 제공합니다._")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 12-4: `__main__.py`에 comment 서브커맨드 추가**

import에 `from tools.archmap.comment import render_comment` 추가, 서브파서 정의부에:

```python
    p_comment = sub.add_parser("comment", help="PR 코멘트 마크다운 생성")
    p_comment.add_argument("--delta", required=True)
    p_comment.add_argument("--report-url", default=None)
    p_comment.add_argument("--out", default="-")
```

분기 처리에:

```python
    elif args.command == "comment":
        delta = json.loads(Path(args.delta).read_text(encoding="utf-8"))
        text = render_comment(delta, args.report_url)
        if args.out == "-":
            sys.stdout.write(text)
        else:
            Path(args.out).write_text(text, encoding="utf-8")
```

- [ ] **Step 12-5: 통과 확인** — `uv run --no-sync python -m pytest tests/test_archmap_comment.py -v` → 4 PASS

- [ ] **Step 12-6: 커밋**

```bash
uv run --no-sync ruff check autoresearch tests tools
git add tools/archmap/comment.py tools/archmap/__main__.py tests/test_archmap_comment.py
git commit -m "feat: 결정론 사실 기반 PR 코멘트 생성기 추가"
```

### Task 13: CI 워크플로우 (`.github/workflows/archmap.yml`)

**Files:**
- Create: `.github/workflows/archmap.yml`

**Interfaces:**
- Consumes: `python -m tools.archmap build|delta|comment` (Task 10~12), 서버 API 계약(Task 5), 코멘트 마커(Task 12).
- Produces: PR마다 upsert되는 archmap 코멘트 + (시크릿 설정 시) 서버로 pr-report/manifest POST.
- 시크릿/변수(없으면 POST 단계는 건너뛰고 코멘트만): `secrets.ARCHMAP_TOKEN`, `vars.ARCHMAP_SERVER_URL`.
- 추출기는 stdlib-only이므로 uv sync 없이 시스템 python으로 실행한다.

- [ ] **Step 13-1: 워크플로우 작성** — `.github/workflows/archmap.yml`

```yaml
name: Archmap

on:
  pull_request:
    types: [opened, synchronize, reopened]
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: write

jobs:
  pr-report:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: head/base architecture.json 추출
        run: |
          python -m tools.archmap build --repo-root . \
            --repo Autoresearch --repo-url "https://github.com/${{ github.repository }}" \
            --revision "${{ github.event.pull_request.head.sha }}" --out /tmp/head.json
          git worktree add /tmp/base-tree "${{ github.event.pull_request.base.sha }}"
          python -m tools.archmap build --repo-root /tmp/base-tree \
            --repo Autoresearch --repo-url "https://github.com/${{ github.repository }}" \
            --revision "${{ github.event.pull_request.base.sha }}" --out /tmp/base.json

      - name: 연결 이슈 조회 (PR 본문의 Closes #N)
        env:
          GH_TOKEN: ${{ github.token }}
          PR_BODY: ${{ github.event.pull_request.body }}
        run: |
          num=$(printf '%s' "$PR_BODY" | grep -oiE 'close[sd]? #[0-9]+' | grep -oE '[0-9]+' | head -1 || true)
          if [ -n "$num" ]; then
            gh api "repos/${{ github.repository }}/issues/$num" \
              --jq '{number: .number, title: .title, body_excerpt: (.body // "" | .[0:300])}' \
              > /tmp/issue.json || rm -f /tmp/issue.json
          fi

      - name: pr-delta.json 생성
        run: |
          git diff --numstat "${{ github.event.pull_request.base.sha }}" \
            "${{ github.event.pull_request.head.sha }}" > /tmp/numstat.txt
          issue_flag=""
          [ -f /tmp/issue.json ] && issue_flag="--issue-json /tmp/issue.json"
          python -m tools.archmap delta --base /tmp/base.json --head /tmp/head.json \
            --numstat /tmp/numstat.txt --pr "${{ github.event.pull_request.number }}" \
            $issue_flag --out /tmp/pr-delta.json

      - name: 서버로 POST (시크릿 있을 때만)
        if: vars.ARCHMAP_SERVER_URL != ''
        continue-on-error: true
        run: |
          python - <<'EOF'
          import json, os, urllib.request
          body = {"architecture": json.load(open("/tmp/head.json", encoding="utf-8")),
                  "pr_delta": json.load(open("/tmp/pr-delta.json", encoding="utf-8"))}
          req = urllib.request.Request(
              os.environ["SERVER"] + "/api/pr-report",
              data=json.dumps(body).encode(),
              headers={"X-Archmap-Token": os.environ["TOKEN"],
                       "Content-Type": "application/json"})
          url = json.load(urllib.request.urlopen(req, timeout=30))["report_url"]
          open("/tmp/report-url.txt", "w").write(url)
          EOF
        env:
          SERVER: ${{ vars.ARCHMAP_SERVER_URL }}
          TOKEN: ${{ secrets.ARCHMAP_TOKEN }}

      - name: PR 코멘트 upsert
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          url_flag=""
          [ -f /tmp/report-url.txt ] && url_flag="--report-url $(cat /tmp/report-url.txt)"
          python -m tools.archmap comment --delta /tmp/pr-delta.json $url_flag --out /tmp/comment.md
          pr=${{ github.event.pull_request.number }}
          existing=$(gh api "repos/${{ github.repository }}/issues/$pr/comments" --paginate \
            --jq '[.[] | select(.body | startswith("<!-- archmap-report -->"))][0].id // empty')
          if [ -n "$existing" ]; then
            gh api -X PATCH "repos/${{ github.repository }}/issues/comments/$existing" \
              -F body=@/tmp/comment.md
          else
            gh api "repos/${{ github.repository }}/issues/$pr/comments" -F body=@/tmp/comment.md
          fi

  manifest:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: architecture.json 추출 후 서버로 POST
        if: vars.ARCHMAP_SERVER_URL != ''
        continue-on-error: true
        run: |
          python -m tools.archmap build --repo-root . \
            --repo Autoresearch --repo-url "https://github.com/${{ github.repository }}" \
            --revision "${{ github.sha }}" --out /tmp/arch.json
          python - <<'EOF'
          import json, os, urllib.request
          req = urllib.request.Request(
              os.environ["SERVER"] + "/api/manifest",
              data=open("/tmp/arch.json", "rb").read(),
              headers={"X-Archmap-Token": os.environ["TOKEN"],
                       "Content-Type": "application/json"})
          urllib.request.urlopen(req, timeout=30)
          EOF
        env:
          SERVER: ${{ vars.ARCHMAP_SERVER_URL }}
          TOKEN: ${{ secrets.ARCHMAP_TOKEN }}
```

- [ ] **Step 13-2: 로컬 시뮬레이션으로 검증** (actionlint가 없으므로 각 스텝의 셸 명령을 직접 실행)

```bash
cd /mnt/c/Autoresarch
python -m tools.archmap build --repo-root . --repo Autoresearch \
  --repo-url https://github.com/SKYAHO/Autoresearch \
  --revision $(git rev-parse HEAD) --out /tmp/head.json
git worktree add /tmp/base-tree origin/main
python -m tools.archmap build --repo-root /tmp/base-tree --repo Autoresearch \
  --repo-url https://github.com/SKYAHO/Autoresearch \
  --revision $(git rev-parse origin/main) --out /tmp/base.json
git diff --numstat origin/main HEAD > /tmp/numstat.txt
python -m tools.archmap delta --base /tmp/base.json --head /tmp/head.json \
  --numstat /tmp/numstat.txt --pr 0 --out /tmp/pr-delta.json
python -m tools.archmap comment --delta /tmp/pr-delta.json
git worktree remove /tmp/base-tree
```

Expected: 이 브랜치의 변경(tools/archmap 신설 등)이 담긴 pr-delta와 코멘트 마크다운이 출력된다.

- [ ] **Step 13-3: 커밋**

```bash
git add .github/workflows/archmap.yml
git commit -m "feat: archmap 추출·리포트 CI 워크플로우 추가"
```

### Task 14: End-to-End 검증 + PR 생성

**Files:**
- 없음 (검증·푸시만)

- [ ] **Step 14-1: 서버 기동 (PR_report 쪽)**

```bash
cd /mnt/c/PR_report
ARCHMAP_TOKEN=dev uv run uvicorn archmap.api:app --port 8000 &
```

- [ ] **Step 14-2: 실제 추출물을 서버에 주입**

```bash
cd /mnt/c/Autoresarch
python - <<'EOF'
import json, urllib.request
body = {"architecture": json.load(open("/tmp/head.json", encoding="utf-8")),
        "pr_delta": json.load(open("/tmp/pr-delta.json", encoding="utf-8"))}
req = urllib.request.Request("http://localhost:8000/api/pr-report",
    data=json.dumps(body).encode(),
    headers={"X-Archmap-Token": "dev", "Content-Type": "application/json"})
print(urllib.request.urlopen(req).read().decode())
EOF
curl -s http://localhost:8000/reports/Autoresearch/0 | head -5
```

Expected: `report_url` 반환 + HTML 첫 줄 `<!doctype html>`. **이 단계가 계약의 실증이다** — 실제 추출기 출력이 서버 스키마 검증을 통과해야 한다. 400이 나오면 스키마·추출기 불일치이므로 여기서 고친다.

- [ ] **Step 14-3: 전체 테스트 + 푸시 + PR**

```bash
cd /mnt/c/Autoresarch
uv run --no-sync python -m pytest -v      # 기존 스위트 포함 전체 통과 확인
uv run --no-sync ruff check autoresearch tests tools
git push -u origin feat/<N>-archmap-extractor
gh pr create --repo SKYAHO/Autoresearch \
  --title "feat: archmap 결정론 추출기와 CI 리포트 추가" \
  --body "Closes #<N>

## 변경 내용
- tools/archmap/: AST 추출기 (architecture.json / pr-delta.json, stdlib-only)
- .github/workflows/archmap.yml: PR 추출→서버 POST→코멘트 upsert, main 머지 시 manifest POST
- 서버 미연결 시에도 결정론 사실 요약 코멘트는 동작

## 검증
- uv run python -m pytest (전체 통과)
- 로컬 E2E: 추출→POST→렌더 확인 (docs/plans Phase 0 Task 14)"
```

PR이 열리면 archmap.yml이 스스로 돌면서 **이 PR 자체에 첫 이해 리포트 코멘트**를 단다 — 도구가 자기 자신을 리포트하는 것이 Phase 0의 수용 확인이다.

- [ ] **Step 14-4: 서버 레포 마무리 푸시**

```bash
cd /mnt/c/PR_report
git push origin main
```

---

## 완료 기준 (스펙 §14 대응)

- [ ] 서버·추출기 전체 테스트 통과, 실제 추출물이 서버 스키마 검증을 통과 (Task 14-2).
- [ ] verified 배지는 `archmap/verify.py` 한 곳에서만 생성된다 (허위 초록 0의 구조적 보장).
- [ ] 서버 미연결 상태에서도 PR 코멘트에 결정론 사실 요약이 남는다.
- [ ] Streamlit 두 탭이 실데이터(매니페스트·리포트)로 렌더된다.
- [ ] sidecar 게이트(Phase 1)·GLM 서술(Phase 2)은 이 계획의 범위 밖이다.

## 남은 결정 (구현 중 확정)

- 서버 공개 호스팅(현재 로컬) — 호스팅 확정 전까지 CI의 POST 단계는 `vars.ARCHMAP_SERVER_URL` 부재로 자동 건너뜀.
- `Autoresearch-airflow`·`-infra` 추출기는 Phase 3·4.
