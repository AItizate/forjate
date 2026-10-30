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
     same stage (NATS vs RabbitMQ, LanceDB vs Milvus, Ollama vs vLLM, Sealed Secrets vs
     External Secrets, ...), disagree on a shared setting (broker, psa_level,
     secrets_mechanism, data_residency, data_egress, network_policy, backup,
     auth_in_front) or claim one gate id with different texts are a conflict. A conflict
     is an error unless a record acknowledges it with an open question that names both
     sides; the validator never picks a winner.
  7. gates consolidation: when gates.yaml exists, every gate a record emits for a stage
     with a transition out of it appears under that transition (warning), and every
     pack override it lists cites a rule of an active pack (error).
  8. ci refs: a `ci` gate's check.ref names a script in scripts/gates/checks/ (the
     directory is the enum). Error in gates.yaml, warning in a record's gate_to_next;
     skipped with a warning when no checks directory is reachable (a tenant repo
     without the factory checkout; set FORJATE_ROOT to point at one).
  9. PSA exceptions: the security record's `psa_exceptions` never name the use case's
     namespace (error), list catalog components (error) that some record runs at that
     stage, and sit below the stage's `psa_level` (warning otherwise). A shared component
     whose namespace runs below the stage's level, or, at `restricted`, a use-case-scoped
     component the catalog does not prove under `restricted`, with no exception is a
     warning: what runs at a stage is every record's choices up to it, because stage
     overlays add and never remove.

Exit 1 on any error. Warnings never fail the run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from common import (BuilderError, PSA_RANK, REPO, STAGES, component_exists, die, load_catalog, load_yaml, report,
                    schema_errors)
from packs import active_packs, load_pack, RULE_REF_RE

RULE_REF = re.compile(r"^pack:(?P<pack>[a-z0-9-]+)#(?P<id>[A-Z][A-Z0-9]*-[0-9]+)$")


def checks_dir() -> Path | None:
    """scripts/gates/checks/ of the factory: the enum of `ci` gate refs."""
    import os
    for root in (Path(os.environ["FORJATE_ROOT"]) if os.environ.get("FORJATE_ROOT") else None, REPO,
                 Path(__file__).resolve().parents[4]):
        if root and (root / "scripts" / "gates" / "checks").is_dir():
            return root / "scripts" / "gates" / "checks"
    return None


def ci_ref_errors(gates: list[dict], where: str) -> list[str]:
    d = checks_dir()
    if d is None:
        return []
    out = []
    for g in gates:
        c = g.get("check") or {}
        if c.get("type") == "ci":
            ref = str(c.get("ref") or "")
            if not ref or not (d / f"{ref}.sh").is_file():
                out.append(f"{where}: gate {g.get('id')} has ci ref '{ref}' with no script scripts/gates/checks/{ref}.sh (the directory is the enum)")
    return out

# Cross-record consistency (check 6) and the secrets ladder (check 4) are read from the
# catalog, not from tables in this file: a capability marked `exclusive` in
# wiki/catalog-capabilities.yaml is a group of mutually exclusive components, its
# `setting` names the record key whose value picks one of them (by component name, or
# by secrets.mechanism), and secrets-mechanism components carry their rank. A better
# component added to the catalog is ranked and grouped without touching the validator.
SECRETS_CAPABILITY = "secrets-mechanism"
# Settings two experts both emit and must agree on per stage (contracts.md lists the owners):
# security/devops share the hardening keys, data-store/devops the backup ladder,
# architecture/security the auth surface, and three experts the egress and residency facts.
SHARED_SETTINGS = ("psa_level", "secrets_mechanism", "data_residency", "data_egress",
                   "network_policy", "backup", "auth_in_front")
TRANSITION_OUT_OF = {"crawl": "crawl->walk", "walk": "walk->run"}
# A CDC connector (the catalog's `cdc` capability) is named debezium-<source>-<broker>; its suffix
# implies a message-broker choice.
CDC_CAPABILITY = "cdc"


class CatalogRules:
    """Exclusive groups, setting→component maps and the secrets ranking, derived from wiki/catalog.json."""

    def __init__(self, catalog: dict | None):
        self.available = catalog is not None
        self.groups: dict[str, set[str]] = {}
        self.cdc: set[str] = set()
        self.setting_to_group: dict[str, tuple[str, dict[str, str]]] = {}
        self.secrets_rank: dict[str, int] = {}
        if catalog is None:
            return
        caps = catalog.get("capabilities") or {}
        comps = catalog.get("components") or []
        self.cdc = {c["path"] for c in comps if CDC_CAPABILITY in (c.get("capabilities") or [])}
        for name, cap in caps.items():
            if not cap.get("exclusive"):
                continue
            members = [c for c in comps if name in (c.get("capabilities") or [])]
            self.groups[name] = {c["path"] for c in members}
            if cap.get("setting"):
                by_value = {}
                for c in members:
                    mech = (c.get("secrets") or {}).get("mechanism")
                    by_value[mech or c["path"].rsplit("/", 1)[-1]] = c["path"]
                # The floor (secret-generator) has no component: it maps to nothing and conflicts with nothing.
                self.setting_to_group[cap["setting"]] = (name, by_value)
            if name == SECRETS_CAPABILITY:
                if cap.get("floor"):
                    self.secrets_rank[cap["floor"]] = 0
                for c in members:
                    s = c.get("secrets") or {}
                    if s.get("mechanism") and isinstance(s.get("rank"), int):
                        self.secrets_rank[s["mechanism"]] = s["rank"]


