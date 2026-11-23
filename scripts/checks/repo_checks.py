#!/usr/bin/env python3
"""Repo-wide checks over k8s/base and k8s/components, driven by wiki/catalog.json. No check names a component
or a vendor: the facts come from the catalog (which components provide a capability, their Services, labels,
Secrets and images) and from the capability vocabulary (the contract keys).

    repo_checks.py coupling [--baseline FILE] [--write-baseline]
    repo_checks.py contract
    repo_checks.py pins     [--baseline FILE] [--write-baseline]

coupling  A component that does not provide `object-store` carries, as a value, a fact of one that does: its
          Service or pod label as a host, its Secret's name, its image repository; or a literal value on a pod's S3
          credential variable (`env` `*_ACCESS_KEY`, `*_SECRET_KEY`; a shipped placeholder Secret is not one). Variable names are the application's and are
          allowed; YAML is read as data, so comments do not count; any other file is read as text.
contract  Every `wiring.consumes` declaration names a protocol some capability's `contract` defines, and only
          keys that contract lists. Rendered pods are checked against it once consumers declare it.
pins      Remote resources carry `?ref=<tag|sha>` (a file URL a versioned path), `helmCharts` an exact
          `version`, and every `image` (pod specs, custom resources, Helm values, kustomize `images:`) a tag
          other than `latest` or a digest.

coupling and pins ratchet against a committed baseline: they fail on an offender the baseline does not list
and on a baseline entry that no longer offends, so the baseline only shrinks. `--write-baseline` rewrites it
(review the diff: it must only lose lines). Exit codes: 0 pass, 1 fail."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CAPABILITY = "object-store"
TAG_RE = re.compile(r"^v?[0-9]+\.[0-9]+(\.[0-9]+)?([-+.][A-Za-z0-9.-]+)?$|^[0-9a-f]{7,40}$")
VERSION_RE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9.-]+)?$")
S3_CREDENTIAL_RE = re.compile(r"(ACCESS_KEY|SECRET_KEY|ACCESS_KEY_ID|SECRET_ACCESS_KEY)$")
YAML_SUFFIXES = {".yaml", ".yml"}
TEXT_SUFFIXES = YAML_SUFFIXES | {".md", ".json", ".toml", ".conf", ".cfg", ".ini", ".txt", ".env", ".example", ".sh", ".py", ".tpl"}


def load_catalog(repo: Path) -> dict:
    return json.loads((repo / "wiki" / "catalog.json").read_text(encoding="utf-8"))


def read_baseline(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.lstrip().startswith("#")}


def ratchet(offenders: set[str], baseline: set[str]) -> tuple[list[str], list[str]]:
    """(new offenders the baseline does not list, baseline entries that no longer offend)."""
    return sorted(offenders - baseline), sorted(baseline - offenders)


def _files(root: Path):
    for f in sorted(root.rglob("*")):
        if f.is_file() and not any(part.startswith(".") for part in f.relative_to(root).parts):
            yield f


def _yaml_docs(f: Path) -> list:
    try:
        return [d for d in yaml.safe_load_all(f.read_text(encoding="utf-8")) if d is not None]
    except (yaml.YAMLError, UnicodeDecodeError):
        return []


def _scalars(node, path: str = ""):
    """(key, value, is_env) for every string scalar; an env entry reports its variable name as the key."""
    if isinstance(node, dict):
        if isinstance(node.get("name"), str) and ("value" in node or "valueFrom" in node):
            if isinstance(node.get("value"), str):
                yield node["name"], node["value"], True
            return
        for k, v in node.items():
            yield from _scalars(v, str(k))
    elif isinstance(node, list):
        for v in node:
            yield from _scalars(v, path)
    elif isinstance(node, str):
        yield path, node, False


# --- coupling -------------------------------------------------------------------------------------------------

def _provider_facts(catalog: dict) -> list[tuple[re.Pattern, str]]:
    """One pattern per distinct fact of the providers (a Service, pod label or Secret name as a whole token, an
    image repository as a substring), described with the providers that carry it."""
    tokens: dict[str, set[str]] = {}
    repos: dict[str, set[str]] = {}
    for c in catalog.get("components", []):
        if CAPABILITY not in (c.get("capabilities") or []):
            continue
        w = c.get("wiring") or {}
        for tok in [w.get("service"), w.get("label"), (w.get("secret") or {}).get("name"), *(w.get("placeholder_secrets") or [])]:
            if tok:
                tokens.setdefault(tok.lower(), set()).add(c["path"])
        for img in c.get("images") or []:
            repo = img.split("@", 1)[0]
            repo = repo.rsplit(":", 1)[0] if ":" in repo.rsplit("/", 1)[-1] else repo
            repos.setdefault(repo.lower(), set()).add(c["path"])
    facts = [(re.compile(rf"(?<![\w.-]){re.escape(t)}(?![\w-])", re.IGNORECASE), f"'{t}' ({', '.join(sorted(p))})") for t, p in sorted(tokens.items())]
    facts += [(re.compile(re.escape(r), re.IGNORECASE), f"image '{r}' ({', '.join(sorted(p))})") for r, p in sorted(repos.items())]
    return facts


def _line_of(value: str, rx: re.Pattern) -> str:
    """The line of a (possibly multi-line) value that matches, trimmed for the report."""
    line = next((ln for ln in value.splitlines() if rx.search(ln)), value).strip()
    return line if len(line) <= 80 else line[:77] + "..."


def _owner(rel_dir: str, paths: list[str]) -> str | None:
    """The deepest catalog component whose directory contains `rel_dir` (relative to k8s/components)."""
    best = None
    for p in paths:
        if (rel_dir == p or rel_dir.startswith(p + "/")) and (best is None or len(p) > len(best)):
            best = p
    return best


def coupling_offenders(repo: Path) -> dict[str, list[str]]:
    catalog = load_catalog(repo)
    facts = _provider_facts(catalog)
    caps = {c["path"]: set(c.get("capabilities") or []) for c in catalog.get("components", [])}
    root = repo / "k8s" / "components"
    out: dict[str, list[str]] = {}
    if not root.is_dir():
        return out
    for f in _files(root):
        if f.suffix not in TEXT_SUFFIXES and not f.name.endswith(".example"):
            continue
        owner = _owner(f.parent.relative_to(root).as_posix(), list(caps))
        if owner and CAPABILITY in caps[owner]:
            continue
        reasons: list[str] = []
        if f.suffix in YAML_SUFFIXES:
            for doc in _yaml_docs(f):
                for key, value, is_env in _scalars(doc):
                    for rx, what in facts:
                        if rx.search(value):
                            reasons.append(f"{key}: '{_line_of(value, rx)}' names {what}")
                    if is_env and S3_CREDENTIAL_RE.search(key) and value:
                        reasons.append(f"env {key}: literal S3 credential (read it with secretKeyRef)")
        else:
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(lines, 1):
                for rx, what in facts:
                    if rx.search(line):
                        reasons.append(f"line {n} names {what}")
        if reasons:
            out[f.relative_to(repo).as_posix()] = reasons
    return out


# --- contract -------------------------------------------------------------------------------------------------

def contract_errors(repo: Path) -> tuple[list[str], int]:
    catalog = load_catalog(repo)
    errors: list[str] = []
    contracts: dict[str, tuple[str, set[str], list[re.Pattern]]] = {}
    for name, cap in (catalog.get("capabilities") or {}).items():
        c = cap.get("contract")
        if c is None:
            continue
        missing = [k for k in ("protocol", "secret_keys", "config_keys") if not c.get(k)]
        if missing:
            errors.append(f"capability {name}: contract lacks {', '.join(missing)}")
            continue
        pats = [re.compile(rf"^(?:{p})$") for p in c.get("config_key_patterns") or []]
        contracts[c["protocol"]] = (name, set(c["secret_keys"]) | set(c["config_keys"]), pats)
    n = 0
    for comp in catalog.get("components", []):
        consumes = (comp.get("wiring") or {}).get("consumes") or []
        if consumes:
            n += 1
        for i, entry in enumerate(consumes):
            where = f"{comp['path']}: wiring.consumes[{i}]"
            proto = entry.get("protocol")
            if proto not in contracts:
                errors.append(f"{where}: protocol '{proto}' has no contract (known: {', '.join(sorted(contracts)) or 'none'})")
                continue
            cap, keys, pats = contracts[proto]
            foreign = [k for k in entry.get("keys") or [] if k not in keys and not any(p.match(k) for p in pats)]
            if foreign:
                errors.append(f"{where}: keys {foreign} are not in the {cap} contract")
    return errors, n


# --- pins -----------------------------------------------------------------------------------------------------

def _remote_ok(ref: str) -> bool:
    if "?ref=" in ref:
        return bool(TAG_RE.match(ref.split("?ref=", 1)[1].split("&", 1)[0]))
    if re.match(r"^https?://", ref) and re.search(r"\.(ya?ml|json)$", ref.split("?", 1)[0]):
        return any(TAG_RE.match(seg) for seg in ref.split("?", 1)[0].split("/"))  # a file URL: pinned by its path
    return False


def _image_ok(image: str) -> bool:
    if "@sha256:" in image:
        return True
    last = image.rsplit("/", 1)[-1]
    return ":" in last and last.rsplit(":", 1)[1] not in ("", "latest")


def _images(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "image" and isinstance(v, str):
                yield v
            elif k == "image" and isinstance(v, dict) and "repository" in v:
                tag = v.get("tag")
                if tag is not None and str(tag) in ("", "latest"):
                    yield f"{v['repository']}:{tag}"
            else:
                yield from _images(v)
    elif isinstance(node, list):
        for v in node:
            yield from _images(v)


def pin_offenders(repo: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for top in ("base", "components"):
        root = repo / "k8s" / top
        if not root.is_dir():
            continue
        for f in _files(root):
            if f.suffix not in YAML_SUFFIXES:
                continue
            reasons: list[str] = []
            for doc in _yaml_docs(f):
                if not isinstance(doc, dict):
                    continue
                if f.name in ("kustomization.yaml", "kustomization.yml") or doc.get("kind") in ("Kustomization", "Component"):
                    for key in ("resources", "components"):
                        for ref in doc.get(key) or []:
                            if isinstance(ref, str) and ("://" in ref or ref.startswith("github.com/")) and not _remote_ok(ref):
                                reasons.append(f"{key}: {ref} is not pinned to a tag or commit")
                    for chart in doc.get("helmCharts") or []:
                        if not VERSION_RE.match(str(chart.get("version") or "")):
                            reasons.append(f"helmCharts {chart.get('name')}: version '{chart.get('version')}' is not exact")
                    for img in doc.get("images") or []:
                        if isinstance(img, dict) and str(img.get("newTag")) == "latest" and not img.get("digest"):
                            reasons.append(f"images {img.get('name')}: newTag latest")
                    continue
                for image in _images(doc):
                    if not _image_ok(image):
                        reasons.append(f"image {image} is untagged or latest")
            if reasons:
                out[f.relative_to(repo).as_posix()] = reasons
    return out


# --- CLI ------------------------------------------------------------------------------------------------------

def _ratchet_cli(name: str, offenders: dict[str, list[str]], baseline_path: Path, write: bool) -> int:
    if write:
        header = [ln for ln in (baseline_path.read_text(encoding="utf-8").splitlines() if baseline_path.is_file() else []) if ln.startswith("#")]
        baseline_path.write_text("\n".join(header + sorted(offenders)) + "\n", encoding="utf-8")
        print(f"{name}: wrote {len(offenders)} entr(y/ies) to {baseline_path.relative_to(REPO) if baseline_path.is_relative_to(REPO) else baseline_path}")
        return 0
    new, gone = ratchet(set(offenders), read_baseline(baseline_path))
    for path in new:
        print(f"NEW {path}")
        for r in offenders[path]:
            print(f"    {r}")
    for path in gone:
        print(f"FIXED {path}: no longer offends; remove it from {baseline_path.name}")
    if new or gone:
        print(f"FAIL: {name}: {len(new)} new offender(s), {len(gone)} stale baseline entr(y/ies)")
        return 1
    print(f"PASS: {name}: {len(offenders)} offender(s), all in the baseline")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("coupling", "contract", "pins"):
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    repo = Path(rest[rest.index("--repo") + 1]).resolve() if "--repo" in rest else REPO
    here = Path(__file__).resolve().parent
    default = {"coupling": here / "object-store-coupling.baseline", "pins": here / "pin.baseline"}
    baseline = Path(rest[rest.index("--baseline") + 1]) if "--baseline" in rest else default.get(cmd)
    if cmd == "contract":
        errors, n = contract_errors(repo)
        for e in errors:
            print(f"  {e}")
        if errors:
            print(f"FAIL: contract: {len(errors)} error(s)")
            return 1
        print(f"PASS: contract: {n} consumer(s) declare wiring.consumes, all within their contract")
        return 0
    offenders = coupling_offenders(repo) if cmd == "coupling" else pin_offenders(repo)
    return _ratchet_cli(f"object-store-{cmd}" if cmd == "coupling" else "pins", offenders, baseline, "--write-baseline" in rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
