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
REPO = PLUGIN.parent.parent
# Worktrees have no installed environment; the main checkout's venv does.
PY = str(REPO / ".venv" / "bin" / "python") if (REPO / ".venv" / "bin" / "python").exists() else "python3"


def sh(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def _load_yaml(path: Path):
    import yaml
    return yaml.safe_load(path.read_text())


_CAPS_CACHE: dict[Path, dict[str, list[str]]] = {}


def _catalog_capabilities(repo: Path) -> dict[str, list[str]]:
    """component path -> capabilities, from the worktree's wiki/catalog.json (run.sh keeps the wiki)."""
    if repo not in _CAPS_CACHE:
        cat = repo / "wiki" / "catalog.json"
        comps = json.loads(cat.read_text())["components"] if cat.exists() else []
        _CAPS_CACHE[repo] = {c["path"]: list(c.get("capabilities") or []) for c in comps}
    return _CAPS_CACHE[repo]


_FACTS_CACHE: dict[Path, dict[str, dict]] = {}


def _catalog_facts(repo: Path) -> dict[str, dict]:
    """component path -> its catalog record (psa_level, namespace, ...), from the worktree's wiki/catalog.json."""
    if repo not in _FACTS_CACHE:
        cat = repo / "wiki" / "catalog.json"
        _FACTS_CACHE[repo] = {c["path"]: c for c in json.loads(cat.read_text())["components"]} if cat.exists() else {}
    return _FACTS_CACHE[repo]


def _choice_components(d: dict, stage: str | None) -> list[str]:
    stages = ((d or {}).get("spec") or {}).get("stages") or {}
    src = [stages.get(stage) or {}] if stage else stages.values()
    return [c for sd in src for c in ((sd or {}).get("choice") or [])]


def _expr_env(d: dict, repo: Path) -> dict:
    """Helpers available to `yaml_expr` assertions, all tolerant of missing keys."""
    spec = (d or {}).get("spec") or {}
    stages = spec.get("stages") or {}

    def st(name=None):
        return stages.get(name) or {} if name else stages

    def settings(name=None):
        if name:
            return (stages.get(name) or {}).get("settings") or {}
        return {k: (v or {}).get("settings") or {} for k, v in stages.items()}

    def setting(key, name=None):
        """One stage's value, or the list of every stage's value for that key."""
        if name:
            return settings(name).get(key)
        return [settings(k).get(key) for k in stages]

    def choices(name=None):
        src = [stages.get(name) or {}] if name else stages.values()
        return [c for sd in src for c in ((sd or {}).get("choice") or [])]

    def alts(name=None):
        src = [stages.get(name) or {}] if name else stages.values()
        return [a for sd in src for a in ((sd or {}).get("alternatives") or [])]

    def risks(name=None):
        src = [stages.get(name) or {}] if name else stages.values()
        return [r for sd in src for r in ((sd or {}).get("risks") or [])]

    def gates(name=None):
        src = [stages.get(name) or {}] if name else stages.values()
        return [g for sd in src for g in ((sd or {}).get("gate_to_next") or [])]

    def rules(name=None):
        src = [stages.get(name) or {}] if name else stages.values()
        return [r for sd in src for r in ((sd or {}).get("constrained_by") or [])]

    def oq():
        return spec.get("open_questions") or []

    def txt(x):
        return str(x if x is not None else "").lower()

    def has(pattern, x):
        return re.search(pattern, txt(x)) is not None

    def listed(x):
        return x if isinstance(x, list) else ([] if x is None else [x])

    def capabilities_of(component):
        return _catalog_capabilities(repo).get(component, [])

    def psa_exceptions(name=None):
        src = [stages.get(name) or {}] if name else stages.values()
        return [e for sd in src for e in ((sd or {}).get("psa_exceptions") or [])]

    def psa_level_of(component):
        return (_catalog_facts(repo).get(component) or {}).get("psa_level", "unknown")

    def namespace_of(component):
        return (_catalog_facts(repo).get(component) or {}).get("namespace")

    def choice_capabilities(name=None):
        """Every catalog capability the stage's (or every stage's) chosen components cover."""
        return sorted({cap for c in choices(name) for cap in capabilities_of(c)})

    return dict(d=d, spec=spec, stages=stages, st=st, settings=settings, setting=setting, choices=choices,
                capabilities_of=capabilities_of, choice_capabilities=choice_capabilities,
                psa_exceptions=psa_exceptions, psa_level_of=psa_level_of, namespace_of=namespace_of,
                alts=alts, risks=risks, gates=gates, rules=rules, oq=oq, txt=txt, has=has, listed=listed, re=re, len=len,
                any=any, all=all, str=str, set=set, sum=sum, int=int, float=float, bool=bool, sorted=sorted, isinstance=isinstance, list=list, dict=dict)


def seed_env(repo: Path) -> None:
    """Overlays consume gitignored .env files: seed them from the committed examples, as run.sh and CI do."""
    for ex in repo.glob("k8s/overlays/**/*.env.example"):
        real = ex.with_name(ex.name[: -len(".example")])
        if not real.exists():
            real.write_bytes(ex.read_bytes())


def check(a: dict, repo: Path) -> tuple[bool, str]:
    t = a["type"]
    path = repo / a.get("path", "")
    if t in {"kustomize_builds", "kubeconform", "command"}:
        seed_env(repo)
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
        rc, out = sh([PY, str(BUILDER / "validate.py"), a["path"]], repo)
        return rc == 0, out[-400:]
    if t == "pack_lint":
        rc, out = sh([PY, str(BUILDER / "packs.py"), "lint", a["path"]], repo)
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
    if t == "schema_valid":
        code = (f"import sys; sys.path.insert(0, {str(BUILDER)!r}); from common import load_yaml, schema_errors; "
                f"from pathlib import Path; e = schema_errors({a['schema']!r}, load_yaml(Path({str(path)!r})), {a['path']!r}); "
                f"print('\\n'.join(e)); sys.exit(1 if e else 0)")
        rc, out = sh([PY, "-c", code], repo)
        return rc == 0, "valid" if rc == 0 else out[-400:]
    if t == "yaml_expr":
        if not path.exists():
            return False, f"{a['path']} missing"
        try:
            d = _load_yaml(path)
            env = _expr_env(d, repo)
            val = eval(a["expr"], {"__builtins__": {}, **env})  # noqa: S307 - repo-authored; globals so comprehensions see the helpers
        except Exception as exc:
            return False, f"expr error: {exc}"
        return bool(val), f"{a['expr']} = {val!r}"
    if t in {"choice_has_capability", "choice_lacks_capability"}:
        # Asserts the role a choice plays, not its name: a better component with the same
        # capability passes too. `stage` is optional; without it every stage's choice counts.
        if not path.exists():
            return t == "choice_lacks_capability", f"{a['path']} missing"
        caps = _catalog_capabilities(repo)
        if not caps:
            return False, "wiki/catalog.json missing in the worktree"
        comps = _choice_components(_load_yaml(path), a.get("stage"))
        hits = [c for c in comps if a["capability"] in caps.get(c, [])]
        unknown = [c for c in comps if c not in caps]
        where = f"stage {a['stage']}" if a.get("stage") else "any stage"
        evidence = f"{a['capability']} ← {hits or 'none'} ({where})" + (f"; not in catalog: {unknown}" if unknown else "")
        return (bool(hits) if t == "choice_has_capability" else not hits), evidence
    if t == "yaml_count":
        rc, out = sh(["yq", "-r", a["query"], a["path"]], repo)
        return rc == 0 and out == str(a["equals"]), f"{a['query']} = {out!r}"
    if t == "command":
        # A shell command run in the worktree (the generated service builds, its tests pass).
        rc, out = sh(["bash", "-lc", a["cmd"]], repo)
        return rc == 0, "exit 0" if rc == 0 else f"exit {rc}: {out[-400:]}"
    if t == "scaffold_check":
        rc, out = sh([PY, str(BUILDER / "scaffold-check.py"), a["path"]], repo)
        return rc == 0, out[-400:]
    if t == "git_unchanged":
        rc, out = sh(["git", "diff", "--quiet", "HEAD", "--", a["path"]], repo)
        return rc == 0, "unchanged" if rc == 0 else "modified"
    return False, f"unknown assertion type {t}"


def quality_metrics(repo: Path) -> dict:
    """Judgement signals across every decision record the run produced; where a skill's value
    shows when pass rates tie (plan.md §3)."""
    m = {"records": 0, "open_questions": 0, "oq_with_rule": 0, "pack_refs": 0, "alternatives": 0, "risks": 0,
         "gates": 0, "gates_automated": 0, "stages": 0}
    # Records an eval copied in as fixtures are inputs, not outputs: skip anything byte-identical to a fixture.
    fixtures = {f.read_bytes() for f in (PLUGIN / "evals" / "fixtures").rglob("*.yaml")}
    for f in sorted(repo.glob("k8s/overlays/usecases/*/.builder/decisions/*.yaml")):
        try:
            if f.read_bytes() in fixtures:
                continue
            d = _load_yaml(f)
        except Exception:
            continue
        if not isinstance(d, dict) or d.get("kind") != "Decision":
            continue
        env = _expr_env(d, repo)
        m["records"] += 1
        m["stages"] += len(env["stages"])
        m["open_questions"] += len(env["oq"]())
        m["oq_with_rule"] += sum(1 for q in env["oq"]() if q.get("caused_by_rule"))
        m["pack_refs"] += len(env["rules"]())
        m["alternatives"] += len(env["alts"]())
        m["risks"] += len(env["risks"]())
        gs = env["gates"]()
        m["gates"] += len(gs)
        m["gates_automated"] += sum(1 for g in gs if ((g.get("check") or {}).get("type") or "manual") != "manual")
    return m


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
         "pass_rate": (sum(r["passed"] for r in results) / len(results)) if results else 0.0,
         "quality": quality_metrics(repo)}
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
        models = ",".join(m.replace("claude-", "") for m in timing.get("models", []))
        if timing.get("is_error"):
            models = f"ERROR: {timing.get('error') or 'is_error'}"
        rows.append((g["eval_name"], run_dir.name, g["pass_rate"], timing.get("total_duration_seconds"), timing.get("total_cost_usd"), timing.get("num_turns"), models, g.get("quality") or {}))
    lines = [f"# Benchmark — {it.parent.name} / {it.name}", "", "| eval | config | pass rate | seconds | cost USD | turns | models |", "|---|---|---|---|---|---|---|"]
    for name, cfg, pr, secs, cost, turns, models, _q in rows:
        lines.append(f"| {name} | {cfg} | {pr:.0%} | {secs if secs is None else round(secs)} | {cost if cost is None else round(cost, 3)} | {turns} | {models} |")
    for cfg in ("with_skill", "without_skill"):
        prs = [r[2] for r in rows if r[1] == cfg]
        if prs:
            lines.append(f"\n**{cfg}** mean pass rate: {sum(prs)/len(prs):.0%} over {len(prs)} run(s)")
    if any(r[7].get("records") for r in rows):
        lines += ["", "## Quality metrics (decision records produced by the run)", "",
                  "| eval | config | records | open questions | with rule | pack refs | alternatives | risks | gates | automated gates |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for name, cfg, _pr, _s, _c, _t, _m, q in rows:
            lines.append(f"| {name} | {cfg} | {q.get('records', 0)} | {q.get('open_questions', 0)} | {q.get('oq_with_rule', 0)} | {q.get('pack_refs', 0)} | {q.get('alternatives', 0)} | {q.get('risks', 0)} | {q.get('gates', 0)} | {q.get('gates_automated', 0)} |")
    (it / "benchmark.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
