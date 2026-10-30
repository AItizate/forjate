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
    hits = [e for e in errors if "cross-record conflict (walk, message-broker)" in e]
    assert hits and "nats" in hits[0] and "rabbitmq" in hits[0] and "open question" in hits[0]


def test_broker_conflict_via_setting_only(usecase: Path):
    # One record names the broker in settings, the other picks the component: still one conflict.
    _write_decision(usecase, "architecture", {"walk": {"choice": [], "settings": {"broker": "nats"}, "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/brokers/rabbitmq"], "rationale": "y"}})
    errors, _ = validate_usecase(usecase)
    assert any("cross-record conflict (walk, message-broker)" in e for e in errors)


def test_acknowledged_conflict_is_a_warning_not_a_fix(usecase: Path):
    _write_decision(usecase, "architecture", {"walk": {"choice": ["apps/brokers/nats"], "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/brokers/rabbitmq"], "rationale": "y"}},
                    open_questions=[{"id": "Q1", "question": "Architecture chose NATS but the Debezium connector needs RabbitMQ; which broker does the organisation operate?", "blocks_stage": "walk"}])
    errors, warnings = validate_usecase(usecase)
    assert not any("cross-record conflict" in e for e in errors)
    assert any("cross-record conflict (walk, message-broker)" in w and "acknowledged by open question data-pipeline/Q1" in w for w in warnings)
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
    assert any("cross-record conflict (walk, message-broker)" in e and "debezium-postgres-rabbitmq" in e for e in errors)
    assert any("needs apps/brokers/rabbitmq" in w for w in warnings)


def test_conflicts_in_different_stages_do_not_collide(usecase: Path):
    _write_decision(usecase, "architecture", {"crawl": {"choice": ["apps/minio/dev"], "rationale": "x"}})
    _write_decision(usecase, "data-pipeline", {"walk": {"choice": ["apps/minio/single-server"], "rationale": "y"}})
    errors, warnings = validate_usecase(usecase)
    assert not any("cross-record conflict" in m for m in errors + warnings)


# --- phase 3: governance experts share settings and gate ids ----------------------

def test_secrets_setting_conflicts_with_secrets_component(usecase: Path):
    # security says sealed-secrets in settings, devops picks the external-secrets component: one conflict.
    _write_decision(usecase, "security", {"walk": {"choice": [], "settings": {"secrets_mechanism": "sealed-secrets"}, "rationale": "x"}})
    _write_decision(usecase, "devops", {"walk": {"choice": ["apps/security/external-secrets"], "rationale": "y"}})
    errors, _ = validate_usecase(usecase)
    hits = [e for e in errors if "cross-record conflict (walk, secrets-mechanism)" in e]
    assert hits and "apps/sealed-secrets" in hits[0] and "apps/security/external-secrets" in hits[0]


def test_secret_generator_maps_to_no_component(usecase: Path):
    _write_decision(usecase, "security", {"crawl": {"choice": [], "settings": {"secrets_mechanism": "secret-generator"}, "rationale": "x"}})
    _write_decision(usecase, "devops", {"crawl": {"choice": [], "settings": {"secrets_mechanism": "secret-generator"}, "rationale": "y"}})
    errors, warnings = validate_usecase(usecase)
    assert not any("cross-record conflict" in m for m in errors + warnings)


def test_two_secrets_mechanisms_in_one_record_is_a_conflict(usecase: Path):
    _write_decision(usecase, "security", {"walk": {"choice": ["apps/sealed-secrets", "apps/security/external-secrets"], "rationale": "x"}})
    _write_decision(usecase, "devops", {"walk": {"choice": [], "rationale": "y"}})
    errors, _ = validate_usecase(usecase)
    assert any("cross-record conflict (walk, secrets-mechanism)" in e for e in errors)


@pytest.mark.parametrize("key,a,b,owner_a,owner_b", [
    ("network_policy", "default-deny", "none", "security", "devops"),
    ("backup", "snapshot+dump", "none", "data-store", "devops"),
    ("auth_in_front", "oauth2-proxy", "none", "architecture", "security"),
    ("psa_level", "restricted", "baseline", "security", "devops"),
])
def test_governance_shared_setting_conflicts(usecase: Path, key, a, b, owner_a, owner_b):
    # The fixture's own data-store record only sets data_residency and retention at walk.
    stage = "walk"
    _write_decision(usecase, owner_a, {stage: {"choice": [], "settings": {key: a}, "rationale": "x"}})
    _write_decision(usecase, owner_b, {stage: {"choice": [], "settings": {key: b}, "rationale": "y"}})
    errors, _ = validate_usecase(usecase)
    hits = [e for e in errors if f"cross-record conflict ({stage}, setting {key})" in e]
    assert hits and a in hits[0] and b in hits[0]


def test_governance_shared_setting_agreement_is_silent(usecase: Path):
    _write_decision(usecase, "security", {"walk": {"choice": [], "settings": {"network_policy": "default-deny", "psa_level": "restricted"}, "rationale": "x"}})
    _write_decision(usecase, "devops", {"walk": {"choice": [], "settings": {"network_policy": "default-deny", "psa_level": "restricted"}, "rationale": "y"}})
    errors, warnings = validate_usecase(usecase)
    assert not any("cross-record conflict" in m for m in errors + warnings)