_RULES: CatalogRules | None = None


def catalog_rules() -> CatalogRules:
    global _RULES
    if _RULES is None:
        _RULES = CatalogRules(load_catalog())
    return _RULES


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
        rank = catalog_rules().secrets_rank
        if not rank:
            return None  # no catalog reachable; validate_usecase warns once
        if v not in rank:
            return f"rule requires secrets_mechanism '{v}', which no catalog component provides ({ref})"
        if rank.get(str(settings["secrets_mechanism"]), -1) < rank[v]:
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
            rules_from_catalog = catalog_rules()
            for c in sd.get("choice") or []:
                for group, members in rules_from_catalog.groups.items():
                    if c in members:
                        claim(group, c, area)
                if c in rules_from_catalog.cdc and "broker" in rules_from_catalog.setting_to_group:
                    group, by_name = rules_from_catalog.setting_to_group["broker"]
                    implied = by_name.get(c.rsplit("-", 1)[-1])
                    if implied:
                        claim(group, implied, f"{area} (via {c})")
            settings = sd.get("settings") or {}
            for key, (group, mapping) in rules_from_catalog.setting_to_group.items():
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
                if c in rules_from_catalog.cdc and "broker" in rules_from_catalog.setting_to_group:
                    needed = rules_from_catalog.setting_to_group["broker"][1].get(c.rsplit("-", 1)[-1])
                    present = any(needed in (dd["spec"]["stages"].get(stage) or {}).get("choice", []) for dd in decisions.values())
                    if needed and not present:
                        warnings.append(f"{area}: {stage}: {c} needs {needed} in some record's choice for the same stage")
    # One gate id, two texts: the consolidation would have to pick one, and it must not.
    gate_texts: dict[str, dict[str, list[str]]] = {}
    for area, d in decisions.items():
        for sd in d["spec"]["stages"].values():
            for g in sd.get("gate_to_next") or []:
                gate_texts.setdefault(g["id"], {}).setdefault(" ".join(str(g.get("text", "")).split()), [])
                if area not in gate_texts[g["id"]][" ".join(str(g.get("text", "")).split())]:
                    gate_texts[g["id"]][" ".join(str(g.get("text", "")).split())].append(area)
    for gid, by_text in gate_texts.items():
        if len(by_text) < 2:
            continue
        areas = sorted({a for aa in by_text.values() for a in aa})
        sides = "; ".join(f"{', '.join(aa)} → \"{t[:60]}\"" for t, aa in by_text.items())
        msg = f"cross-record conflict (gate {gid}): {sides}"
        ack = _acknowledged(decisions, [gid] + areas)
        if ack:
            warnings.append(f"{msg}; acknowledged by open question {ack}, resolve with the authors")
        else:
            errors.append(f"{msg}; one gate id, one text: raise an open question naming the id and both records, do not merge the texts")
    return errors, warnings


