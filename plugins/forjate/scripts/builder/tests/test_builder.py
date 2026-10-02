"""Tests for the use-case builder tooling. Run: poetry run pytest plugins/forjate/scripts/builder/tests"""

import copy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve().parent
BUILDER = HERE.parent
REPO = BUILDER.parents[3]
FIXTURE = HERE / "fixtures" / "db-migration-a-to-b"
PACKS = REPO / "context-packs" / "examples"

sys.path.insert(0, str(BUILDER))
from validate import validate_usecase  # noqa: E402
from packs import load_pack, resolve  # noqa: E402


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=REPO)


def test_example_packs_lint_clean():
    for pack in ("regulated-corp", "solo-dev"):
        _, _, errors = load_pack(PACKS / pack)
        assert errors == []


def test_fixture_usecase_is_valid():
    errors, warnings = validate_usecase(FIXTURE)
    assert errors == []
    # The plan runs eight experts but the fixture only ships one record.
    assert any("decisions/business.yaml is missing" in w for w in warnings)


def test_resolve_filters_by_role_and_orders_by_precedence():
    packs = [("regulated-corp", PACKS / "regulated-corp"), ("solo-dev", PACKS / "solo-dev")]
    ctx = resolve("security", packs)
    refs = [e["ref"] for e in ctx["entries"]]
    assert "pack:regulated-corp#AI-1" not in refs          # ai-engineering only
    assert refs[0].startswith("pack:solo-dev#")            # precedence 70 first
    assert ctx["overrides"][0]["rule"] == "pack:regulated-corp#SEC-1"
    assert ctx["overrides"][0]["overridden_by"] == "pack:solo-dev#SEC-1"


def test_resolve_unknown_role_fails():
    from common import BuilderError
    with pytest.raises(BuilderError):
        resolve("wizard", [])


@pytest.fixture
def usecase(tmp_path: Path) -> Path:
    dst = tmp_path / "db-migration-a-to-b"
    shutil.copytree(FIXTURE, dst)
    return dst


def _edit_decision(uc: Path, mutate) -> None:
    p = uc / ".builder" / "decisions" / "data-store.yaml"
    d = yaml.safe_load(p.read_text())
    mutate(d)
    p.write_text(yaml.safe_dump(d, sort_keys=False))


def test_denied_component_is_rejected(usecase: Path):
    _edit_decision(usecase, lambda d: d["spec"]["stages"]["crawl"]["choice"].append("apps/databases/mongodb"))
    errors, _ = validate_usecase(usecase)
    assert any("denied component" in e and "DATA-1" in e for e in errors)


def test_unknown_component_is_rejected(usecase: Path):
    _edit_decision(usecase, lambda d: d["spec"]["stages"]["crawl"]["choice"].append("apps/databases/oracle"))
    errors, _ = validate_usecase(usecase)
    assert any("not in catalog" in e for e in errors)


def test_residency_violation_is_rejected(usecase: Path):
    _edit_decision(usecase, lambda d: d["spec"]["stages"]["walk"]["settings"].update(data_residency="us"))
    errors, _ = validate_usecase(usecase)
    assert any("data_residency" in e and "RES-1" in e for e in errors)


def test_unknown_rule_ref_is_rejected(usecase: Path):
    _edit_decision(usecase, lambda d: d["spec"]["stages"]["crawl"]["constrained_by"].append("pack:regulated-corp#NOPE-9"))
    errors, _ = validate_usecase(usecase)
    assert any("unknown rule" in e for e in errors)


def test_schema_violation_is_rejected(usecase: Path):
    _edit_decision(usecase, lambda d: d["spec"]["stages"]["crawl"].pop("rationale"))
    errors, _ = validate_usecase(usecase)
    assert any("'rationale' is a required property" in e for e in errors)


def test_cli_validate_exit_codes(usecase: Path):
    ok = run(str(BUILDER / "validate.py"), str(usecase))
    assert ok.returncode == 0, ok.stdout + ok.stderr
    _edit_decision(usecase, lambda d: d["spec"]["stages"]["crawl"]["choice"].append("apps/databases/mongodb"))
    bad = run(str(BUILDER / "validate.py"), str(usecase))
    assert bad.returncode == 1
    assert "DATA-1" in bad.stdout
