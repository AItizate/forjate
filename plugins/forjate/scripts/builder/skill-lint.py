#!/usr/bin/env python3
"""Flag catalog component paths hard-coded in the builder's skills.

    skill-lint.py [--strict] [--skills <name> ...]

A skill that says "Walk → apps/sealed-secrets" keeps a better component from ever
being chosen; the catalog owns the capability→component mapping and a generated
references/catalog-snapshot.md per skill shows what it resolves today. This lint
reads every SKILL.md and references/*.md of plugins/forjate/skills/ except the
snapshots and reports each exact catalog path it finds, with two allowances:

  - a component that is the single option for one of its capabilities (prose may
    name it: there is nothing to choose), and
  - a line that ends with `<!-- skill-lint: allow -->` (a rule of judgement that
    uses a component as an illustration, or a path in a command example).

Names in prose ("Postgres", "Redis") are not flagged: the plan protects rules of
judgement that use a component as an illustration; stage→component tables, which
always use paths, are the target.

Exit 0 and a report by default (warn mode, what CI runs); --strict exits 1 when
anything is flagged.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent.parent
SKILLS = PLUGIN / "skills"
REPO = PLUGIN.parent.parent
CATALOG = REPO / "wiki" / "catalog.json"
SNAPSHOT_NAME = "catalog-snapshot.md"
ALLOW_MARK = "<!-- skill-lint: allow -->"


def load_catalog() -> dict:
    if not CATALOG.is_file():
        sys.exit(f"error: {CATALOG} missing; run scripts/wiki-compile.py")
    return json.loads(CATALOG.read_text())


def single_option_components(catalog: dict) -> set[str]:
    """Components that are the only choosable option for at least one of their capabilities."""
    by_cap: dict[str, list[str]] = {}
    for c in catalog["components"]:
        if not c.get("stages"):
            continue
        for cap in c.get("capabilities") or []:
            by_cap.setdefault(cap, []).append(c["path"])
    return {paths[0] for paths in by_cap.values() if len(paths) == 1}


def path_pattern(paths: list[str]) -> re.Pattern:
    # Longest first so apps/minio/single-server wins over a hypothetical apps/minio.
    alts = "|".join(re.escape(p) for p in sorted(paths, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9_/.-])(?:{alts})(?![A-Za-z0-9_/-])")


def lint_skill(skill_dir: Path, pattern: re.Pattern, allowed: set[str]) -> tuple[list[tuple[str, int, str, str]], int]:
    """(file, line, component, text) per hit; count of hits skipped as single-option or allowed."""
    hits, skipped = [], 0
    files = [skill_dir / "SKILL.md"] + sorted((skill_dir / "references").glob("*.md")) if (skill_dir / "references").is_dir() else [skill_dir / "SKILL.md"]
    for f in files:
        if not f.is_file() or f.name == SNAPSHOT_NAME:
            continue
        for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            found = pattern.findall(line)
            if not found:
                continue
            if line.rstrip().endswith(ALLOW_MARK):
                skipped += len(found)
                continue
            for comp in found:
                if comp in allowed:
                    skipped += 1
                else:
                    hits.append((f.relative_to(skill_dir).as_posix(), n, comp, line.strip()))
    return hits, skipped


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true", help="exit 1 when any component path is flagged")
    ap.add_argument("--skills", nargs="*", help="only these skills (default: all)")
    ap.add_argument("--quiet", action="store_true", help="totals per skill only, no lines")
    args = ap.parse_args(argv)

    catalog = load_catalog()
    paths = [c["path"] for c in catalog["components"]]
    allowed = single_option_components(catalog)
    pattern = path_pattern(paths)

    skills = sorted(d for d in SKILLS.iterdir() if (d / "SKILL.md").is_file())
    if args.skills:
        skills = [d for d in skills if d.name in set(args.skills)]
    total = 0
    print("| Skill | Flagged | Allowed (single option or marked) | Components named |")
    print("|-------|---------|-----------------------------------|------------------|")
    details = []
    for d in skills:
        hits, skipped = lint_skill(d, pattern, allowed)
        total += len(hits)
        comps = sorted({h[2].rsplit('/', 1)[-1] for h in hits})
        print(f"| {d.name} | {len(hits)} | {skipped} | {', '.join(comps) or '—'} |")
        details += [(d.name, *h) for h in hits]
    if details and not args.quiet:
        print()
        for skill, f, n, comp, text in details:
            print(f"{skill}/{f}:{n}: {comp}: {text[:120]}")
    print()
    verdict = "ok" if total == 0 else f"{total} component path(s) named outside snapshots"
    print(f"skill-lint: {verdict} ({'strict' if args.strict else 'warn'} mode)")
    return 1 if (total and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
