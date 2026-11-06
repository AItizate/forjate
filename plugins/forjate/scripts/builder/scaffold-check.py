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
  5. Readiness, statically (#41). A seed, run or verify Job reaches services of the scaffold (the stubs and
     the agent API, Deployments of scaffold.yaml) through its *_URL variables, and those services reach
     others through theirs. For every service on that route, a request to its /readyz must be reachable from
     the Job's `main` (a helper called with the service's URL setting counts) before the first use of the
     request to the URL in the same function (reading the setting, as a guard on its host, is not a request).
     A setting is wherever the code binds the env var's name: an assignment or a keyword argument. Which
     variables a Job uses is read from its code, not from its env list.
     Components the app only calls (Docling, Ollama) are not scaffold workloads and are out of scope.
  6. When the use case has an assembled overlay (kustomization.yaml at its root), every scaffold workload
     with a health_path has a Deployment there whose container carries a startupProbe: a process that
     listens only after its store answers is not killed while it waits.
  7. A workload that mounts a catalog component's Secret reads that Secret's keys as the catalog's
     `wiring.secret.keys` names them (MinIO's are MINIO_ROOT_USER/MINIO_ROOT_PASSWORD, not an S3 SDK's
     names): a key the app never reads is a credential it never gets. The verify Job (phase verify) never
     runs MODEL_MODE=live: the Crawl gate runs where no provider key exists.

Exit 1 with one finding per line; 0 clean.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import load_catalog, load_yaml, schema_errors  # noqa: E402

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
    by_phase = {w.get("phase"): w for w in have.values() if w.get("phase")}
    for w in wanted:
        generic = {"seed-job": "seed", "verify-job": "verify", "run-job": "run", "replay-job": "run", "intake-job": "run"}.get(w)
        if w not in have and not (generic and generic in by_phase):
            findings.append(f"workload {w}: in the architecture record at Crawl but not in scaffold.yaml (nor a Job with phase {generic or '?'})")
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


# --------------------------------------------------------------------------- 5. readiness waits
HTTP_CALLS = {"get", "head", "options", "request", "urlopen", "stream"}


class Pkg:
    """The scaffold's package as syntax trees: functions by (module, name), imports, URL settings by env var."""

    def __init__(self, app: Path, package: str):
        self.package = package
        self.modules: dict[str, ast.Module] = {}
        root = app / "src" / package
        for py in sorted(root.rglob("*.py")) if root.is_dir() else []:
            rel = py.relative_to(app / "src").with_suffix("")
            name = ".".join(rel.parts[:-1]) if rel.name == "__init__" else ".".join(rel.parts)
            try:
                self.modules[name] = ast.parse(py.read_text())
            except SyntaxError:
                continue  # reported by check_tools
        self.funcs: dict[tuple[str, str], ast.AST] = {}
        for mod, tree in self.modules.items():
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.funcs.setdefault((mod, node.name), node)

    def imports(self, mod: str) -> set[str]:
        out: set[str] = set()
        tree = self.modules.get(mod)
        if tree is None:
            return out
        base = mod.split(".")[:-1] if not mod.endswith("__init__") else mod.split(".")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    parent = base[: len(base) - node.level + 1] if node.level > 1 else base
                    target = ".".join(parent + (node.module.split(".") if node.module else []))
                else:
                    target = node.module or ""
                for cand in [target] + [f"{target}.{a.name}" for a in node.names]:
                    if cand in self.modules:
                        out.add(cand)
            elif isinstance(node, ast.Import):
                out |= {a.name for a in node.names if a.name in self.modules}
        return out

    def import_closure(self, mod: str) -> set[str]:
        seen, todo = set(), [mod]
        while todo:
            m = todo.pop()
            if m in seen or m not in self.modules:
                continue
            seen.add(m)
            todo += list(self.imports(m))
        return seen

    def settings_keys(self, env_name: str) -> set[str]:
        """Names a code path can use for the env var: the attribute it is stored in, and the variable itself."""
        keys = {env_name}
        for tree in self.modules.values():
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                    if any(isinstance(c, ast.Constant) and c.value == env_name for c in ast.walk(node.value)):
                        for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                            if isinstance(t, ast.Name):
                                keys.add(t.id)
                            elif isinstance(t, ast.Attribute):
                                keys.add(t.attr)
                elif isinstance(node, ast.keyword) and node.arg:   # Settings(odoo_url=_env("ODOO_URL"))
                    if any(isinstance(c, ast.Constant) and c.value == env_name for c in ast.walk(node.value)):
                        keys.add(node.arg)
        return keys

    def resolve(self, mod: str, name: str) -> list[tuple[str, str]]:
        """The functions a call by simple name can reach: this module's, else every module's."""
        if (mod, name) in self.funcs:
            return [(mod, name)]
        return [k for k in self.funcs if k[1] == name]