def _gate(gid: str, text: str, **check) -> dict:
    g = {"id": gid, "text": text}
    if check:
        g["check"] = check
    return g


def test_gate_id_claimed_with_two_texts_is_a_conflict(usecase: Path):
    _write_decision(usecase, "security", {"walk": {"choice": [], "rationale": "x", "gate_to_next": [_gate("G-SEC-1", "default-deny NetworkPolicy in place")]}})
    _write_decision(usecase, "devops", {"walk": {"choice": [], "rationale": "y", "gate_to_next": [_gate("G-SEC-1", "ArgoCD tracks a tag")]}})
    errors, _ = validate_usecase(usecase)
    hits = [e for e in errors if "cross-record conflict (gate G-SEC-1)" in e]
    assert hits and "security" in hits[0] and "devops" in hits[0] and "do not merge" in hits[0]


def test_gate_id_same_text_in_two_records_is_fine(usecase: Path):
    text = "namespace default-deny with egress allow-list"
    _write_decision(usecase, "security", {"walk": {"choice": [], "rationale": "x", "gate_to_next": [_gate("G-SEC-1", text)]}})
    _write_decision(usecase, "devops", {"walk": {"choice": [], "rationale": "y", "gate_to_next": [_gate("G-SEC-1", text)]}})
    errors, warnings = validate_usecase(usecase)
    assert not any("conflict (gate" in m for m in errors + warnings)


def test_gate_collision_acknowledged_is_a_warning(usecase: Path):
    _write_decision(usecase, "security", {"walk": {"choice": [], "rationale": "x", "gate_to_next": [_gate("G-SEC-1", "default-deny in place")]}})
    _write_decision(usecase, "devops", {"walk": {"choice": [], "rationale": "y", "gate_to_next": [_gate("G-SEC-1", "ArgoCD tracks a tag")]}})
    _write_decision(usecase, "quality", {"walk": {"choice": [], "rationale": "z"}},
                    open_questions=[{"id": "Q1", "question": "G-SEC-1 is claimed by security and devops with different texts; which record owns it?"}])
    errors, warnings = validate_usecase(usecase)
    assert not any("conflict (gate" in e for e in errors)
    assert any("conflict (gate G-SEC-1)" in w and "quality/Q1" in w for w in warnings)


def _write_gates(uc: Path, transitions: dict, overrides: list | None = None) -> None:
    g = {"apiVersion": "forjate.io/v0", "kind": "Gates", "metadata": {"usecase": uc.name, "version": 1},
         "spec": {"transitions": transitions}}
    if overrides is not None:
        g["spec"]["pack_overrides"] = overrides
    (uc / ".builder" / "gates.yaml").write_text(yaml.safe_dump(g, sort_keys=False))


def test_gates_yaml_missing_a_record_gate_is_a_warning(usecase: Path):
    # The fixture's data-store record has G-DS-1 at crawl. Run is skipped by the plan,
    # so a walk gate without a walk->run transition is not reported.
    _write_decision(usecase, "security", {"walk": {"choice": [], "rationale": "x", "gate_to_next": [_gate("G-SEC-1", "default-deny", type="ci", ref="netpol-check")]}})
    _write_gates(usecase, {"crawl->walk": {"gates": [_gate("G-Q-1", "verify Job exits 0", type="verify-job", ref="dbmig-validate")]}})
    errors, warnings = validate_usecase(usecase)
    assert errors == []
    assert any("crawl->walk lacks G-DS-1 from decisions/data-store.yaml" in w for w in warnings)
    assert not any("G-SEC-1" in w for w in warnings)


def test_gates_yaml_consolidated_is_silent(usecase: Path):
    _write_gates(usecase, {"crawl->walk": {"approver": "head of data", "gates": [
        _gate("G-Q-1", "verify Job exits 0", type="verify-job", ref="dbmig-validate"),
        _gate("G-DS-1", "retention of the staging copy agreed with the approver", type="manual", ref="decisions/data-store.yaml"),
    ]}})
    errors, warnings = validate_usecase(usecase)
    assert errors == []
    assert not any("gates.yaml" in w for w in warnings)


def test_gates_yaml_unknown_override_and_wrong_usecase_are_errors(usecase: Path):
    _write_gates(usecase, {"crawl->walk": {"gates": []}}, overrides=[{"rule": "pack:regulated-corp#NOPE-1", "overridden_by": "user-instruction"}])
    errors, _ = validate_usecase(usecase)
    assert any("pack_overrides cites unknown rule" in e for e in errors)
    g = yaml.safe_load((usecase / ".builder/gates.yaml").read_text())
    g["metadata"]["usecase"] = "other"; g["spec"]["pack_overrides"] = []
    (usecase / ".builder/gates.yaml").write_text(yaml.safe_dump(g))
    errors, _ = validate_usecase(usecase)
    assert any("gates.yaml: metadata.usecase" in e for e in errors)


# --- phase 4: ci refs are the checks directory, secret scan, fixtures ------------

CHECKS = REPO / "scripts" / "gates" / "checks"


