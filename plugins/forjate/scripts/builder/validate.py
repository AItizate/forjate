#!/usr/bin/env python3
"""Validate a use case's .builder/ artifacts.

    validate.py <usecase-dir>...

Checks, per use case:
  1. every artifact validates against its schema (brief, stage-plan, decisions, gates, packs)
  2. every catalog component referenced by a decision exists under k8s/components/
  3. every pack rule cited in constrained_by / caused_by_rule exists in an active pack
  4. no decision violates a `must` constraint of a structured type that applies
     to its stage and to the brief's data classification
  5. consistency between stage-plan and decisions: experts the plan marks as
     run=true have a record, decisions do not cover stages the plan skipped
  6. cross-record consistency: two records that choose incompatible components for the
     same stage (NATS vs RabbitMQ, LanceDB vs Milvus, Ollama vs vLLM, ...) or disagree on
     a shared setting (broker, psa_level, secrets_mechanism, data_residency, data_egress)
     are a conflict. A conflict is an error unless a record acknowledges it with an open
     question that names both sides; the validator never picks a winner.

Exit 1 on any error. Warnings never fail the run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from common import BuilderError, STAGES, component_exists, die, load_yaml, report, schema_errors
from packs import active_packs, load_pack, RULE_REF_RE

RULE_REF = re.compile(r"^pack:(?P<pack>[a-z0-9-]+)#(?P<id>[A-Z][A-Z0-9]*-[0-9]+)$")
PSA_RANK = {"privileged": 0, "baseline": 1, "restricted": 2}

# Cross-record consistency (check 6). Components in one group are mutually exclusive
# within a use case; a setting in SHARED_SETTINGS must have one value per stage across
# every record that states it. Settings that name a component map onto the group so
# "broker: nats" in one record and apps/brokers/rabbitmq in another is one conflict.
EXCLUSIVE_GROUPS = {
    "broker": {"apps/brokers/nats", "apps/brokers/rabbitmq"},
    "vector store": {"apps/databases/lancedb", "apps/databases/milvus"},
    "inference server": {"apps/ai-models/ollama", "apps/ai-models/vllm"},
    "object storage": {"apps/minio/dev", "apps/minio/single-server"},
    "secrets mechanism": {"apps/sealed-secrets", "apps/security/external-secrets", "apps/security/vault"},
}
SETTING_TO_GROUP = {
    "broker": ("broker", {"nats": "apps/brokers/nats", "rabbitmq": "apps/brokers/rabbitmq"}),
    "inference": ("inference server", {"ollama": "apps/ai-models/ollama", "vllm": "apps/ai-models/vllm"}),
}
SHARED_SETTINGS = ("psa_level", "secrets_mechanism", "data_residency", "data_egress")
CDC_BROKER = {"-nats": "apps/brokers/nats", "-rabbitmq": "apps/brokers/rabbitmq"}
SECRETS_RANK = {"secret-generator": 0, "sealed-secrets": 1, "external-secrets": 2, "vault": 2}


def _glob(pattern: str, s: str) -> bool:
    return re.fullmatch(re.escape(pattern).replace(r"\*", ".*"), s) is not None


def load_rules(packs: list[tuple[str, Path]]) -> tuple[dict[str, dict], list[str]]:
    """All rules of all active packs, keyed by 'pack:<name>#<ID>', with the source's enforce level."""
    rules: dict[str, dict] = {}
    errors: list[str] = []
    for name, pack_dir in packs:
        manifest, constraints, errs = load_pack(pack_dir)
        errors += errs
        if errs:
            continue
        for src in manifest["spec"]["sources"]:
            ref = f"pack:{name}#{src['id']}"
            entry = {"enforce": src["enforce"], "applies_to": src.get("applies_to") or manifest["spec"]["applies_to"]}
            if src["kind"] == "constraint":
                rid = RULE_REF_RE.match(src["path"]).group("id")
                entry["rule"] = constraints["rules"][rid]
            rules[ref] = entry
    return rules, errors