def call_name(call: ast.Call) -> str:
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def mentions(node: ast.AST) -> set[str]:
    """Attribute names and string constants under node: how a code path names a URL setting."""
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.add(n.value)
        elif isinstance(n, ast.Name):
            out.add(n.id)
    return out


def is_readyz_request(call: ast.Call) -> bool:
    if call_name(call) not in HTTP_CALLS:
        return False
    return any(isinstance(c, ast.Constant) and isinstance(c.value, str) and "/readyz" in c.value
               for a in list(call.args) + [k.value for k in call.keywords] for c in ast.walk(a))


class Waits:
    """For each function: which URL settings a readiness wait on /readyz covers, following calls by name."""

    def __init__(self, pkg: Pkg):
        self.pkg = pkg
        self.helpers: dict[tuple[str, str], list[int]] = {}   # fn -> indexes of the parameters it requests /readyz on
        self.http_helpers: dict[tuple[str, str], list[int]] = {}   # fn -> indexes of the parameters it requests, any path
        self.direct: dict[tuple[str, str], set[str]] = {}
        for key, fn in pkg.funcs.items():
            params = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
            for call in (c for c in ast.walk(fn) if isinstance(c, ast.Call) and is_readyz_request(c)):
                subject = mentions(ast.Module(body=[ast.Expr(a) for a in call.args], type_ignores=[]))
                self.direct.setdefault(key, set()).update(subject - set(params))
                self.helpers.setdefault(key, []).extend(i for i, p in enumerate(params) if p in subject)
            # A helper that requests whatever URL it is given (http_ready(url)) waits on /readyz when its
            # caller passes a /readyz URL: http_ready(f"{settings.odoo_url}/readyz").
            for call in (c for c in ast.walk(fn) if isinstance(c, ast.Call) and call_name(c) in HTTP_CALLS):
                subject = mentions(ast.Module(body=[ast.Expr(a) for a in call.args], type_ignores=[]))
                self.http_helpers.setdefault(key, []).extend(i for i, p in enumerate(params) if p in subject)
        self.effect: dict[tuple[str, str], set[str]] = {k: set(v) for k, v in self.direct.items()}
        changed = True
        while changed:
            changed = False
            for key, fn in pkg.funcs.items():
                got = self.effect.setdefault(key, set())
                before = len(got)
                for call in (c for c in ast.walk(fn) if isinstance(c, ast.Call)):
                    got |= self.call_effect(key[0], call)
                changed |= len(got) != before

    def is_request(self, mod: str, call: ast.Call) -> bool:
        """An HTTP call, or a call to a function that makes one on what it is given."""
        return call_name(call) in HTTP_CALLS or any(self.http_helpers.get(t) for t in self.pkg.resolve(mod, call_name(call)))

    def call_effect(self, mod: str, call: ast.Call) -> set[str]:
        out: set[str] = set()
        for target in self.pkg.resolve(mod, call_name(call)):
            out |= self.effect.get(target, set())
            for i in self.helpers.get(target, []):
                if i < len(call.args):
                    out |= mentions(call.args[i])
            for i in self.http_helpers.get(target, []):
                if i < len(call.args) and any(isinstance(c, ast.Constant) and isinstance(c.value, str) and "/readyz" in c.value
                                              for c in ast.walk(call.args[i])):
                    out |= mentions(call.args[i])
        return out