def test_ci_ref_outside_the_checks_directory_is_an_error_in_gates(usecase: Path):
    gates = {"apiVersion": "forjate.io/v0", "kind": "Gates", "metadata": {"usecase": usecase.name, "version": 1},
             "spec": {"transitions": {"crawl->walk": {"gates": [
                 {"id": "G-SEC-1", "text": "x", "owner": "security", "check": {"type": "ci", "ref": "netpol-check"}},
                 {"id": "G-SEC-2", "text": "y", "owner": "security", "check": {"type": "ci", "ref": "no-such-check"}}]}}}}
    (usecase / ".builder" / "gates.yaml").write_text(yaml.safe_dump(gates, sort_keys=False))
    errors, _ = validate_usecase(usecase)
    assert any("G-SEC-2" in e and "no-such-check" in e and "enum" in e for e in errors)
    assert not any("G-SEC-1" in e for e in errors)


def test_ci_ref_outside_the_checks_directory_is_a_warning_in_a_record(usecase: Path):
    _write_decision(usecase, "security", {"walk": {"choice": [], "rationale": "x", "gate_to_next": [_gate("G-SEC-1", "t", type="ci", ref="made-up")]}})
    errors, warnings = validate_usecase(usecase)
    assert not any("made-up" in e for e in errors)
    assert any("made-up" in w and "no script" in w for w in warnings)


def test_every_check_script_has_the_contract_header():
    scripts = sorted(p for p in CHECKS.glob("*.sh") if not p.name.startswith("_"))
    assert len(scripts) >= 20
    for s in scripts:
        text = s.read_text()
        assert 'source "$(dirname "$0")/_lib.sh"' in text, s.name
        assert text.splitlines()[1].startswith("# "), f"{s.name}: second line must describe the check"


def test_golden_fixtures_validate_with_every_record_and_gates(tmp_path: Path):
    fixtures = BUILDER.parent.parent / "evals" / "fixtures"
    for name, packs in (("invoice-intake", [{"name": "regulated-corp", "source": "context-packs/examples/regulated-corp"}]), ("support-copilot", [])):
        uc = tmp_path / name
        b = uc / ".builder"
        (b / "decisions").mkdir(parents=True)
        shutil.copy(fixtures / "briefs" / f"{name}.yaml", b / "brief.yaml")
        shutil.copy(fixtures / "plans" / f"{name}.yaml", b / "stage-plan.yaml")
        shutil.copy(fixtures / "gates" / f"{name}.yaml", b / "gates.yaml")
        for f in (fixtures / "records" / name).glob("*.yaml"):
            shutil.copy(f, b / "decisions" / f.name)
        # records/<uc>/ is the complete set; its core five are copies of decisions/<uc>/ (what the experts' evals consume)
        for f in (fixtures / "decisions" / name).glob("*.yaml"):
            assert (fixtures / "records" / name / f.name).read_text() == f.read_text(), f"{name}/{f.name}: records/ copy drifted from decisions/"
        (b / "packs.yaml").write_text(yaml.safe_dump({"apiVersion": "forjate.io/v0", "kind": "ActivePacks", "spec": {"packs": packs}}))
        errors, warnings = validate_usecase(uc)
        assert errors == [], f"{name}: {errors}"
        assert not any("lacks" in w for w in warnings), f"{name}: stale gates.yaml: {warnings}"
        areas = {p.stem for p in (b / "decisions").glob("*.yaml")}
        plan = yaml.safe_load((b / "stage-plan.yaml").read_text())
        assert {e["role"] for e in plan["spec"]["experts"] if e["run"]} == areas


def test_secret_scan_finds_literals_patches_and_examples(tmp_path: Path):
    (tmp_path / "configs").mkdir(); (tmp_path / "patches").mkdir()
    (tmp_path / "kustomization.yaml").write_text("configMapGenerator:\n  - name: cfg\n    literals:\n      - OPENAI_API_KEY=sk-live-0123456789abcdef0123456789abcdef\n")
    (tmp_path / "patches" / "env-patch.yaml").write_text("env:\n  - name: GITHUB_TOKEN\n    value: ghp_0123456789abcdefghijklmnopqrstuvwxyz1234\n  - name: DB\n    value: postgres://app:S3cr3tPassw0rdValue@db:5432/x\n")
    (tmp_path / "configs" / "litellm.yaml").write_text("model_list:\n  - litellm_params:\n      api_key: os.environ/KEY\n      api_base: http://ollama-service:11434\n")
    (tmp_path / "configs" / "x.env.example").write_text("DB_PASSWORD=CHANGE_ME\nAPI_TOKEN=Qm9yaW5nVG9rZW5WYWx1ZTEyMzQ1Njc4\n")
    r = run(str(BUILDER / "secret-scan.py"), str(tmp_path), "--json")
    assert r.returncode == 1, r.stdout + r.stderr
    import json
    rules = [f["rule"] for f in json.loads(r.stdout)]
    assert any("openai-style key" in x for x in rules)
    assert any("github token" in x for x in rules)
    assert any("credentials in url" in x for x in rules)
    assert any("not a placeholder" in x for x in rules)
    assert not any("os.environ" in x for x in rules)


