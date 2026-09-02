#!/usr/bin/env python3
"""Health-check the Forjate wiki.

The lint pass of the LLM Wiki pattern, adapted for a source tree that mutates.
The check that matters most here is **drift**: a page whose sources in k8s/ were
committed after the page was last compiled is not merely stale, it states
outdated facts with the authority of a curated page.

Checks:
  drift          source path changed in git after the page's compiled_at
  missing        a kustomization exists in k8s/ with no page in the wiki
  dangling       a page whose source directory no longer exists
  broken-link    a markdown link to a wiki file that is not there
  orphan         a concept page nothing links to
  schema         frontmatter that violates wiki/SCHEMA.md

Usage:
    poetry run python scripts/wiki-lint.py [--strict]

    --strict   exit non-zero on any finding (default: only on drift/schema)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required. Run: poetry install")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wiki_compile_api import REPO, WIKI, discover, rel  # noqa: E402

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+\.md)\)")
HARD_FAIL = {"drift", "schema", "dangling"}


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def last_commit(rel_path: str) -> str | None:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", rel_path],
                             cwd=REPO, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def main() -> int:
    ap = argparse.ArgumentParser(description="Health-check the Forjate wiki")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero on any finding, not just hard failures")
    args = ap.parse_args()

    if not WIKI.is_dir():
        sys.exit("wiki/ does not exist. Run scripts/wiki-compile.py first.")

    findings: list[tuple[str, str]] = []
    pages = sorted(WIKI.rglob("*.md"))
    inbound: dict[str, int] = {}

    for page in pages:
        fm = frontmatter(page)
        rp = rel(page)
        kind = fm.get("kind")

        if page.name in {"SCHEMA.md", "log.md"}:
            continue

        if not fm:
            findings.append(("schema", f"{rp}: no frontmatter"))
            continue
        if not kind:
            findings.append(("schema", f"{rp}: frontmatter has no `kind`"))

        sources = fm.get("sources") or []
        if kind in {"component", "overlay", "base"} and not sources:
            findings.append(("schema", f"{rp}: kind={kind} requires `sources`"))
        if kind == "concept" and sources:
            findings.append((
                "schema",
                f"{rp}: a concept page must not claim `sources` "
                f"(it belongs under components/ or overlays/)",
            ))

        compiled_at = str(fm.get("compiled_at") or "")
        for s in sources:
            src_path = REPO / str(s)
            if not src_path.exists():
                findings.append(("dangling", f"{rp}: source `{s}` no longer exists "
                                             f"— mark the page kind: retired"))
                continue
            commit = last_commit(str(s))
            if commit and compiled_at and commit > compiled_at:
                findings.append(("drift", f"{rp}: `{s}` changed {commit}, "
                                          f"page compiled {compiled_at}"))

        for target in LINK_RE.findall(page.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://")):
                continue
            resolved = (page.parent / target).resolve()
            if WIKI in resolved.parents or resolved.parent == WIKI:
                if not resolved.exists():
                    findings.append(("broken-link", f"{rp}: → {target}"))
                else:
                    inbound[rel(resolved)] = inbound.get(rel(resolved), 0) + 1

    # Concept pages nobody links to are invisible to an agent walking the index.
    for page in sorted((WIKI / "concepts").glob("*.md")) if (WIKI / "concepts").is_dir() else []:
        if inbound.get(rel(page), 0) == 0:
            findings.append(("orphan", f"{rel(page)}: no inbound links"))

    # Anything in the tree the compiler would produce but that is not on disk.
    for p in discover():
        if not p.out.exists():
            findings.append(("missing", f"{rel(p.out)}: not compiled "
                                        f"(source {p.rel_source})"))

    if not findings:
        print(f"wiki-lint: clean ({len(pages)} pages checked)")
        return 0

    by_check: dict[str, list[str]] = {}
    for check, msg in findings:
        by_check.setdefault(check, []).append(msg)

    for check in sorted(by_check):
        msgs = by_check[check]
        print(f"\n{check} ({len(msgs)})")
        for m in msgs[:25]:
            print(f"  {m}")
        if len(msgs) > 25:
            print(f"  ... and {len(msgs) - 25} more")

    hard = sum(len(v) for k, v in by_check.items() if k in HARD_FAIL)
    print(f"\nwiki-lint: {len(findings)} finding(s), {hard} hard failure(s)")
    if hard or (args.strict and findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
