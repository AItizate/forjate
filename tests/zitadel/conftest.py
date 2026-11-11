"""Shared fixtures for the zitadel component tests.

Render tests need `kustomize` and `helm` on PATH (the same tools CI installs) and
network access the first time, to pull the pinned chart. They skip, loudly, when
the tools are missing, so a laptop without them still runs the script tests.
"""
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "k8s/components/apps/auth/zitadel"
BUNDLE = ROOT / "k8s/components/bundles/zitadel-stack"
EXAMPLE = ROOT / "docs/examples/zitadel-tenant"


def render(path: Path) -> list[dict]:
    """kustomize build --enable-helm, parsed into a list of objects."""
    if not (shutil.which("kustomize") and shutil.which("helm")):
        pytest.skip("kustomize and helm are required for render tests")
    out = subprocess.run(
        ["kustomize", "build", "--enable-helm", str(path)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert out.returncode == 0, f"kustomize build {path} failed:\n{out.stderr}"
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def by_kind(objs, kind, name=None):
    found = [o for o in objs if o["kind"] == kind and (name is None or o["metadata"]["name"] == name)]
    assert found, f"no {kind} {name or ''} in the render"
    return found if name is None else found[0]


@pytest.fixture(scope="session")
def bundle():
    return render(BUNDLE)


@pytest.fixture(scope="session")
def example():
    return render(EXAMPLE)