def test_secret_scan_is_clean_on_the_repo_overlays():
    r = run(str(BUILDER / "secret-scan.py"), str(REPO / "k8s" / "overlays"))
    assert r.returncode == 0, r.stdout


# --- phase 5 (#23): capabilities from the catalog, snapshots, grader, skill-lint -------

import json
import re

import validate as validate_mod  # noqa: E402

REPO_ROOT = BUILDER.parent.parent.parent.parent
CATALOG = REPO_ROOT / "wiki" / "catalog.json"
CAPABILITIES = REPO_ROOT / "wiki" / "catalog-capabilities.yaml"
CONTRACTS = REPO_ROOT / "docs" / "use-case-builder" / "contracts.md"


def test_secrets_ranking_comes_from_the_catalog():
    rules = validate_mod.CatalogRules(json.loads(CATALOG.read_text()))
    assert rules.available
    assert rules.secrets_rank["secret-generator"] == 0
    assert rules.secrets_rank["sealed-secrets"] < rules.secrets_rank["external-secrets"]
    assert "vault" not in rules.secrets_rank  # deprecated component, no longer curated
    # Nothing in the validator module names a component.
    src = (BUILDER / "validate.py").read_text()
    assert not re.search(r"apps/(databases|brokers|ai-models|minio|sealed-secrets|security)/", src)


def test_exclusive_groups_and_setting_maps_come_from_the_catalog():
    rules = validate_mod.CatalogRules(json.loads(CATALOG.read_text()))
    assert {"apps/brokers/nats", "apps/brokers/rabbitmq"} <= rules.groups["message-broker"]
    assert rules.setting_to_group["broker"] == ("message-broker", {"nats": "apps/brokers/nats", "rabbitmq": "apps/brokers/rabbitmq"})
    assert rules.setting_to_group["secrets_mechanism"][1]["sealed-secrets"] == "apps/sealed-secrets"
    # openbao is a store, not a mechanism: pairing it with external-secrets is not a conflict.
    assert "apps/security/openbao" not in rules.groups["secrets-mechanism"]


def test_without_a_catalog_the_rules_are_empty_and_marked_unavailable():
    rules = validate_mod.CatalogRules(None)
    assert not rules.available and rules.groups == {} and rules.secrets_rank == {}


def test_secrets_rule_weaker_mechanism_is_rejected_and_unknown_mechanism_is_named(usecase: Path):
    rule = {"enforce": "must", "applies_to": ["*"], "rule": {"type": "secrets_mechanism", "value": "external-secrets"}}
    sd = {"settings": {"secrets_mechanism": "sealed-secrets"}}
    msg = validate_mod.check_rule("pack:x#SEC-1", rule, "security", "run", sd, "pii")
    assert msg and "weaker" in msg
    ok = validate_mod.check_rule("pack:x#SEC-1", rule, "security", "run", {"settings": {"secrets_mechanism": "external-secrets"}}, "pii")
    assert ok is None
    bogus = dict(rule, rule={"type": "secrets_mechanism", "value": "vault"})
    msg = validate_mod.check_rule("pack:x#SEC-2", bogus, "security", "run", sd, "pii")
    assert msg and "no catalog component provides" in msg


def test_openbao_with_external_secrets_is_not_a_conflict(usecase: Path):
    _write_decision(usecase, "security", {"walk": {"choice": ["apps/security/external-secrets", "apps/security/openbao"],
                                                   "settings": {"secrets_mechanism": "external-secrets"}, "rationale": "x"}})
    errors, warnings = validate_usecase(usecase)
    assert not any("secrets-mechanism" in m for m in errors + warnings)


def test_capability_vocabulary_matches_contracts_and_catalog():
    vocab = yaml.safe_load(CAPABILITIES.read_text())["capabilities"]
    text = CONTRACTS.read_text()
    section = text.split("## Catalog capabilities", 1)[1].split("### Component properties", 1)[0]
    documented = set(re.findall(r"^\| `([a-z0-9-]+)` \|", section, re.MULTILINE))
    assert documented == set(vocab), f"contracts.md vs catalog-capabilities.yaml: {documented ^ set(vocab)}"
    catalog = json.loads(CATALOG.read_text())
    assert set(catalog["capabilities"]) == set(vocab)
    used = {c for comp in catalog["components"] for c in comp.get("capabilities") or []}
    assert used <= set(vocab)
    for comp in catalog["components"]:
        assert "roles" not in comp
        assert isinstance(comp["secrets"], dict) and "takes" in comp["secrets"]


def test_snapshots_exist_for_every_asking_skill_and_are_labelled():
    vocab = yaml.safe_load(CAPABILITIES.read_text())
    skills = {s for c in vocab["capabilities"].values() for s in c["asked_by"]} | set(vocab["snapshot_all"])
    for skill in skills:
        snap = BUILDER.parent.parent / "skills" / skill / "references" / "catalog-snapshot.md"
        assert snap.is_file(), f"{skill} has no catalog snapshot; run scripts/wiki-compile.py"
        body = snap.read_text()
        assert "generated by scripts/wiki-compile.py" in body and "snapshot, not a rule" in body
    devops = (BUILDER.parent.parent / "skills" / "devops" / "references" / "catalog-snapshot.md").read_text()
    assert "## `backup`" in devops and "No component today" in devops
    assert not (BUILDER.parent.parent / "skills" / "business" / "references" / "catalog-snapshot.md").exists()


