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
