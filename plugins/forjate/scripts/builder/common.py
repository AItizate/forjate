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