def test_grader_choice_has_capability(tmp_path: Path):
    sys.path.insert(0, str(BUILDER.parent.parent / "evals"))
    import grade  # noqa: E402
    (tmp_path / "wiki").mkdir()
    shutil.copy(CATALOG, tmp_path / "wiki" / "catalog.json")
    rec = tmp_path / "d.yaml"
    rec.write_text(yaml.safe_dump({"spec": {"stages": {
        "crawl": {"choice": ["apps/databases/redis", "apps/databases/postgres"]},
        "walk": {"choice": ["apps/databases/postgres", "apps/brokers/nats"]}}}}))
    ok, ev = grade.check({"type": "choice_has_capability", "path": "d.yaml", "capability": "session-memory"}, tmp_path)
    assert ok and "redis" in ev
    ok, _ = grade.check({"type": "choice_has_capability", "path": "d.yaml", "capability": "session-memory", "stage": "walk"}, tmp_path)
    assert not ok
    ok, _ = grade.check({"type": "choice_lacks_capability", "path": "d.yaml", "capability": "semantic-memory"}, tmp_path)
    assert ok
    ok, _ = grade.check({"type": "choice_lacks_capability", "path": "d.yaml", "capability": "message-broker", "stage": "walk"}, tmp_path)
    assert not ok
    ok, ev = grade.check({"type": "yaml_expr", "path": "d.yaml", "expr": "'message-broker' in choice_capabilities('walk') and 'working-memory' in choice_capabilities()"}, tmp_path)
    assert ok, ev
    ok, ev = grade.check({"type": "choice_has_capability", "path": "missing.yaml", "capability": "cache"}, tmp_path)
    assert not ok


def test_skill_lint_runs_and_allows_single_option_components(tmp_path: Path):
    r = run(str(BUILDER / "skill-lint.py"), "--quiet")
    assert r.returncode == 0, r.stdout + r.stderr  # warn mode never fails
    assert "| ux |" in r.stdout
    # docling is the only document-parsing option: naming it is allowed.
    lint = __import__("importlib").util.spec_from_file_location("skill_lint", BUILDER / "skill-lint.py")
    mod = __import__("importlib").util.module_from_spec(lint); lint.loader.exec_module(mod)
    catalog = json.loads(CATALOG.read_text())
    single = mod.single_option_components(catalog)
    assert "apps/document-processing/docling" in single and "apps/databases/postgres" not in single
    # a skill that ladders a multi-option component by path is flagged; a marked line and a single option are not
    skill = tmp_path / "demo"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("# demo\n| Walk | `apps/databases/postgres` |\n")
    (skill / "references" / "notes.md").write_text("Example: `apps/databases/postgres` as an illustration <!-- skill-lint: allow -->\nParser: `apps/document-processing/docling`\n")
    pattern = mod.path_pattern([c["path"] for c in catalog["components"]])
    hits, skipped = mod.lint_skill(skill, pattern, single)
    assert [h[2] for h in hits] == ["apps/databases/postgres"] and skipped == 2
    # the rewritten skills are clean in strict mode
    strict = run(str(BUILDER / "skill-lint.py"), "--strict", "--skills", "ai-engineering", "architecture", "data-store", "data-pipeline", "business")
    assert strict.returncode == 0, strict.stdout


# ------------------------------------------------------------ PSA exceptions (#22)

USECASES = REPO / "k8s" / "overlays" / "usecases"


def _golden(tmp_path: Path, name: str) -> Path:
    dst = tmp_path / name
    shutil.copytree(USECASES / name / ".builder", dst / ".builder")
    return dst


def _psa_messages(msgs: list[str]) -> list[str]:
    return [m for m in msgs if "psa_exceptions" in m or "psa_level" in m]


def test_golden_psa_exceptions_are_clean(tmp_path: Path):
    for name in ("invoice-intake", "support-copilot"):
        errors, warnings = validate_usecase(_golden(tmp_path, name))
        assert errors == [] and _psa_messages(warnings) == [], (name, errors, warnings)


def test_psa_exception_in_the_use_case_namespace_is_an_error(tmp_path: Path):
    uc = _golden(tmp_path, "invoice-intake")
    f = uc / ".builder" / "decisions" / "security.yaml"
    d = yaml.safe_load(f.read_text())
    d["spec"]["stages"]["walk"]["psa_exceptions"][0]["namespace"] = "uc-invoice-intake"
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    errors, _ = validate_usecase(uc)
    assert any("never lowers the use case's namespace" in e for e in errors)


