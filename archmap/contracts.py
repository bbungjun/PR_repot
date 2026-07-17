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
