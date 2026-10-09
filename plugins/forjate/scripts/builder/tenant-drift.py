#!/usr/bin/env python3
"""Compare a tenant repository's CLAUDE.md with its k8s/ tree and list the drift.

    tenant-drift.py <repo-dir> [--json]

A real tenant's CLAUDE.md described a gitops/{production,testing}/<app>.yaml tree that did not exist
(docs/use-case-builder/tenant-patterns.md). Before the coordinator's review mode trusts either, it lists:

  documented-missing   paths the CLAUDE.md names (in code blocks, tables or inline) that do not exist
  undocumented         top-level directories under k8s/ (and namespaces/<ns>) the CLAUDE.md never mentions
  dead-directories     namespaces/<ns> directories the root kustomization.yaml does not reference
  branch-refs          remote ?ref= values that are branches, not tags or commits

Exit 0 always (it is a report); --json for the coordinator.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PATH_RE = re.compile(r"(?<![\w/.-])((?:k8s|gitops|argocd|scripts|\.github|docs|namespaces|overlays|components|base)(?:/[\w.@{}, -]+)+/?)")
REF_RE = re.compile(r"\?ref=([^\s\"'#)]+)")
TAG_RE = re.compile(r"^v?\d+\.\d+(\.\d+)?([-+.][A-Za-z0-9.-]+)?$|^[0-9a-f]{7,40}$")


def documented_paths(text: str) -> set[str]:
    out: set[str] = set()
    for m in PATH_RE.finditer(text):
        p = m.group(1).rstrip("/").strip()
        # expand {a,b} alternatives the way a shell would
        alts = re.search(r"\{([^}]+)\}", p)
        if alts:
            for a in alts.group(1).split(","):
                out.add(p.replace(alts.group(0), a.strip()))
        else:
            out.add(p)
    # tree listings in code blocks: lines like "  namespaces/" or "├── patches/"
    stack: list[tuple[int, str]] = []
    for line in text.splitlines():
        m = re.match(r"^([\s│├└─|`-]*)([\w.@-]+/?)\s*(#.*)?$", line)
        if not m or not line.strip() or line.strip().startswith(("#", "```", "-", "*", "|")):
            continue
        indent = len(m.group(1).replace("│", " ").replace("├", " ").replace("└", " ").replace("─", " ").replace("|", " ").replace("`", " "))
        name = m.group(2)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        full = "/".join(n.rstrip("/") for _, n in stack) + ("/" if stack else "") + name.rstrip("/")
        stack.append((indent, name))
        if "/" in full and full.split("/")[0] in ("k8s", "gitops", "argocd", "scripts", ".github", "docs"):
            out.add(full)
    return {p for p in out if not p.startswith(("http", "ssh"))}


def drift(repo: Path) -> dict:
    claude = repo / "CLAUDE.md"
    report: dict[str, list[str]] = {"documented-missing": [], "undocumented": [], "dead-directories": [], "branch-refs": []}
    text = claude.read_text() if claude.is_file() else ""
    if not text:
        report["note"] = "no CLAUDE.md in the tenant repo"
    docs = documented_paths(text)
    for p in sorted(docs):
        clean = re.sub(r"<[^>]+>", "", p).rstrip("/")
        if "<" in p or "*" in p:
            parent = Path(clean).parent
            if not (repo / parent).exists():
                report["documented-missing"].append(p)
            continue
        if not (repo / clean).exists():
            report["documented-missing"].append(p)
    k8s = repo / "k8s"
    if k8s.is_dir():
        for d in sorted(x for x in k8s.iterdir() if x.is_dir() and not x.name.startswith(".")):
            if f"k8s/{d.name}" not in text and d.name not in text:
                report["undocumented"].append(f"k8s/{d.name}")
        ns_dir = k8s / "namespaces"
        root = k8s / "kustomization.yaml"
        root_text = root.read_text() if root.is_file() else ""
        if ns_dir.is_dir():
            for d in sorted(x for x in ns_dir.iterdir() if x.is_dir()):
                if f"namespaces/{d.name}" not in root_text:
                    report["dead-directories"].append(f"k8s/namespaces/{d.name}")
                if f"namespaces/{d.name}" not in text and d.name not in text:
                    report["undocumented"].append(f"k8s/namespaces/{d.name}")
        for f in sorted(k8s.rglob("kustomization.yaml")):
            for m in REF_RE.finditer(f.read_text()):
                if not TAG_RE.match(m.group(1)):
                    report["branch-refs"].append(f"{f.relative_to(repo)}: ?ref={m.group(1)}")
    else:
        report["note"] = (report.get("note", "") + "; " if report.get("note") else "") + "no k8s/ directory in the tenant repo"
    return report


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    repo = Path(args[0]).resolve()
    r = drift(repo)
    if "--json" in argv:
        print(json.dumps(r, indent=2))
        return 0
    print(f"# Drift between {repo}/CLAUDE.md and its tree")
    if r.get("note"):
        print(f"note: {r['note']}")
    for key in ("documented-missing", "undocumented", "dead-directories", "branch-refs"):
        items = r.get(key) or []
        print(f"\n## {key} ({len(items)})")
        for i in items:
            print(f"- {i}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