def test_missing_psa_exceptions_are_warnings_derived_from_the_catalog(tmp_path: Path):
    uc = _golden(tmp_path, "invoice-intake")
    f = uc / ".builder" / "decisions" / "security.yaml"
    d = yaml.safe_load(f.read_text())
    for sd in d["spec"]["stages"].values():
        sd.pop("psa_exceptions", None)
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    errors, warnings = validate_usecase(uc)
    psa = _psa_messages(warnings)
    assert errors == []
    catalog = json.loads(CATALOG.read_text())
    shared_privileged = {c["namespace"] for c in catalog["components"] if c.get("namespace") and c.get("psa_level") == "privileged"}
    assert any("would run in uc-invoice-intake" in w for w in psa)
    assert any(any(f"{ns} needs a level below" in w for ns in shared_privileged) for w in psa)


def test_validator_names_no_component():
    """Where a component runs and the level it meets come from wiki/catalog.json, never from the validator."""
    src = (BUILDER / "validate.py").read_text()
    assert not re.search(r"[\"']apps/", src)


def _wiki_compile():
    import importlib.util
    spec = importlib.util.spec_from_file_location("wiki_compile", REPO / "scripts" / "wiki-compile.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wiki_compile"] = mod      # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_pod_psa_level_is_derived_from_the_pod_spec():
    wc = _wiki_compile()
    hardened = {"securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{"name": "a", "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}}]}
    assert wc.pod_psa_level(hardened) == "restricted"
    assert wc.pod_psa_level({"containers": [{"name": "a"}]}) == "baseline"
    assert wc.pod_psa_level({"containers": [{"name": "a"}], "volumes": [{"name": "h", "hostPath": {"path": "/"}}]}) == "privileged"
    assert wc.pod_psa_level({"hostNetwork": True, "containers": [{"name": "a"}]}) == "privileged"
    assert wc.pod_psa_level({"containers": [{"name": "a", "securityContext": {"capabilities": {"add": ["NET_ADMIN"]}}}]}) == "privileged"


def test_catalog_overrides_cannot_contradict_the_tree():
    wc = _wiki_compile()
    tree = {"psa_level": "privileged", "namespace": "storage-system", "declared": {"storage-system"}, "remote": False}
    extra = {"psa_restricted": True}
    errors = wc.merge_psa_and_namespace("apps/x", extra, tree, {"namespace": "other"})
    assert any("namespace override 'other'" in e for e in errors)
    assert any("psa_restricted is true" in e for e in errors)
    extra = {"psa_restricted": "unknown"}
    assert wc.merge_psa_and_namespace("apps/x", extra, tree, {}) == []
    assert (extra["psa_level"], extra["namespace"], extra["namespace_how"]) == ("privileged", "storage-system", "declares")
    extra = {"psa_restricted": False}
    wc.merge_psa_and_namespace("apps/x", extra, dict(tree, namespace="pinned", declared=set()), {"namespace": None})
    assert extra["namespace"] is None and extra["namespace_how"] is None


def test_catalog_carries_psa_level_and_namespace_for_every_component():
    catalog = json.loads(CATALOG.read_text())
    for c in catalog["components"]:
        assert c["psa_level"] in ("privileged", "baseline", "restricted", "n/a", "unknown"), c["path"]
        assert (c["namespace"] is None) == (c["namespace_how"] is None), c["path"]
        if c.get("psa_restricted") is True:
            assert c["psa_level"] == "restricted", c["path"]


def test_assembly_reproduces_the_golden_overlays(tmp_path: Path):
    """The golden overlays are generated: regenerating them from their records and today's catalog must give
    the committed files, so a catalog change (a component's namespace, its PSA level) cannot drift unseen."""
    k8s = tmp_path / "k8s"
    (k8s / "overlays" / "usecases").mkdir(parents=True)
    for d in ("components", "base"):
        (k8s / d).symlink_to(REPO / "k8s" / d)
    for name in ("invoice-intake", "support-copilot"):
        src, dst = USECASES / name, k8s / "overlays" / "usecases" / name
        shutil.copytree(src / ".builder", dst / ".builder")
        r = run(str(BUILDER.parent.parent / "skills" / "kustomize" / "scripts" / "assemble.py"), str(dst), "--force")
        assert r.returncode == 0, r.stdout + r.stderr
        def files(root: Path) -> set[str]:
            # the working tree minus the inputs (.builder/, app/) and the gitignored .env copies of the examples
            return {p.relative_to(root).as_posix() for p in root.rglob("*")
                    if p.is_file() and not set(p.relative_to(root).parts[:1]) & {".builder", "app"} and p.suffix != ".env"
                    and "__pycache__" not in p.parts}
        generated, committed = files(dst), files(src)
        assert committed - generated == set(), f"{name}: committed files the assembly no longer writes"
        assert generated - committed == set(), f"{name}: files the assembly writes that are not committed"
        for rel_path in generated:
            assert (dst / rel_path).read_text() == (src / rel_path).read_text(), f"{name}: {rel_path} drifted from the assembly"


