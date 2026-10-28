#!/usr/bin/env python3
"""Which ephemeral use cases a change affects.

Prints the CI plan for .github/workflows/validate-usecases.yml as JSON:

    {"usecases": ["openbao-secrets"], "runner": false}

A use case is affected when the diff touches its own directory, a path in its
spec.files, or any directory its kustomization pulls in, followed through
resources:, components:, transformers: and namespaces/ sub-kustomizations. That
graph is the one the wiki compiler computes, so no workflow lists paths by hand.

`runner` is true when the runner, its schema or its scaffolding template
changed: those can break every use case, so all of them run too.

Usage:
    affected.py --all                 every use case, runner included
    affected.py --base <git-ref>      what changed in <git-ref>...HEAD
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from wiki_compile_api import REPO, compile_pages, rel  # noqa: E402

import yaml  # noqa: E402  (the compiler already requires it)

USECASES = REPO / "k8s" / "overlays" / "usecases"

# A change under any of these can break every use case.
RUNNER = (
    "scripts/ephemeral",
    ".ait/templates/usecase",
    ".github/workflows/validate-usecases.yml",
    # The graph below comes from the compiler: if it changes, trust nothing.
    "scripts/wiki-compile.py",
    "scripts/wiki_compile_api.py",
)


def under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def usecases() -> list[Path]:
    return sorted(p.parent for p in USECASES.glob("*/usecase.yaml"))


def dependencies(uc: Path, pages: list) -> set[str]:
    """Repo paths whose change can change what this use case deploys or runs."""
    root = rel(uc)
    deps = {root}

    contract = yaml.safe_load((uc / "usecase.yaml").read_text(encoding="utf-8")) or {}
    for entry in (contract.get("spec") or {}).get("files") or []:
        deps.update(str(p).rstrip("/") for p in entry.get("paths") or [])

    by_source = {p.rel_source: p for p in pages}
    todo = [p for p in pages if under(p.rel_source, root)]
    seen: set[str] = set()
    while todo:
        page = todo.pop()
        if page.rel_source in seen:
            continue
        seen.add(page.rel_source)
        for ref in page.local_refs:
            deps.add(ref)
            if ref in by_source:
                todo.append(by_source[ref])
    return deps


def changed_files(base: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"],
                         cwd=REPO, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def main() -> int:
    ap = argparse.ArgumentParser(description="Plan the use-case CI run")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="run every use case")
    group.add_argument("--base", help="git ref to diff against (<base>...HEAD)")
    args = ap.parse_args()

    names = [uc.name for uc in usecases()]

    if args.all:
        print(json.dumps({"usecases": names, "runner": True}))
        return 0

    changed = changed_files(args.base)
    runner = [f for f in changed if any(under(f, p) for p in RUNNER)]
    if runner:
        print(f"runner: {runner[0]} changed, every use case runs", file=sys.stderr)
        print(json.dumps({"usecases": names, "runner": True}))
        return 0

    pages = compile_pages()
    selected = []
    for uc in usecases():
        deps = dependencies(uc, pages)
        hit = next((f for f in changed if any(under(f, d) for d in deps)), None)
        if hit:
            print(f"{uc.name}: {hit}", file=sys.stderr)
            selected.append(uc.name)
        else:
            print(f"{uc.name}: not affected", file=sys.stderr)

    print(json.dumps({"usecases": selected, "runner": False}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