def reachable(pkg: Pkg, start: tuple[str, str]) -> set[tuple[str, str]]:
    seen, todo = set(), [start]
    while todo:
        key = todo.pop()
        if key in seen or key not in pkg.funcs:
            continue
        seen.add(key)
        for call in (c for c in ast.walk(pkg.funcs[key]) if isinstance(c, ast.Call)):
            todo += pkg.resolve(key[0], call_name(call))
    return seen


def url_vars(w: dict) -> list[tuple[str, str]]:
    """(ENV_VAR, host) of the workload's *_URL variables."""
    out = []
    for item in w.get("env") or []:
        key, _, value = str(item).partition("=")
        if key.endswith("_URL") and "://" in value:
            out.append((key, value.split("://", 1)[1].split("/")[0].split(":")[0].split(".")[0]))
    return out


def module_of(w: dict) -> str:
    cmd = w.get("command") or []
    return cmd[2] if len(cmd) >= 3 and cmd[:2] == ["python", "-m"] else ""


def service_route(pkg: Pkg, services: dict[str, dict], start: str) -> dict[str, list[tuple[str, set[str]]]]:
    """The services a service reaches by the URL settings its modules use, and those they reach in turn."""
    route: dict[str, list[tuple[str, set[str]]]] = {}
    todo, seen = [start], set()
    while todo:
        svc = todo.pop()
        if svc in seen:
            continue
        seen.add(svc)
        used: set[str] = set()
        for mod in pkg.import_closure(module_of(services[svc])):
            used |= mentions(pkg.modules[mod])
        for var, host in url_vars(services[svc]):
            keys = pkg.settings_keys(var)
            if host in services and keys & used:
                route.setdefault(host, []).append((var, keys))
                todo.append(host)
    return route


def check_readiness(scaffold: dict, app: Path, findings: list[str]) -> None:
    spec = scaffold.get("spec") or {}
    pkg = Pkg(app, spec.get("package", ""))
    if not pkg.modules:
        return
    workloads = spec.get("workloads", [])
    services = {w["name"]: w for w in workloads if w.get("kind") == "deployment"}
    waits = Waits(pkg)
    for w in workloads:
        if w.get("kind") != "job" or w.get("phase") not in ("seed", "run", "verify"):
            continue
        entry = module_of(w)
        if not entry or (entry, "main") not in pkg.funcs:
            continue   # the module or its main is missing: check_workloads says so
        root = (entry, "main")
        fns = reachable(pkg, root)
        used: set[str] = set()
        for key in fns:
            used |= mentions(pkg.funcs[key])
        route: dict[str, list[tuple[str, set[str]]]] = {}
        for var, host in url_vars(w):
            keys = pkg.settings_keys(var)
            if host in services and keys & used:
                route.setdefault(host, []).append((var, keys))
                for svc, vias in service_route(pkg, services, host).items():
                    route.setdefault(svc, []).extend(vias)
        covered = waits.effect.get(root, set())
        for svc, vias in sorted(route.items()):
            if not any(keys & covered for _, keys in vias):
                findings.append(
                    f"workload {w['name']} ({w.get('phase')}): its route reaches {svc} (through {', '.join(sorted({v for v, _ in vias}))}) "
                    f"but no request to {svc}'s /readyz is reachable from {entry}.main; wait for it, bounded and loud, before the first request")
                continue
            for key in fns:   # waiting is not enough if the URL is used before it, in the same function
                fn = pkg.funcs[key]
                points = sorted(c.lineno for c in ast.walk(fn) if isinstance(c, ast.Call)
                                and any(keys & (waits.call_effect(key[0], c) | (mentions(c) if is_readyz_request(c) else set())) for _, keys in vias))
                if not points:
                    continue
                wait_calls = {id(n) for c in ast.walk(fn) if isinstance(c, ast.Call) and c.lineno in points for n in ast.walk(c)}
                # a request to the URL before the wait is the race; reading the setting (a guard on its host) is not
                for c in sorted((c for c in ast.walk(fn) if isinstance(c, ast.Call) and id(c) not in wait_calls
                                 and c.lineno < points[0] and waits.is_request(key[0], c)), key=lambda c: c.lineno):
                    hit = next((a for _, keys in vias for a in sorted(keys & mentions(c))), None)
                    if hit:
                        findings.append(f"workload {w['name']} ({w.get('phase')}): {key[0]}.{key[1]} uses {hit} (line {c.lineno}) before it waits for {svc}'s /readyz (line {points[0]})")
                        break


