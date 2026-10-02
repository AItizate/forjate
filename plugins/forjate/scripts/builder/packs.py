#!/usr/bin/env python3
"""Context-pack resolver: the one interface every forjate skill uses to receive
external guidelines (corporate policies, tool-development standards, user rules).

    packs.py lint <pack-dir>...
        Validate a pack's manifest, constraints and referenced files.

    packs.py resolve --for <role> [--usecase-dir <dir> | --packs <packs.yaml>]
        Merge every active pack, keep only the sources that apply to <role>,
        order by precedence, inline the structured rules, and print a compact
        YAML document the skill pastes into its context. Conflicts between
        packs on the same rule type/target are resolved highest-precedence
        wins and listed under `overrides` so nothing is silently dropped.

Packs can be local directories or git URLs with ?ref=, the same syntax used for
remote components. Remote packs are cloned once into ~/.cache/forjate/packs/.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from common import (
    BuilderError, ENFORCE_RANK, REPO, ROLES, component_exists, die, load_yaml, report,
    schema_errors,
)

CACHE = Path(os.environ.get("FORJATE_PACK_CACHE", Path.home() / ".cache" / "forjate" / "packs"))
GIT_URL_RE = re.compile(r"^(?P<url>(ssh://|https?://|git@)[^?]+?)(//(?P<sub>[^?]+))?(\?ref=(?P<ref>.+))?$")
RULE_REF_RE = re.compile(r"^constraints\.yaml#/rules/(?P<id>[A-Z][A-Z0-9]*-[0-9]+)$")

# Rule types where two packs setting the same (type, target) conflict.
EXCLUSIVE_TYPES = {
    "min_psa_level", "secrets_mechanism", "data_egress", "data_residency",
    "max_cost_usd_month", "naming_pattern", "require_setting",
}


# --------------------------------------------------------------------------- load

def locate(source: str, ref: str | None = None) -> Path:
    """Turn a pack source (local path or git URL) into a directory on disk."""
    m = GIT_URL_RE.match(source)
    if not m or not source.startswith(("ssh://", "http://", "https://", "git@")):
        p = Path(source)
        if not p.is_absolute():
            p = REPO / p
        if not p.is_dir():
            raise BuilderError(f"pack source not found: {source}")
        return p
    url, sub, ref = m.group("url"), m.group("sub"), m.group("ref") or ref
    if not ref:
        raise BuilderError(f"remote pack must be pinned with ?ref=: {source}")
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")
    target = CACHE / f"{slug}@{ref}"
    if not target.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", "--branch", ref, url, str(target)],
            check=True,
        )
    return target / sub if sub else target


def load_pack(pack_dir: Path) -> tuple[dict, dict | None, list[str]]:
    """Load pack.yaml (+ constraints.yaml if present). Returns (manifest, constraints, errors)."""
    errors: list[str] = []
    manifest_path = pack_dir / "pack.yaml"
    if not manifest_path.is_file():
        return {}, None, [f"{pack_dir}: missing pack.yaml"]
    manifest = load_yaml(manifest_path)
    errors += schema_errors("pack", manifest, str(manifest_path))

    constraints = None
    cpath = pack_dir / "constraints.yaml"
    if cpath.is_file():
        constraints = load_yaml(cpath)
        errors += schema_errors("constraints", constraints, str(cpath))
        for rid, rule in (constraints.get("rules") or {}).items():
            if rule.get("type") in {"deny_components", "allow_components_only", "require_components"}:
                for c in rule.get("value", []):
                    if not component_exists(c):
                        errors.append(f"{cpath}: rule {rid}: component not in catalog: {c}")

    for src in manifest.get("spec", {}).get("sources", []):
        path = src.get("path", "")
        if src.get("kind") == "constraint":
            m = RULE_REF_RE.match(path)
            if not m:
                errors.append(f"{manifest_path}: source {src.get('id')}: constraint path must be constraints.yaml#/rules/<ID>")
            elif constraints is None or m.group("id") not in (constraints.get("rules") or {}):
                errors.append(f"{manifest_path}: source {src.get('id')}: rule {path} not found in constraints.yaml")
            elif m.group("id") != src.get("id"):
                errors.append(f"{manifest_path}: source id {src.get('id')} must equal rule id {m.group('id')}")
        else:
            if not (pack_dir / path).is_file():
                errors.append(f"{manifest_path}: source {src.get('id')}: file not found: {path}")
    return manifest, constraints, errors


def active_packs(packs_file: Path) -> list[tuple[str, Path]]:
    data = load_yaml(packs_file)
    errs = schema_errors("packs-active", data, str(packs_file))
    if errs:
        raise BuilderError("\n".join(errs))
    out = []
    for p in data["spec"]["packs"]:
        out.append((p["name"], locate(p["source"], p.get("ref"))))
    return out


# ------------------------------------------------------------------------ resolve

def applies(applies_to: list[str] | None, role: str) -> bool:
    if not applies_to:
        return True
    return "*" in applies_to or role in applies_to


def resolve(role: str, packs: list[tuple[str, Path]]) -> dict:
    if role not in ROLES:
        raise BuilderError(f"unknown role '{role}'. Known: {', '.join(ROLES)}")
    entries: list[dict] = []
    errors: list[str] = []
    for declared_name, pack_dir in packs:
        manifest, constraints, errs = load_pack(pack_dir)
        errors += errs
        if errs:
            continue
        meta, spec = manifest["metadata"], manifest["spec"]
        if meta["name"] != declared_name:
            errors.append(f"{pack_dir}: packs.yaml calls it '{declared_name}' but pack.yaml says '{meta['name']}'")
            continue
        if not applies(spec["applies_to"], role):
            continue
        for src in spec["sources"]:
            if not applies(src.get("applies_to"), role):
                continue
            entry = {
                "ref": f"pack:{meta['name']}#{src['id']}",
                "pack": meta["name"],
                "version": meta["version"],
                "scope": meta["scope"],
                "precedence": meta["precedence"],
                "kind": src["kind"],
                "enforce": src["enforce"],
            }
            if src.get("summary"):
                entry["summary"] = src["summary"]
            if src["kind"] == "constraint":
                rid = RULE_REF_RE.match(src["path"]).group("id")
                entry["rule"] = constraints["rules"][rid]
            else:
                entry["path"] = str(pack_dir / src["path"])
            entries.append(entry)
    if errors:
        raise BuilderError("\n".join(errors))

    entries.sort(key=lambda e: (-e["precedence"], -ENFORCE_RANK[e["enforce"]], e["ref"]))

    # Conflict resolution on exclusive rule types: first (highest precedence) wins.
    winners: dict[tuple, dict] = {}
    overrides: list[dict] = []
    kept: list[dict] = []
    for e in entries:
        rule = e.get("rule")
        if rule and rule["type"] in EXCLUSIVE_TYPES:
            key = (rule["type"], rule.get("target"), tuple(rule.get("stages") or ()))
            if key in winners:
                w = winners[key]
                overrides.append({
                    "rule": e["ref"], "enforce": e["enforce"],
                    "overridden_by": w["ref"],
                    "note": "a lower-precedence must was overridden" if e["enforce"] == "must" else "superseded",
                })
                continue
            winners[key] = e
        kept.append(e)

    return {
        "apiVersion": "forjate.io/v0",
        "kind": "ResolvedContext",
        "for": role,
        "packs": [{"name": n, "dir": str(d)} for n, d in packs],
        "entries": kept,
        "overrides": overrides,
        "how_to_apply": (
            "must: hard constraint, never violate; if you cannot satisfy it raise an open_question "
            "citing the ref. should: the default; deviate only with an explicit rationale. "
            "may: a suggestion. Cite every ref that shaped a choice in constrained_by. "
            "Open guideline paths only when their summary is relevant to the decision at hand."
        ),
    }


# ---------------------------------------------------------------------------- cli

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    lint = sub.add_parser("lint", help="validate one or more pack directories")
    lint.add_argument("packs", nargs="+", type=Path)

    res = sub.add_parser("resolve", help="print the resolved context for one role")
    res.add_argument("--for", dest="role", required=True, choices=ROLES)
    g = res.add_mutually_exclusive_group()
    g.add_argument("--usecase-dir", type=Path, help="reads <dir>/.builder/packs.yaml")
    g.add_argument("--packs", type=Path, help="an ActivePacks yaml file")
    res.add_argument("--pack-dir", type=Path, action="append", default=[],
                     help="ad-hoc local pack(s), used when no packs.yaml is given")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "lint":
            errors: list[str] = []
            for p in args.packs:
                _, _, errs = load_pack(p.resolve())
                errors += errs
                if not errs:
                    print(f"ok {p}")
            return report(errors)

        if args.usecase_dir:
            packs = active_packs(args.usecase_dir / ".builder" / "packs.yaml")
        elif args.packs:
            packs = active_packs(args.packs)
        else:
            packs = []
            for d in args.pack_dir:
                manifest, _, errs = load_pack(d.resolve())
                if errs:
                    raise BuilderError("\n".join(errs))
                packs.append((manifest["metadata"]["name"], d.resolve()))
        print(yaml.safe_dump(resolve(args.role, packs), sort_keys=False, width=100))
        return 0
    except BuilderError as exc:
        die(str(exc))
        return 2


if __name__ == "__main__":
    sys.exit(main())