def psa_exception_findings(uc_name: str, decisions: dict[str, dict], where: str) -> tuple[list[str], list[str]]:
    """Check 9: the security record's psa_exceptions against the stage level and the catalog.

    Where a component runs and the level its pods meet are catalog facts (`namespace`,
    `psa_level` in wiki/catalog.json, derived from k8s/** by wiki-compile.py); nothing here
    names a component. A shared component (one with a `namespace`) runs there; the rest run
    in the use case's namespace unless an exception moves them. `unknown` counts as below
    any enforced level, `n/a` (no pods) never needs an exception."""
    errors: list[str] = []
    warnings: list[str] = []
    sec = decisions.get("security")
    catalog = load_catalog()
    if not sec or catalog is None:
        return errors, warnings
    facts = {c["path"]: c for c in catalog.get("components") or []}
    uc_ns = f"uc-{uc_name}"

    def rank(level) -> int:
        return PSA_RANK.get(str(level), -1)

    runs: dict[str, list[str]] = {}
    seen: list[str] = []
    for s in STAGES:
        for d in decisions.values():
            for c in (d["spec"]["stages"].get(s) or {}).get("choice") or []:
                if c not in seen:
                    seen.append(c)
        runs[s] = list(seen)
    for stage, sd in sec["spec"]["stages"].items():
        level = str((sd.get("settings") or {}).get("psa_level") or "")
        covered: set[str] = set()
        for e in sd.get("psa_exceptions") or []:
            at = f"{where}: {stage}: psa_exceptions {e['namespace']}"
            if e["namespace"] == uc_ns:
                errors.append(f"{at}: an exception never lowers the use case's namespace; move the components to a namespace of their own")
            if level in PSA_RANK and PSA_RANK[e["level"]] >= PSA_RANK[level]:
                warnings.append(f"{at}: level {e['level']} is not below the stage's psa_level {level}, so it is not an exception")
            for c in e["components"]:
                covered.add(c)
                if not component_exists(c):
                    errors.append(f"{at}: component not in catalog: {c}")
                    continue
                if c not in runs.get(stage, []):
                    warnings.append(f"{at}: {c} is not chosen by any record at {stage} or before")
                home = (facts.get(c) or {}).get("namespace")
                if home and home != e["namespace"]:
                    warnings.append(f"{at}: the catalog runs {c} in {home}, not {e['namespace']}")
        if rank(level) <= 0:
            continue
        shared: dict[str, list[tuple[str, str]]] = {}
        unproven: list[str] = []
        for c in runs.get(stage, []):
            f = facts.get(c) or {}
            lvl = f.get("psa_level", "unknown")
            if c in covered or lvl == "n/a" or rank(lvl) >= rank(level):
                continue
            if f.get("namespace"):
                shared.setdefault(f["namespace"], []).append((c, lvl))
            else:
                unproven.append(f"{c} ({lvl})")
        for ns, comps in shared.items():
            warnings.append(f"{where}: {stage}: {ns} needs a level below psa_level {level} and has no psa_exceptions entry: "
                            + ", ".join(f"{c} ({lvl})" for c, lvl in comps))
        if unproven:
            warnings.append(f"{where}: {stage}: below psa_level {level} in the catalog (psa_level) and would run in {uc_ns}: "
                            f"{', '.join(unproven)}; move them to a namespace of their own with a psa_exceptions entry, or choose candidates that meet it")
    return errors, warnings


def gates_consolidation(decisions: dict[str, dict], gates: dict, skipped: set[str]) -> list[str]:
    """Check 7. Every record gate for a stage with a transition out of it is in gates.yaml."""
    warnings: list[str] = []
    transitions = gates["spec"].get("transitions") or {}
    for area, d in decisions.items():
        for stage, sd in d["spec"]["stages"].items():
            tr = TRANSITION_OUT_OF.get(stage)
            if not tr:
                continue
            target = tr.split("->")[1]
            if target in skipped:
                continue
            present = {g["id"] for g in (transitions.get(tr) or {}).get("gates") or []}
            for g in sd.get("gate_to_next") or []:
                if g["id"] not in present:
                    warnings.append(f"gates.yaml: {tr} lacks {g['id']} from decisions/{area}.yaml; re-run the quality expert in consolidate mode")
    return warnings


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
            warnings += ci_ref_errors(sd.get("gate_to_next") or [], f"{dpath}: {stage}")
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
    p_errs, p_warns = psa_exception_findings(uc_name, decisions, str(b / "decisions" / "security.yaml"))
    errors += p_errs
    warnings += p_warns

    for role, run in planned_experts.items():
        if run and role not in found_areas:
            warnings.append(f"{uc}: plan runs expert '{role}' but decisions/{role}.yaml is missing")
        if not run and role in found_areas:
            warnings.append(f"{uc}: plan skips expert '{role}' but decisions/{role}.yaml exists")

    if gates:
        for ov in gates["spec"].get("pack_overrides", []):
            if ov["rule"] not in rules:
                errors.append(f"{b/'gates.yaml'}: pack_overrides cites unknown rule {ov['rule']}")
        if gates["metadata"]["usecase"] != uc_name:
            errors.append(f"{b/'gates.yaml'}: metadata.usecase != '{uc_name}'")
        if checks_dir() is None:
            warnings.append(f"{b/'gates.yaml'}: ci refs not checked (no scripts/gates/checks/ reachable; set FORJATE_ROOT)")
        for tr, body in gates["spec"]["transitions"].items():
            errors += ci_ref_errors(body.get("gates") or [], f"{b/'gates.yaml'}: {tr}")
        warnings += [f"{uc}: {w}" for w in gates_consolidation(decisions, gates, skipped)]
    if not catalog_rules().available:
        warnings.append(f"{uc}: wiki/catalog.json not reachable (set FORJATE_ROOT); secrets ranking and exclusive-component conflicts not checked")
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