# ------------------------------------------------------------------- 6. startup probes in the overlay
WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet"}


def overlay_workloads(root: Path) -> dict[str, list[dict]]:
    """Workload documents of the overlay rooted at root/kustomization.yaml, following local resources only."""
    out: dict[str, list[dict]] = {}
    seen: set[Path] = set()

    def visit(path: Path) -> None:
        path = path.resolve()
        if path in seen or not path.is_relative_to(root.resolve()):
            return
        seen.add(path)
        if path.is_dir():
            for name in ("kustomization.yaml", "kustomization.yml"):
                if (path / name).is_file():
                    k = yaml.safe_load((path / name).read_text()) or {}
                    for r in k.get("resources") or []:
                        if isinstance(r, str) and "://" not in r:
                            visit(path / r)
                    return
        elif path.is_file() and path.suffix in (".yaml", ".yml"):
            for d in yaml.safe_load_all(path.read_text()):
                if isinstance(d, dict) and d.get("kind") in WORKLOAD_KINDS:
                    out.setdefault(d["metadata"]["name"], []).append(d)

    visit(root)
    return out


def check_startup_probes(uc: Path, scaffold: dict, findings: list[str]) -> None:
    if not (uc / "kustomization.yaml").is_file():
        return   # not assembled yet: the scaffold is checked before the overlay exists
    try:
        have = overlay_workloads(uc)
    except yaml.YAMLError as exc:
        findings.append(f"overlay: invalid YAML: {exc}")
        return
    for w in (scaffold.get("spec") or {}).get("workloads", []):
        if not w.get("health_path"):
            continue
        docs = have.get(w["name"])
        if not docs:
            findings.append(f"workload {w['name']} has health_path {w['health_path']} but no Deployment of that name in the overlay")
            continue
        for d in docs:
            containers = (((d.get("spec") or {}).get("template") or {}).get("spec") or {}).get("containers") or []
            main = next((c for c in containers if c.get("name") == w["name"]), containers[0] if containers else {})
            if not main.get("startupProbe"):
                findings.append(f"workload {w['name']} has health_path {w['health_path']} but its container has no startupProbe in the overlay: "
                                f"a process that listens only after its store answers is killed while it waits")

def check_secret_keys(scaffold: dict, app: Path, findings: list[str]) -> None:
    catalog = load_catalog()
    if not catalog:
        return
    keys_of = {}
    for c in catalog.get("components", []):
        sec = (c.get("wiring") or {}).get("secret") or {}
        if sec.get("name") and sec.get("keys"):
            keys_of.setdefault(sec["name"], (c["path"], sec["keys"]))
    mounted = {s for w in (scaffold.get("spec") or {}).get("workloads", []) for s in (w.get("secrets") or [])}
    source = "\n".join(f.read_text(errors="replace") for f in (app / "src").rglob("*.py")) if (app / "src").is_dir() else ""
    for w in (scaffold.get("spec") or {}).get("workloads", []):
        if w.get("phase") == "verify" and "MODEL_MODE=live" in (w.get("env") or []):
            findings.append(f"workload {w.get('name')}: the verify Job runs MODEL_MODE=live; the Crawl gate runs the double (replay or rules)")
    for name in sorted(mounted & keys_of.keys()):
        component, keys = keys_of[name]
        unread = [k for k in keys if k not in source]
        if unread:
            findings.append(f"secret {name} ({component}): the app never reads {', '.join(unread)}; "
                            f"the catalog's keys are {', '.join(keys)}, read them by that name")


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
    if scaffold:
        check_readiness(scaffold, app, findings)
        check_startup_probes(uc, scaffold, findings)
    check_workflows(app, findings)
    check_dockerfile(app, findings)
    if scaffold:
        check_secret_keys(scaffold, app, findings)
    if as_json:
        print(json.dumps(findings, indent=2))
    else:
        for f in findings:
            print(f"finding: {f}")
        print(f"scaffold-check: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