def test_tenant_target_gives_psa_exceptions_their_own_namespace_child(tmp_path: Path):
    k8s = tmp_path / "k8s"
    (k8s / "overlays" / "usecases").mkdir(parents=True)
    for d in ("components", "base"):
        (k8s / d).symlink_to(REPO / "k8s" / d)
    uc = k8s / "overlays" / "usecases" / "invoice-intake"
    shutil.copytree(USECASES / "invoice-intake" / ".builder", uc / ".builder")
    tenant = tmp_path / "demo-iac"
    r = run(str(BUILDER.parent.parent / "skills" / "kustomize" / "scripts" / "assemble.py"), str(uc),
            "--target", "tenant", "--tenant-repo", str(tenant), "--tenant", "demo", "--factory-ref", "v1.1.0")
    assert r.returncode == 0, r.stdout + r.stderr
    root = yaml.safe_load((tenant / "k8s" / "kustomization.yaml").read_text())
    assert "./namespaces/uc-invoice-intake-baseline" in root["resources"]
    exc = yaml.safe_load((tenant / "k8s" / "namespaces" / "uc-invoice-intake-baseline" / "kustomization.yaml").read_text())
    assert exc["namespace"] == "uc-invoice-intake-baseline"
    assert any("apps/databases/postgres" in x for x in exc["resources"])
    child = yaml.safe_load((tenant / "k8s" / "namespaces" / "uc-invoice-intake" / "kustomization.yaml").read_text())
    assert not any("apps/databases/postgres" in x for x in child["resources"]) and "aliases.yaml" in child["resources"]
    ns = yaml.safe_load((tenant / "k8s" / "namespaces" / "uc-invoice-intake" / "namespace.yaml").read_text())
    assert ns["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"


# --- phase 5 (#27): governance settings vocabulary, autonomy ceiling, per-stage component sets ---------

SKILLS_DIR = BUILDER.parent.parent / "skills"
ENTERPRISE = PACKS / "enterprise-in-a-box"
RECORDLESS = {"coordinator", "stage-planner", "kustomize", "context-pack", "app-scaffold"}


def _governance_vocabulary() -> dict[str, dict]:
    text = CONTRACTS.read_text()
    section = text.split("### Governance settings", 1)[1].split("## What `validate.py` checks", 1)[0]
    rows = {}
    for m in re.finditer(r"^\| `([a-z_]+)` \| (.*?) \| (.*?) \| (.*?) \| .*? \| .*? \|$", section, re.MULTILINE):
        key, values, owner, copied = m.groups()
        rows[key] = {"values": values, "owner": owner.split(" ")[0], "copied_by": [c.strip().split(" ")[0] for c in copied.split(",") if c.strip() and c.strip() != "—"]}
    assert len(rows) >= 20, rows.keys()
    return rows


def _posture_section(skill: str) -> str | None:
    text = (SKILLS_DIR / skill / "SKILL.md").read_text()
    if "## Governance posture" not in text:
        return None
    return text.split("## Governance posture", 1)[1].split("\n## ", 1)[0]


def test_governance_vocabulary_matches_the_skills_that_document_it():
    vocab = _governance_vocabulary()
    for skill in sorted(d.name for d in SKILLS_DIR.iterdir() if (d / "SKILL.md").is_file()):
        section = _posture_section(skill)
        if section is None:
            continue
        documented = set(re.findall(r"`([a-z_]+)`", section))
        owned = {k for k, v in vocab.items() if v["owner"] == skill}
        copied = {k for k, v in vocab.items() if skill in v["copied_by"]}
        assert owned <= documented, f"{skill}: owns {owned - documented} per contracts.md but its Governance posture does not document them"
        assert copied <= documented, f"{skill}: copies {copied - documented} per contracts.md but its Governance posture does not document them"
        # a key the skill writes is in the vocabulary (settings the validator does not know are not posture)
        rows = set(re.findall(r"^\| `([a-z_]+)` \|", section, re.MULTILINE))
        assert rows <= set(vocab) | {"open_standards_exceptions", "auth_in_front"}, f"{skill}: posture table names keys outside contracts.md: {rows - set(vocab)}"


def test_enterprise_pack_targets_are_vocabulary_and_applies_to_owners_or_copiers():
    vocab = _governance_vocabulary()
    pack, constraints, errors = load_pack(ENTERPRISE)
    rules = constraints["rules"]
    assert errors == []
    for entry in pack["spec"]["sources"]:
        if entry["kind"] != "constraint":
            continue
        rule = rules[entry["id"]]
        target = rule["target"]
        assert target in vocab or target == "auth_in_front", f"{entry['id']}: target {target} is not a governance setting"
        if target not in vocab:
            continue
        writers = {vocab[target]["owner"], *vocab[target]["copied_by"]}
        for role in entry["applies_to"]:
            if role in RECORDLESS:
                continue
            assert role in writers, f"{entry['id']}: applies to {role}, which neither owns nor copies {target} per contracts.md"
    exe2 = rules["EXE-2"]
    assert exe2["type"] == "deny_setting_value" and exe2["value"] == ["disabled"]


def _write_plan_autonomy(uc: Path, per_stage: dict[str, str], brief_autonomy: str | None = None) -> None:
    p = uc / ".builder" / "stage-plan.yaml"
    plan = yaml.safe_load(p.read_text())
    for stage, aut in per_stage.items():
        plan["spec"]["stages"][stage]["autonomy"] = aut
    p.write_text(yaml.safe_dump(plan, sort_keys=False))
    if brief_autonomy:
        b = uc / ".builder" / "brief.yaml"
        brief = yaml.safe_load(b.read_text())
        brief["spec"]["autonomy"] = brief_autonomy
        b.write_text(yaml.safe_dump(brief, sort_keys=False))


def test_crawl_autonomy_above_assistive_is_an_error(usecase: Path):
    _write_plan_autonomy(usecase, {"crawl": "semi-autonomous"})
    errors, _ = validate_usecase(usecase)
    assert any("crawl autonomy 'semi-autonomous'" in e for e in errors)


def test_stage_autonomy_above_the_brief_is_an_error(usecase: Path):
    _write_plan_autonomy(usecase, {"crawl": "assistive", "walk": "autonomous"}, brief_autonomy="semi-autonomous")
    errors, _ = validate_usecase(usecase)
    assert any("walk autonomy 'autonomous' exceeds the brief's 'semi-autonomous'" in e for e in errors)


def test_record_autonomy_above_the_plan_ceiling_is_an_error(usecase: Path):
    _write_plan_autonomy(usecase, {"crawl": "assistive", "walk": "semi-autonomous"})
    _write_decision(usecase, "ai-engineering", {"walk": {"choice": [], "settings": {"autonomy": "autonomous"}, "rationale": "x"}})
    errors, _ = validate_usecase(usecase)
    assert any("settings.autonomy 'autonomous' exceeds the plan's ceiling 'semi-autonomous'" in e for e in errors)
    _write_decision(usecase, "ai-engineering", {"walk": {"choice": [], "settings": {"autonomy": "assistive"}, "rationale": "x"}})
    errors, _ = validate_usecase(usecase)
    assert not any("settings.autonomy" in e for e in errors)


def test_governance_settings_are_shared_across_records(usecase: Path):
    _write_decision(usecase, "ai-engineering", {"walk": {"choice": [], "settings": {"write_actions": "approval-required"}, "rationale": "x"}})
    _write_decision(usecase, "security", {"walk": {"choice": [], "settings": {"write_actions": "autonomous"}, "rationale": "y"}})
    errors, _ = validate_usecase(usecase)
    assert any("cross-record conflict (walk, setting write_actions)" in e for e in errors)


def test_dropped_component_without_replacement_is_a_warning_and_a_same_capability_replacement_is_silent(usecase: Path):
    # Crawl runs a dev object store; Walk's records do not repeat it.
    _write_decision(usecase, "architecture", {"crawl": {"choice": ["apps/minio/dev"], "rationale": "x"},
                                              "walk": {"choice": [], "rationale": "y"}})
    _, warnings = validate_usecase(usecase)
    assert any("apps/minio/dev was chosen at crawl and is gone at walk" in w for w in warnings)
    # The Walk record names it: dropped on purpose.
    _write_decision(usecase, "architecture", {"crawl": {"choice": ["apps/minio/dev"], "rationale": "x"},
                                              "walk": {"choice": [], "rationale": "the dev object store is retired; artifacts move to the system of record"}})
    _, warnings = validate_usecase(usecase)
    assert not any("is gone at walk" in w for w in warnings)
    # Another component with the same capability supersedes it: silent.
    _write_decision(usecase, "architecture", {"crawl": {"choice": ["apps/minio/dev"], "rationale": "x"},
                                              "walk": {"choice": ["apps/minio/single-server"], "rationale": "y"}})
    _, warnings = validate_usecase(usecase)
    assert not any("is gone at walk" in w for w in warnings)


def test_psa_check_reads_the_stage_set_the_assembly_builds(tmp_path: Path):
    """A Crawl component that no Walk record chooses is not in Walk's overlay, so an exception listing it at Walk is stale."""
    uc = _golden(tmp_path, "invoice-intake")
    f = uc / ".builder" / "decisions" / "security.yaml"
    d = yaml.safe_load(f.read_text())
    entry = next(e for e in d["spec"]["stages"]["walk"]["psa_exceptions"] if e["namespace"] == "uc-invoice-intake-baseline")
    entry["components"].append("apps/minio/dev")
    f.write_text(yaml.safe_dump(d, sort_keys=False))
    _, warnings = validate_usecase(uc)
    assert any("apps/minio/dev is not chosen by any record at walk" in w for w in warnings)
    from common import stage_components  # noqa: E402
    decisions = {p.stem: yaml.safe_load(p.read_text()) for p in (uc / ".builder" / "decisions").glob("*.yaml")}
    assert "apps/minio/dev" in stage_components(decisions, "crawl") and "apps/minio/dev" not in stage_components(decisions, "walk")


def test_walk_overlay_deletes_what_crawl_ran_and_walk_does_not():
    relocated = yaml.safe_load((USECASES / "invoice-intake" / "stages" / "walk" / "relocated" / "kustomization.yaml").read_text())
    deletes = [p for p in relocated["patches"] if "$patch: delete" in p["patch"]]
    assert any(p["target"] == {"kind": "Pod", "name": "minio", "namespace": "uc-invoice-intake"} for p in deletes)
    walk = [p for p in (USECASES / "invoice-intake" / "stages" / "walk").rglob("*minio-secret*") if p.suffix != ".env"]
    assert walk == [], "the dev object store's Secret left Walk with it"
