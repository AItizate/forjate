#!/usr/bin/env python3
"""Check a scaffolded app against the records that specified it.

    scaffold-check.py <usecase-dir> [--app <dir>] [--json]

  1. .builder/scaffold.yaml validates and names the app's package, image, workloads and tools.
  2. Every tool line of the AI-engineering record (every stage) has a function of that name under
     app/src/**, with every parameter and the return annotated; `requires approval token` means an
     `approval_token` parameter, `read-only` means none; `idempotent` means an `idempotency_key`
     parameter. Every architecture workload at Crawl has a scaffold workload entry whose command
     module exists.
  3. .github/workflows/*.yml only call AItizate/gh-actions-templates pinned to @v1 (plus local
     steps for tests and the dispatch): no docker/build-push-action, no `docker build`/`docker push`,
     no `trivy` by hand, no `@main`; a build-push template call exists; the write-back dispatch
     sends `app-image-updated`.
  4. Dockerfile: a tagged base image (never latest), a non-root USER. pyproject.toml and tests/ exist.

Exit 1 with one finding per line; 0 clean.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import load_yaml, schema_errors  # noqa: E402

TOOL_LINE = re.compile(r"^\s*(?P<name>[a-z][a-z0-9_]*)\s*:\s*(?P<desc>[^\[]*?)\s*(\[(?P<flags>[^\]]*)\])?\s*$")
TEMPLATE = re.compile(r"^AItizate/gh-actions-templates/\.github/workflows/(?P<name>[a-z0-9-]+-template\.yml)@(?P<ref>.+)$")


def parse_tools(ai: dict) -> dict[str, set[str]]:
    tools: dict[str, set[str]] = {}
    for sd in (ai.get("spec") or {}).get("stages", {}).values():
        for line in (sd.get("settings") or {}).get("tools") or []:
            m = TOOL_LINE.match(str(line))
            if not m:
                continue
            flags = {f.strip().lower() for f in (m.group("flags") or "").split(",") if f.strip()}
            tools.setdefault(m.group("name"), set()).update(flags)
    return tools


def functions(app: Path) -> dict[str, list[tuple[Path, ast.FunctionDef]]]:
    out: dict[str, list[tuple[Path, ast.FunctionDef]]] = {}
    for py in sorted((app / "src").rglob("*.py")):
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError as exc:
            out.setdefault("__syntax_error__", []).append((py, exc))  # type: ignore[arg-type]
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(node.name, []).append((py, node))
    return out


def check_tools(ai: dict, app: Path, findings: list[str]) -> None:
    tools = parse_tools(ai)
    fns = functions(app)
    for py, exc in fns.pop("__syntax_error__", []):
        findings.append(f"{py}: syntax error: {exc}")
    for name, flags in sorted(tools.items()):
        cands = [(p, f) for p, f in fns.get(name, []) if "tools" in p.parts or True]
        if not cands:
            findings.append(f"tool {name}: no function `def {name}(` under app/src/")
            continue
        py, fn = cands[0]
        params = [a for a in fn.args.args + fn.args.kwonlyargs if a.arg not in ("self", "cls")]
        names = {a.arg for a in params}
        for a in params:
            if a.annotation is None:
                findings.append(f"tool {name} ({py.name}): parameter `{a.arg}` is not typed")
        if fn.returns is None:
            findings.append(f"tool {name} ({py.name}): no return annotation")
        needs_token = any("approval token" in f for f in flags)
        if needs_token and "approval_token" not in names:
            findings.append(f"tool {name} ({py.name}): record says `requires approval token` but there is no `approval_token` parameter")
        if "read-only" in flags and "approval_token" in names:
            findings.append(f"tool {name} ({py.name}): record says `read-only` but it takes an `approval_token`")
        if "idempotent" in flags and "idempotency_key" not in names:
            findings.append(f"tool {name} ({py.name}): record says `idempotent` but there is no `idempotency_key` parameter")


def check_workloads(arch: dict, scaffold: dict, app: Path, findings: list[str]) -> None:
    crawl = ((arch.get("spec") or {}).get("stages", {}).get("crawl") or {}).get("settings") or {}
    wanted = [str(w) for w in (crawl.get("workloads") or [])]
    have = {w["name"]: w for w in (scaffold.get("spec") or {}).get("workloads", [])}
    for w in wanted:
        if w not in have:
            findings.append(f"workload {w}: in the architecture record at Crawl but not in scaffold.yaml")
    pkg = (scaffold.get("spec") or {}).get("package", "")
    for name, w in have.items():
        cmd = w.get("command") or []
        if len(cmd) >= 3 and cmd[:2] == ["python", "-m"]:
            mod = cmd[2]
            path = app / "src" / Path(*mod.split("."))
            if not (path.with_suffix(".py").is_file() or (path / "__main__.py").is_file()):
                findings.append(f"workload {name}: command module {mod} has no file under app/src/")
            if pkg and not mod.startswith(pkg + "."):
                findings.append(f"workload {name}: command module {mod} is outside package {pkg}")


def check_workflows(app: Path, findings: list[str]) -> None:
    wf_dir = app / ".github" / "workflows"
    files = sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))) if wf_dir.is_dir() else []
    if not files:
        findings.append("no .github/workflows/ under app/ (expected the template calls)")
        return
    templates_used: set[str] = set()
    dispatch = False
    for f in files:
        text = f.read_text()
        try:
            doc = load_yaml(f)
        except Exception as exc:
            findings.append(f"{f.name}: invalid YAML: {exc}")
            continue
        for job_name, job in ((doc.get("jobs") or {}).items()):
            uses = job.get("uses") if isinstance(job, dict) else None
            if uses:
                m = TEMPLATE.match(str(uses))
                if not m:
                    findings.append(f"{f.name}: job {job_name} uses `{uses}`, not a shared AItizate/gh-actions-templates workflow")
                elif m.group("ref") != "v1" and not re.fullmatch(r"v1(\.\d+){0,2}", m.group("ref")):
                    findings.append(f"{f.name}: job {job_name} pins the template to `@{m.group('ref')}` instead of @v1")
                else:
                    templates_used.add(m.group("name"))
            for step in (job.get("steps") or []) if isinstance(job, dict) else []:
                su = str(step.get("uses", ""))
                run = str(step.get("run", ""))
                if "docker/build-push-action" in su or re.search(r"\bdocker\s+(build|push)\b", run) or re.search(r"\btrivy\b", run):
                    findings.append(f"{f.name}: job {job_name} reimplements build/scan/push (`{su or run.strip().splitlines()[0][:60]}`); call build-push-generic-template.yml@v1")
                if "repository-dispatch" in su or "repository_dispatch" in run or "dispatches" in run:
                    if "app-image-updated" in text:
                        dispatch = True
        if "@main" in text and "gh-actions-templates" in text:
            findings.append(f"{f.name}: a template is referenced on @main (a branch ref)")
    if not any(t.startswith("build-push") for t in templates_used):
        findings.append("no workflow calls build-push-generic-template.yml@v1 (or the ECR variant)")
    if "pr-validation-template.yml" not in templates_used:
        findings.append("no workflow calls pr-validation-template.yml@v1")
    if not dispatch:
        findings.append("no workflow dispatches `app-image-updated` to the IaC repo (the write-back)")


def check_dockerfile(app: Path, findings: list[str]) -> None:
    df = app / "Dockerfile"
    if not df.is_file():
        findings.append("no app/Dockerfile")
        return
    text = df.read_text()
    froms = re.findall(r"^FROM\s+(\S+)", text, re.MULTILINE)
    if not froms:
        findings.append("Dockerfile has no FROM")
    for base in froms:
        if ":" not in base.split("/")[-1] or base.endswith(":latest"):
            findings.append(f"Dockerfile base `{base}` is not pinned to a tag")
    users = re.findall(r"^USER\s+(\S+)", text, re.MULTILINE)
    if not users or users[-1] in ("root", "0"):
        findings.append("Dockerfile does not switch to a non-root USER")


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    uc = Path(args[0]).resolve()
    app = Path(argv[argv.index("--app") + 1]).resolve() if "--app" in argv else uc / "app"
    findings: list[str] = []
    b = uc / ".builder"
    sc_path = b / "scaffold.yaml"
    scaffold: dict = {}
    if not sc_path.is_file():
        findings.append(f"{sc_path.relative_to(uc)} missing")
    else:
        scaffold = load_yaml(sc_path)
        findings += schema_errors("scaffold", scaffold, str(sc_path))
    if not app.is_dir():
        findings.append(f"{app} missing")
        print("\n".join(findings))
        return 1
    for req in ("pyproject.toml", "README.md"):
        if not (app / req).is_file():
            findings.append(f"app/{req} missing")
    if not list((app / "tests").rglob("test_*.py")) if (app / "tests").is_dir() else True:
        findings.append("app/tests/ has no test_*.py")
    ai = b / "decisions" / "ai-engineering.yaml"
    if ai.is_file():
        check_tools(load_yaml(ai), app, findings)
        declared = {t["name"] for t in (scaffold.get("spec") or {}).get("tools", [])}
        for name in parse_tools(load_yaml(ai)):
            if scaffold and name not in declared:
                findings.append(f"tool {name}: not listed in scaffold.yaml tools")
    arch = b / "decisions" / "architecture.yaml"
    if arch.is_file() and scaffold:
        check_workloads(load_yaml(arch), scaffold, app, findings)
    check_workflows(app, findings)
    check_dockerfile(app, findings)
    if as_json:
        print(json.dumps(findings, indent=2))
    else:
        for f in findings:
            print(f"finding: {f}")
        print(f"scaffold-check: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
