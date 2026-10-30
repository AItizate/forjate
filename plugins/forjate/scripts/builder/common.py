"""Shared loaders for the use-case builder tooling.

Everything the builder emits is YAML validated against the JSON Schemas in
schemas/. The schemas reference each other through relative $ref, so they are
loaded into one registry keyed by file name instead of being fetched by $id.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HERE = Path(__file__).resolve().parent
SCHEMAS = HERE / "schemas"
PLUGIN_ROOT = HERE.parent.parent

# The plugin may run from inside this repo or installed under ~/.claude/plugins.
# Either way the tenant repo being worked on is the project directory.
REPO = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd()).resolve()
COMPONENTS = REPO / "k8s" / "components"

STAGES = ("crawl", "walk", "run")
ROLES = (
    "coordinator", "stage-planner", "kustomize", "context-pack", "app-scaffold",
    "business", "architecture", "ai-engineering", "data-store", "data-pipeline",
    "security", "compliance", "quality", "devops", "ux",
)
ENFORCE_RANK = {"may": 0, "should": 1, "must": 2}
PSA_RANK = {"privileged": 0, "baseline": 1, "restricted": 2}
AUTONOMY_RANK = {"assistive": 0, "semi-autonomous": 1, "autonomous": 2}


class BuilderError(Exception):
    """A validation failure meant for humans; message is already formatted."""


class _Loader(yaml.SafeLoader):
    """SafeLoader that leaves dates as strings so JSON Schema `format: date` can check them."""


_Loader.yaml_implicit_resolvers = {
    k: [(tag, regexp) for tag, regexp in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(path: Path) -> dict:
    try:
        data = yaml.load(path.read_text(), Loader=_Loader)
    except yaml.YAMLError as exc:
        raise BuilderError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise BuilderError(f"{path}: expected a mapping at top level")
    return data


def _registry() -> Registry:
    registry = Registry()
    for schema_file in SCHEMAS.glob("*.schema.json"):
        schema = json.loads(schema_file.read_text())
        resource = Resource.from_contents(schema)
        # Register under both the declared $id and the bare file name so a
        # relative "$ref": "_defs.schema.json#/..." resolves offline.
        registry = registry.with_resource(schema["$id"], resource)
        registry = registry.with_resource(schema_file.name, resource)
    return registry


_REGISTRY = None


def validator_for(schema_name: str) -> Draft202012Validator:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _registry()
    schema = json.loads((SCHEMAS / f"{schema_name}.schema.json").read_text())
    return Draft202012Validator(schema, registry=_REGISTRY, format_checker=FormatChecker())


def schema_errors(schema_name: str, data: dict, where: str) -> list[str]:
    errors = []
    for err in sorted(validator_for(schema_name).iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        errors.append(f"{where}: {loc}: {err.message}")
    return errors


def load_catalog() -> dict | None:
    """wiki/catalog.json of the factory: the project, FORJATE_ROOT, or the checkout this plugin lives in."""
    for root in (REPO, Path(os.environ["FORJATE_ROOT"]) if os.environ.get("FORJATE_ROOT") else None,
                 Path(__file__).resolve().parents[4]):
        if root and (root / "wiki" / "catalog.json").is_file():
            return json.loads((root / "wiki" / "catalog.json").read_text())
    return None


def stage_components(decisions: dict[str, dict], stage: str) -> list[str]:
    """Every component some record chooses at exactly this stage, in record order, without duplicates.

    A stage overlay is built from this set alone. A Crawl choice absent from every Walk record is
    superseded (another component covers its capability at Walk) or dropped; it is never carried
    forward. The assembly and the validator read the same set, so what the validator checks is what
    the overlay runs."""
    out: list[str] = []
    for d in decisions.values():
        for c in ((d.get("spec") or {}).get("stages") or {}).get(stage, {}) and (d["spec"]["stages"][stage].get("choice") or []):
            if c not in out:
                out.append(c)
    return out


def superseded_components(decisions: dict[str, dict], stage: str, catalog: dict | None) -> list[tuple[str, str, list[str]]]:
    """(component, previous stage, replacements) for every component chosen at the previous in-scope
    stage and absent at this one; replacements are the components of this stage that share a
    capability with it per the catalog (empty when nothing covers it any more)."""
    stages_with_records = [s for s in STAGES if any(s in ((d.get("spec") or {}).get("stages") or {}) for d in decisions.values())]
    if stage not in stages_with_records or stages_with_records.index(stage) == 0:
        return []
    prev = stages_with_records[stages_with_records.index(stage) - 1]
    caps = {c["path"]: set(c.get("capabilities") or []) for c in (catalog or {}).get("components") or []}
    now = stage_components(decisions, stage)
    out = []
    for c in stage_components(decisions, prev):
        if c in now:
            continue
        out.append((c, prev, [n for n in now if caps.get(c) and caps.get(c) & caps.get(n, set())]))
    return out


def component_exists(component: str) -> bool:
    """A catalog component is a directory under k8s/components/ with a kustomization."""
    return (COMPONENTS / component / "kustomization.yaml").is_file()


def report(errors: list[str], warnings: list[str] | None = None) -> int:
    for w in warnings or []:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    return 1 if errors else 0


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)