def check_rule(ref: str, entry: dict, area: str, stage: str, sd: dict, data_class: str) -> str | None:
    """Return an error string if the stage decision violates this must-rule."""
    rule = entry.get("rule")
    if not rule or entry["enforce"] != "must":
        return None
    if "*" not in entry["applies_to"] and area not in entry["applies_to"]:
        return None
    if rule.get("stages") and stage not in rule["stages"]:
        return None
    if rule.get("data_classes") and data_class not in rule["data_classes"]:
        return None

    t, v = rule["type"], rule["value"]
    choice = sd.get("choice") or []
    settings = sd.get("settings") or {}
    tgt = rule.get("target")

    if t == "deny_components":
        bad = [c for c in choice if c in v]
        return f"uses denied component(s) {bad} ({ref})" if bad else None
    if t == "allow_components_only":
        bad = [c for c in choice if c not in v]
        return f"uses component(s) outside allowlist {bad} ({ref})" if bad else None
    if t == "require_components":
        missing = [c for c in v if c not in choice]
        return f"missing required component(s) {missing} ({ref})" if missing else None
    if t == "min_psa_level" and "psa_level" in settings:
        if PSA_RANK.get(str(settings["psa_level"]), -1) < PSA_RANK[v]:
            return f"psa_level '{settings['psa_level']}' below required '{v}' ({ref})"
        return None
    if t == "secrets_mechanism" and "secrets_mechanism" in settings:
        if SECRETS_RANK.get(str(settings["secrets_mechanism"]), -1) < SECRETS_RANK[v]:
            return f"secrets_mechanism '{settings['secrets_mechanism']}' weaker than required '{v}' ({ref})"
        return None
    if t in {"model_allowlist", "model_denylist"} and "model" in settings:
        models = settings["model"] if isinstance(settings["model"], list) else [settings["model"]]
        for m in models:
            hit = any(_glob(p, str(m)) for p in v)
            if t == "model_allowlist" and not hit:
                return f"model '{m}' not in allowlist ({ref})"
            if t == "model_denylist" and hit:
                return f"model '{m}' is denied ({ref})"
        return None
    if t == "data_egress" and "data_egress" in settings:
        rank = {"none": 0, "anonymized": 1, "any": 2}
        if rank.get(str(settings["data_egress"]), 9) > rank[v]:
            return f"data_egress '{settings['data_egress']}' exceeds allowed '{v}' ({ref})"
        return None
    if t == "data_residency" and "data_residency" in settings:
        if str(settings["data_residency"]) != v:
            return f"data_residency '{settings['data_residency']}' != required '{v}' ({ref})"
        return None
    if t == "max_cost_usd_month" and "estimated_cost_usd_month" in sd:
        if float(sd["estimated_cost_usd_month"]) > float(v):
            return f"estimated cost {sd['estimated_cost_usd_month']} exceeds {v} ({ref})"
        return None
    if t == "naming_pattern" and tgt in settings:
        if not re.fullmatch(v, str(settings[tgt])):
            return f"{tgt} '{settings[tgt]}' does not match /{v}/ ({ref})"
        return None
    if t == "require_setting":
        if tgt not in settings:
            return f"setting '{tgt}' is required ({ref})"
        if v not in (None, "", "*") and str(settings[tgt]) != str(v):
            return f"setting '{tgt}' must be '{v}', got '{settings[tgt]}' ({ref})"
        return None
    if t == "deny_setting_value" and tgt in settings:
        vals = v if isinstance(v, list) else [v]
        if settings[tgt] in vals:
            return f"setting '{tgt}' has denied value '{settings[tgt]}' ({ref})"
        return None
    return None


