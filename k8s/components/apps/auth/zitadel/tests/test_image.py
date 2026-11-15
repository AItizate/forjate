"""The bootstrap Job runs a digest-pinned image with its dependencies baked in (M7).

The Job used to `pip install` its dependencies at start, which needs egress to PyPI
and fails under a default-deny NetworkPolicy. These tests pin the replacement: no
runtime install, nothing in the Job spec that needs the network besides Zitadel and
the Kubernetes API, an image referenced by digest only, the same (or a stricter)
securityContext, and an image definition (image/Dockerfile) that keeps the install
guarantees and ships no installer or shell.
"""
import hashlib
import os
import re

import yaml

from conftest import COMPONENT, ROOT, by_kind, render

BOOTSTRAP = COMPONENT / "bootstrap"
DOCKERFILE = (BOOTSTRAP / "image/Dockerfile").read_text()
PUBLISHED = yaml.safe_load((BOOTSTRAP / "image/published.yaml").read_text())
KUSTOMIZATION = yaml.safe_load((BOOTSTRAP / "kustomization.yaml").read_text())
PLACEHOLDER = "sha256:" + "0" * 64
DIGEST_REF = re.compile(r"^[a-z0-9.\-/]+@sha256:[0-9a-f]{64}$")
INSTALLERS = re.compile(r"\b(pip3?|uv|poetry|apk|apt(-get)?|npm|curl|wget)\b")


def pod_spec(objs):
    return by_kind(objs, "Job", "zitadel-bootstrap")["spec"]["template"]["spec"]


def images_entry():
    [entry] = [i for i in KUSTOMIZATION["images"] if i["name"] == PUBLISHED["image"]]
    return entry


# ----------------------------------------------------------- the rendered Job

def test_job_installs_nothing_at_start(bundle):
    spec = pod_spec(bundle)
    assert not spec.get("initContainers"), "dependencies are baked into the image, no init container"
    for c in spec["containers"]:
        argv = " ".join(c.get("command", []) + c.get("args", []))
        assert not INSTALLERS.search(argv), f"{c['name']} runs an installer: {argv}"
        assert c["command"] == ["python", "/scripts/bootstrap.py"]


def test_job_spec_needs_no_network_besides_zitadel_and_the_api(bundle):
    spec = pod_spec(bundle)
    assert [c["name"] for c in spec["containers"]] == ["bootstrap"]
    env = {e["name"] for c in spec["containers"] for e in c.get("env", [])}
    offenders = {n for n in env if re.match(r"(PIP_|UV_|HTTPS?_PROXY|NO_PROXY|PYTHONPATH$)", n)}
    assert not offenders, f"package index, proxy or deps path in the Job env: {offenders}"
    # No volume to install into: the only writable volume is /tmp.
    assert {v["name"] for v in spec["volumes"]} == {"bootstrap-config", "bootstrap-scripts", "admin-sa-key", "tmp"}
    assert not spec.get("hostNetwork")


def test_job_image_is_pinned_by_digest_only(bundle, example):
    for objs in (bundle, example):
        for c in pod_spec(objs)["containers"]:
            assert DIGEST_REF.match(c["image"]), f"{c['image']} is not a digest-only reference"
            assert c["image"].startswith(PUBLISHED["image"] + "@")


def test_security_context_is_unchanged_or_stricter(bundle):
    """The exact hardening the Job had before the image moved (M3/M7 review)."""
    spec = pod_spec(bundle)
    assert spec["securityContext"] == {
        "runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532, "fsGroup": 65532,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    for c in spec["containers"]:
        sc = c["securityContext"]
        assert sc["allowPrivilegeEscalation"] is False
        assert sc["readOnlyRootFilesystem"] is True
        assert sc["capabilities"] == {"drop": ["ALL"]}
        assert not sc.get("privileged")
        assert "runAsUser" not in sc or sc["runAsUser"] != 0


def test_a_tenant_mirror_keeps_the_digest(tmp_path):
    overlay = tmp_path / "mirror"
    overlay.mkdir()
    (overlay / "kustomization.yaml").write_text(yaml.safe_dump({
        # kustomize refuses absolute resource paths
        "resources": [os.path.relpath(BOOTSTRAP, overlay)],
        "images": [{"name": PUBLISHED["image"], "newName": "registry.example.com/mirror/zitadel-bootstrap"}],
    }))
    [c] = pod_spec(render(overlay))["containers"]
    assert c["image"] == f"registry.example.com/mirror/zitadel-bootstrap@{images_entry()['digest']}"


# ------------------------------------------------------- the image definition

def test_dockerfile_base_is_pinned_by_digest_in_every_stage():
    [base] = re.findall(r"^ARG PYTHON_IMAGE=(\S+)$", DOCKERFILE, re.M)
    assert re.fullmatch(r"python:[\w.\-]+@sha256:[0-9a-f]{64}", base), base
    froms = re.findall(r"^FROM (\S+)", DOCKERFILE, re.M)
    assert froms and all(f == "${PYTHON_IMAGE}" for f in froms), froms


def test_dockerfile_ships_no_installer_or_shell_and_runs_non_root():
    final = DOCKERFILE.split("\nFROM ")[-1]
    for path in ("site-packages/pip", "ensurepip", "/usr/local/bin/pip*", "/sbin/apk", "/bin/busybox"):
        assert path in final, f"the final stage must remove {path}"
    assert re.search(r"^USER 65532:65532$", final, re.M)
    assert "requirements.txt" not in final, "the final stage copies the installed deps, it installs nothing"


def test_published_record_matches_the_kustomization_and_the_build_inputs():
    """A change to requirements.txt or to the base image needs a new image: the
    record of what the published digest was built from must follow."""
    assert images_entry()["digest"] == PUBLISHED["digest"]
    assert set(images_entry()) == {"name", "digest"}, "digest only, no tag that could drift from it"
    sha = hashlib.sha256((BOOTSTRAP / "requirements.txt").read_bytes()).hexdigest()
    assert PUBLISHED["requirements_sha256"] == sha, "requirements.txt changed: rebuild and republish the image"
    [base] = re.findall(r"^ARG PYTHON_IMAGE=(\S+)$", DOCKERFILE, re.M)
    assert PUBLISHED["base"] == base, "the Dockerfile base changed: rebuild and republish the image"


def test_the_shipped_digest_is_not_the_placeholder():
    """Fails until the image is published and its digest written in both places:
    an all-zero digest renders fine but the Job would never pull."""
    assert images_entry()["digest"] != PLACEHOLDER, (
        "the bootstrap image digest is still the placeholder: publish the image and write its digest "
        "(docs/apps/zitadel.md, 'Bootstrap image') before this ships")
