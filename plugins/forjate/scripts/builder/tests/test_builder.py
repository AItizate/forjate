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


def test_golden_briefs_validate():
    from common import load_yaml, schema_errors
    briefs = sorted((BUILDER.parent.parent / "evals" / "fixtures" / "briefs").glob("*.yaml"))
    assert len(briefs) >= 3
    for b in briefs:
        assert schema_errors("brief", load_yaml(b), str(b)) == []


# --- cross-record consistency (check 6) -------------------------------------

def _write_decision(uc: Path, area: str, stages: dict, open_questions: list | None = None) -> None:
    d = {"apiVersion": "forjate.io/v0", "kind": "Decision",
         "metadata": {"area": area, "usecase": uc.name, "author": f"forjate:{area}", "version": 1},
         "spec": {"stages": stages}}
    if open_questions:
        d["spec"]["open_questions"] = open_questions
    (uc / ".builder" / "decisions" / f"{area}.yaml").write_text(yaml.safe_dump(d, sort_keys=False))


def test_broker_conflict_across_records_is_an_error(usecase: Path):
    _write_decision(usecase, "architecture", {"walk": {"choice": ["apps/brokers/nats"], "settings": {"broker": "nats"}, "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/brokers/rabbitmq"], "settings": {"broker": "rabbitmq"}, "rationale": "y"}})
    errors, _ = validate_usecase(usecase)
    hits = [e for e in errors if "cross-record conflict (walk, broker)" in e]
    assert hits and "nats" in hits[0] and "rabbitmq" in hits[0] and "open question" in hits[0]


def test_broker_conflict_via_setting_only(usecase: Path):
    # One record names the broker in settings, the other picks the component: still one conflict.
    _write_decision(usecase, "architecture", {"walk": {"choice": [], "settings": {"broker": "nats"}, "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/brokers/rabbitmq"], "rationale": "y"}})
    errors, _ = validate_usecase(usecase)
    assert any("cross-record conflict (walk, broker)" in e for e in errors)


def test_acknowledged_conflict_is_a_warning_not_a_fix(usecase: Path):
    _write_decision(usecase, "architecture", {"walk": {"choice": ["apps/brokers/nats"], "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/brokers/rabbitmq"], "rationale": "y"}},
                    open_questions=[{"id": "Q1", "question": "Architecture chose NATS but the Debezium connector needs RabbitMQ; which broker does the organisation operate?", "blocks_stage": "walk"}])
    errors, warnings = validate_usecase(usecase)
    assert not any("cross-record conflict" in e for e in errors)
    assert any("cross-record conflict (walk, broker)" in w and "acknowledged by open question data-pipeline/Q1" in w for w in warnings)
    # The records are untouched: both brokers are still there for the user to decide.
    arch = yaml.safe_load((usecase / ".builder/decisions/architecture.yaml").read_text())
    assert arch["spec"]["stages"]["walk"]["choice"] == ["apps/brokers/nats"]


def test_shared_setting_conflict_is_an_error(usecase: Path):
    # data-store fixture says data_residency eu at walk; a devops record saying us conflicts.
    _write_decision(usecase, "devops", {"walk": {"choice": [], "settings": {"data_residency": "us"}, "rationale": "x"}})
    errors, _ = validate_usecase(usecase)
    assert any("cross-record conflict (walk, setting data_residency)" in e and "eu" in e and "us" in e for e in errors)


def test_same_choice_across_records_is_not_a_conflict(usecase: Path):
    _write_decision(usecase, "architecture", {"walk": {"choice": ["apps/brokers/nats"], "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/brokers/nats"], "settings": {"broker": "nats"}, "rationale": "y"}})
    errors, warnings = validate_usecase(usecase)
    assert not any("cross-record conflict" in m for m in errors + warnings)


def test_cdc_connector_implies_its_broker(usecase: Path):
    _write_decision(usecase, "architecture", {"walk": {"choice": ["apps/brokers/nats"], "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/cdc/debezium-postgres-rabbitmq"], "rationale": "y"}})
    errors, warnings = validate_usecase(usecase)
    assert any("cross-record conflict (walk, broker)" in e and "debezium-postgres-rabbitmq" in e for e in errors)
    assert any("needs apps/brokers/rabbitmq" in w for w in warnings)


def test_conflicts_in_different_stages_do_not_collide(usecase: Path):
    _write_decision(usecase, "architecture", {"crawl": {"choice": ["apps/minio/dev"], "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/minio/single-server"], "rationale": "y"}})
    errors, warnings = validate_usecase(usecase)
    assert not any("cross-record conflict" in m for m in errors + warnings)