def _acknowledged(decisions: dict[str, dict], values: list[str]) -> str | None:
    """Return 'area/Qn' if some record raises an open question naming every conflicting value."""
    needles = []
    for v in values:
        v = str(v)
        needles.append([v.lower()] + ([v.rsplit("/", 1)[-1].lower()] if "/" in v else []))
    for area, d in decisions.items():
        for q in d["spec"].get("open_questions", []):
            text = str(q.get("question", "")).lower()
            if all(any(re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", text) for n in alts) for alts in needles):
                return f"{area}/{q.get('id', '?')}"
    return None


def cross_record_conflicts(decisions: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Check 6. Returns (errors, warnings). Never mutates a record."""
    errors: list[str] = []
    warnings: list[str] = []
    if len(decisions) < 2:
        return errors, warnings
    for stage in STAGES:
        # group -> value -> [areas]
        claims: dict[str, dict[str, list[str]]] = {}
        shared: dict[str, dict[str, list[str]]] = {}

        def claim(group: str, value: str, area: str) -> None:
            claims.setdefault(group, {}).setdefault(value, [])
            if area not in claims[group][value]:
                claims[group][value].append(area)

        for area, d in decisions.items():
            sd = d["spec"]["stages"].get(stage)
            if not sd:
                continue
            for c in sd.get("choice") or []:
                for group, members in EXCLUSIVE_GROUPS.items():
                    if c in members:
                        claim(group, c, area)
                if c.startswith("apps/cdc/"):
                    for suffix, broker in CDC_BROKER.items():
                        if c.endswith(suffix):
                            claim("broker", broker, f"{area} (via {c})")
            settings = sd.get("settings") or {}
            for key, (group, mapping) in SETTING_TO_GROUP.items():
                v = str(settings.get(key, "")).lower()
                if v in mapping:
                    claim(group, mapping[v], area)
            for key in SHARED_SETTINGS:
                if key in settings and settings[key] not in (None, ""):
                    shared.setdefault(key, {}).setdefault(str(settings[key]), [])
                    if area not in shared[key][str(settings[key])]:
                        shared[key][str(settings[key])].append(area)

        for group, by_value in claims.items():
            if len(by_value) < 2:
                continue
            sides = "; ".join(f"{', '.join(areas)} → {v}" for v, areas in by_value.items())
            msg = f"cross-record conflict ({stage}, {group}): {sides}"
            ack = _acknowledged(decisions, list(by_value))
            if ack:
                warnings.append(f"{msg}; acknowledged by open question {ack}, resolve with the user")
            else:
                errors.append(f"{msg}; raise an open question naming both in one of the records, do not resolve it silently")
        for key, by_value in shared.items():
            if len(by_value) < 2:
                continue
            sides = "; ".join(f"{', '.join(areas)} → {v}" for v, areas in by_value.items())
            msg = f"cross-record conflict ({stage}, setting {key}): {sides}"
            ack = _acknowledged(decisions, list(by_value))
            if ack:
                warnings.append(f"{msg}; acknowledged by open question {ack}, resolve with the user")
            else:
                errors.append(f"{msg}; raise an open question naming both values in one of the records, do not resolve it silently")
        # A CDC connector without its broker anywhere is a gap, not a conflict.
        for area, d in decisions.items():
            sd = d["spec"]["stages"].get(stage) or {}
            for c in sd.get("choice") or []:
                if c.startswith("apps/cdc/"):
                    needed = next((b for suf, b in CDC_BROKER.items() if c.endswith(suf)), None)
                    present = any(needed in (dd["spec"]["stages"].get(stage) or {}).get("choice", []) for dd in decisions.values())
                    if needed and not present:
                        warnings.append(f"{area}: {stage}: {c} needs {needed} in some record's choice for the same stage")
    return errors, warnings


def validate_usecase(uc: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    b = uc / ".builder"
    if not b.is_dir():
        return [f"{uc}: no .builder/ directory"], []

    def load(name: str, schema: str, required: bool) -> dict | None:
        p = b / name
        if not p.is_file():
            if required:
                errors.append(f"{p}: missing")
            return None
        data = load_yaml(p)
        errors.extend(schema_errors(schema, data, str(p)))
        return data

    brief = load("brief.yaml", "brief", required=True)
    plan = load("stage-plan.yaml", "stage-plan", required=False)
    gates = load("gates.yaml", "gates", required=False)
    packs_doc = load("packs.yaml", "packs-active", required=False)

    uc_name = uc.name
    if brief and brief["metadata"]["name"] != uc_name:
        errors.append(f"{b/'brief.yaml'}: metadata.name '{brief['metadata']['name']}' != directory '{uc_name}'")
    data_class = (brief or {}).get("spec", {}).get("data", {}).get("classification", "none")

    rules: dict[str, dict] = {}
    if packs_doc:
        try:
            rules, errs = load_rules(active_packs(b / "packs.yaml"))
            errors += errs
        except BuilderError as exc:
            errors.append(str(exc))

    skipped = set()
    planned_experts: dict[str, bool] = {}
    if plan:
        skipped = {s for s, v in plan["spec"]["stages"].items() if not v["in_scope"]}
        skipped |= {s for s in STAGES if s not in plan["spec"]["stages"]}
        planned_experts = {e["role"]: e["run"] for e in plan["spec"]["experts"]}

    found_areas = set()
    decisions: dict[str, dict] = {}
    for dpath in sorted((b / "decisions").glob("*.yaml")) if (b / "decisions").is_dir() else []:
        d = load_yaml(dpath)
        errs = schema_errors("decision", d, str(dpath))
        errors += errs
        if errs:
            continue
        area = d["metadata"]["area"]
        found_areas.add(area)
        decisions[area] = d
        if dpath.stem != area:
            errors.append(f"{dpath}: file name should be {area}.yaml")
        if d["metadata"]["usecase"] != uc_name:
            errors.append(f"{dpath}: metadata.usecase != '{uc_name}'")

        for q in d["spec"].get("open_questions", []):
            if q.get("caused_by_rule") and q["caused_by_rule"] not in rules:
                errors.append(f"{dpath}: open question {q['id']} cites unknown rule {q['caused_by_rule']}")

        for stage, sd in d["spec"]["stages"].items():
            if stage in skipped:
                warnings.append(f"{dpath}: decides for stage '{stage}' which the plan skipped")
            for c in sd.get("choice", []):
                if not component_exists(c):
                    errors.append(f"{dpath}: {stage}: component not in catalog: {c}")
            for ref in sd.get("constrained_by", []):
                if ref not in rules:
                    errors.append(f"{dpath}: {stage}: constrained_by cites unknown rule {ref}")
            for ref, entry in rules.items():
                msg = check_rule(ref, entry, area, stage, sd, data_class)
                if msg:
                    errors.append(f"{dpath}: {stage}: {msg}")

    c_errs, c_warns = cross_record_conflicts(decisions)
    errors += [f"{uc}: {e}" for e in c_errs]
    warnings += [f"{uc}: {w}" for w in c_warns]

    for role, run in planned_experts.items():
        if run and role not in found_areas:
            warnings.append(f"{uc}: plan runs expert '{role}' but decisions/{role}.yaml is missing")
        if not run and role in found_areas:
            warnings.append(f"{uc}: plan skips expert '{role}' but decisions/{role}.yaml exists")

    if gates:
        for ov in gates["spec"].get("pack_overrides", []):
            if ov["rule"] not in rules:
                errors.append(f"{b/'gates.yaml'}: pack_overrides cites unknown rule {ov['rule']}")
    return errors, warnings


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    all_errors: list[str] = []
    all_warnings: list[str] = []
    for arg in argv:
        uc = Path(arg).resolve()
        try:
            errs, warns = validate_usecase(uc)
        except BuilderError as exc:
            errs, warns = [str(exc)], []
        all_errors += errs
        all_warnings += warns
        print(f"{'FAIL' if errs else 'ok  '} {uc.name}  ({len(errs)} error(s), {len(warns)} warning(s))")
    return report(all_errors, all_warnings)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BuilderError as exc:
        die(str(exc))
