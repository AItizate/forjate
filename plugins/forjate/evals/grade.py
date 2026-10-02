#!/usr/bin/env python3
"""Grade eval runs against their assertions.

    grade.py <run-dir>                 one run (…/<eval>/<with|without>_skill) → grading.json
    grade.py --all <iteration-dir>     every run under it → grading.json each + benchmark.md

grading.json uses the field names the skill-creator viewer expects:
{"expectations": [{"text": ..., "passed": bool, "evidence": ...}], "pass_rate": float}
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
BUILDER = PLUGIN / "scripts" / "builder"


def sh(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def check(a: dict, repo: Path) -> tuple[bool, str]:
    t = a["type"]
    path = repo / a.get("path", "")
    if t == "file_exists":
        return path.exists(), f"{a['path']} {'exists' if path.exists() else 'missing'}"
    if t == "file_absent":
        return not path.exists(), f"{a['path']} {'exists' if path.exists() else 'absent'}"
    if t in {"grep", "not_grep"}:
        if not path.exists():
            return t == "not_grep", f"{a['path']} missing"
        files = sorted(f for f in path.rglob("*") if f.is_file()) if path.is_dir() else [path]
        text = "\n".join(f.read_text(errors="replace") for f in files)
        hit = re.search(a["pattern"], text, re.MULTILINE) is not None
        return (hit if t == "grep" else not hit), f"/{a['pattern']}/ {'matched' if hit else 'not found'} in {a['path']}"
    if t == "kustomize_builds":
        rc, out = sh(["kubectl", "kustomize", "--enable-helm", a["path"]], repo)
        return rc == 0, out[-400:] if rc else "builds"
    if t == "kubeconform":
        rc, out = sh(["bash", "-c", f"kubectl kustomize --enable-helm {a['path']} | kubeconform -strict -ignore-missing-schemas -summary -"], repo)
        return rc == 0, out[-400:]
    if t == "usecase_valid":
        rc, out = sh(["poetry", "run", "python", str(BUILDER / "validate.py"), a["path"]], repo)
        return rc == 0, out[-400:]
    if t == "pack_lint":
        rc, out = sh(["poetry", "run", "python", str(BUILDER / "packs.py"), "lint", a["path"]], repo)
        return rc == 0, out[-400:]
    if t == "yaml_path":
        rc, out = sh(["yq", "-r", a["query"], a["path"]], repo)
        return rc == 0 and out == str(a["equals"]), f"{a['query']} = {out!r}"
    if t == "components_in_catalog":
        rc, out = sh(["yq", "-r", ".spec.components[]", a["path"]], repo)
        if rc:
            return False, out[-200:]
        missing = [c for c in out.splitlines() if c and not (repo / "k8s/components" / c / "kustomization.yaml").exists()]
        return not missing, f"missing: {missing}" if missing else f"all {len(out.splitlines())} in catalog"
    if t == "git_unchanged":
        rc, out = sh(["git", "diff", "--quiet", "HEAD", "--", a["path"]], repo)
        return rc == 0, "unchanged" if rc == 0 else "modified"
    return False, f"unknown assertion type {t}"


def grade_run(run_dir: Path) -> dict:
    meta = json.loads((run_dir.parent / "eval_metadata.json").read_text())
    repo = run_dir / "repo"
    results = []
    for a in meta["assertions"]:
        try:
            ok, ev = check(a, repo)
        except Exception as exc:  # a broken assertion is a failed assertion, visibly
            ok, ev = False, f"grader error: {exc}"
        results.append({"text": a["text"], "passed": bool(ok), "evidence": ev})
    g = {"eval_name": meta["eval_name"], "run": run_dir.name, "expectations": results,
         "pass_rate": (sum(r["passed"] for r in results) / len(results)) if results else 0.0}
    (run_dir / "grading.json").write_text(json.dumps(g, indent=2))
    return g


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__); return 2
    if argv[0] != "--all":
        g = grade_run(Path(argv[0]).resolve())
        for r in g["expectations"]:
            print(f"  {'PASS' if r['passed'] else 'FAIL'}  {r['text']}  — {r['evidence']}")
        print(f"pass rate: {g['pass_rate']:.0%}")
        return 0
    it = Path(argv[1]).resolve()
    rows = []
    for run_dir in sorted(it.glob("*/*_skill")):
        if not (run_dir / "repo").is_dir():
            continue
        g = grade_run(run_dir)
        timing = json.loads((run_dir / "timing.json").read_text()) if (run_dir / "timing.json").exists() else {}
        rows.append((g["eval_name"], run_dir.name, g["pass_rate"], timing.get("total_duration_seconds"), timing.get("total_cost_usd"), timing.get("num_turns")))
    lines = [f"# Benchmark — {it.parent.name} / {it.name}", "", "| eval | config | pass rate | seconds | cost USD | turns |", "|---|---|---|---|---|---|"]
    for name, cfg, pr, secs, cost, turns in rows:
        lines.append(f"| {name} | {cfg} | {pr:.0%} | {secs if secs is None else round(secs)} | {cost if cost is None else round(cost, 3)} | {turns} |")
    for cfg in ("with_skill", "without_skill"):
        prs = [r[2] for r in rows if r[1] == cfg]
        if prs:
            lines.append(f"\n**{cfg}** mean pass rate: {sum(prs)/len(prs):.0%} over {len(prs)} run(s)")
    (it / "benchmark.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
