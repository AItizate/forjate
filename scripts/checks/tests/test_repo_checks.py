"""Tests for scripts/checks/repo_checks.py, on small fixture trees: each check flags the offender it exists
for, leaves the clean case alone, and the baseline ratchets (a new offender fails, a fixed one must leave)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("repo_checks", HERE.parent / "repo_checks.py")
rc = importlib.util.module_from_spec(spec)
sys.modules["repo_checks"] = rc
spec.loader.exec_module(rc)

CONTRACT = {"protocol": "s3", "secret_keys": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
            "config_keys": ["AWS_ENDPOINT_URL_S3", "S3_HOST", "S3_PORT", "S3_USE_TLS", "AWS_REGION", "S3_BUCKET", "AWS_CA_BUNDLE"],
            "config_key_patterns": ["S3_BUCKET_[A-Z0-9_]+"]}


def _wiring(**kw) -> dict:
    w = {"service": None, "label": None, "secret": None, "protocol": "tcp", "consumes": []}
    w.update(kw)
    return w


def _repo(tmp_path: Path, files: dict[str, str], components: list[dict]) -> Path:
    for p, body in files.items():
        f = tmp_path / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    (tmp_path / "wiki").mkdir(exist_ok=True)
    caps = {"object-store": {"summary": "s", "asked_by": ["data-store"], "contract": CONTRACT},
            "artifact-store": {"summary": "a", "asked_by": ["data-store"]}}
    (tmp_path / "wiki" / "catalog.json").write_text(json.dumps({"capabilities": caps, "components": components}))
    return tmp_path


STORE = {"path": "apps/store/blob", "capabilities": ["object-store", "artifact-store"], "images": ["registry.example/acme/blobd:1.2"],
         "wiring": _wiring(service="blobd", label="blobd", protocol="s3", secret={"name": "blobd-root", "keys": ["ROOT"]})}


def _consumer(path: str = "apps/x/app", **wiring) -> dict:
    return {"path": path, "capabilities": [], "images": [], "wiring": _wiring(**wiring)}


# --- coupling -------------------------------------------------------------------------------------------------

def test_coupling_flags_provider_host_secret_image_and_literal_s3_keys(tmp_path: Path):
    repo = _repo(tmp_path, {
        "k8s/components/apps/x/app/deployment.yaml": (
            "apiVersion: apps/v1\nkind: Deployment\nmetadata: {name: app}\nspec:\n  template:\n    spec:\n      containers:\n"
            "        - name: app\n          image: app:1\n          env:\n"
            "            - {name: BLOBD_URL, value: 'http://blobd:8333'}\n"          # provider host as a value
            "            - {name: USE_BLOBD, value: 'true'}\n"                       # app-owned name, harmless value
            "            - {name: BLOBD_ACCESS_KEY, value: admin}\n"                 # literal S3 credential
            "            - name: BLOBD_SECRET_KEY\n              valueFrom: {secretKeyRef: {name: app-s3, key: AWS_SECRET_ACCESS_KEY}}\n"),
        "k8s/components/apps/x/app/README.md": "Stores blobs in Blobd.\n",
        "k8s/components/apps/x/app/sidecar.yaml": "kind: Pod\nspec:\n  containers: [{name: s, image: 'registry.example/acme/blobd:1.2'}]\n",
        "k8s/components/apps/x/app/secret-ref.yaml": "kind: ConfigMap\ndata:\n  SECRET: blobd-root\n",
        "k8s/components/apps/store/blob/kustomization.yaml": "resources: []\n# blobd itself may name blobd\n",
    }, [STORE, _consumer()])
    off = rc.coupling_offenders(repo)
    dep = off["k8s/components/apps/x/app/deployment.yaml"]
    assert any("blobd" in r and "BLOBD_URL" in r for r in dep)
    assert any("literal S3 credential" in r and "BLOBD_ACCESS_KEY" in r for r in dep)
    assert not any("USE_BLOBD" in r or "BLOBD_SECRET_KEY" in r for r in dep)
    assert "k8s/components/apps/x/app/README.md" in off
    assert "k8s/components/apps/x/app/sidecar.yaml" in off
    assert "k8s/components/apps/x/app/secret-ref.yaml" in off
    assert not any(p.startswith("k8s/components/apps/store/") for p in off)


def test_coupling_ignores_env_names_comments_and_longer_tokens(tmp_path: Path):
    repo = _repo(tmp_path, {
        "k8s/components/apps/x/app/deployment.yaml": (
            "# talks to blobd in the default setup\nkind: Deployment\nspec:\n  template:\n    spec:\n      containers:\n"
            "        - name: app\n          image: app:1\n          env:\n"
            "            - name: BLOBD_ADDRESS\n              valueFrom: {configMapKeyRef: {name: app-s3, key: S3_HOST}}\n"
            "            - {name: BUCKET, value: blobd-assets}\n"
            "            - {name: FILE, value: values-blobd-backend.yaml}\n"),
        "k8s/components/apps/x/app/secret.yaml": "kind: Secret\nstringData:\n  APP_S3_ACCESS_KEY: changeme\n",
    }, [STORE, _consumer()])
    assert rc.coupling_offenders(repo) == {}


def test_a_nested_component_is_scanned_as_itself_not_as_its_parent(tmp_path: Path):
    """A provider nested under a consumer's directory keeps its exemption, and vice versa."""
    nested_store = dict(STORE, path="apps/x/app/store")
    repo = _repo(tmp_path, {"k8s/components/apps/x/app/store/pod.yaml": "kind: Pod\nspec: {containers: [{name: b, image: 'x:1', args: [blobd]}]}\n",
                            "k8s/components/apps/x/app/cm.yaml": "kind: ConfigMap\ndata: {URL: 'http://blobd:8333'}\n"},
                [_consumer(), nested_store])
    assert set(rc.coupling_offenders(repo)) == {"k8s/components/apps/x/app/cm.yaml"}


# --- ratchet --------------------------------------------------------------------------------------------------

def test_ratchet_fails_on_a_new_offender_and_on_a_baseline_entry_that_no_longer_offends(tmp_path: Path):
    baseline = tmp_path / "x.baseline"
    baseline.write_text("# header\nk8s/a.yaml\nk8s/b.yaml\n")
    new, gone = rc.ratchet({"k8s/a.yaml", "k8s/c.yaml"}, rc.read_baseline(baseline))
    assert new == ["k8s/c.yaml"] and gone == ["k8s/b.yaml"]
    assert rc.ratchet({"k8s/a.yaml", "k8s/b.yaml"}, rc.read_baseline(baseline)) == ([], [])


# --- contract -------------------------------------------------------------------------------------------------

def test_contract_accepts_contract_keys_and_role_buckets(tmp_path: Path):
    ok = [{"protocol": "s3", "secret": "app-s3", "keys": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_BUCKET_MEDIA"], "format": "env"}]
    repo = _repo(tmp_path, {}, [STORE, _consumer(consumes=ok)])
    errors, n = rc.contract_errors(repo)
    assert errors == [] and n == 1


def test_contract_rejects_foreign_keys_and_an_unknown_protocol(tmp_path: Path):
    bad = [{"protocol": "s3", "secret": "app-s3", "keys": ["MINIO_ROOT_USER"], "format": "env"},
           {"protocol": "ftp", "secret": "app-ftp", "keys": ["X"], "format": "env"}]
    repo = _repo(tmp_path, {}, [STORE, _consumer(consumes=bad)])
    errors, n = rc.contract_errors(repo)
    assert n == 1
    assert any("MINIO_ROOT_USER" in e for e in errors)
    assert any("'ftp'" in e for e in errors)


def test_contract_needs_the_capability_to_declare_it(tmp_path: Path):
    repo = _repo(tmp_path, {}, [STORE])
    cat = json.loads((repo / "wiki" / "catalog.json").read_text())
    del cat["capabilities"]["object-store"]["contract"]["secret_keys"]
    (repo / "wiki" / "catalog.json").write_text(json.dumps(cat))
    errors, _ = rc.contract_errors(repo)
    assert any("secret_keys" in e for e in errors)


# --- pins -----------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("body,flagged", [
    ("resources:\n  - github.com/acme/operator\n", True),
    ("resources:\n  - github.com/acme/operator?ref=main\n", True),
    ("resources:\n  - github.com/acme/operator?ref=v7.1.1\n", False),
    ("resources:\n  - https://github.com/acme/op?ref=0123abc\n", False),
    ("resources:\n  - https://raw.githubusercontent.com/acme/op/master/deploy.yaml\n", True),
    ("resources:\n  - https://github.com/acme/op/releases/download/v1.2.3/op.yaml\n", False),
    ("resources:\n  - ../local\n  - deployment.yaml\n", False),
    ("helmCharts:\n  - {name: op, repo: https://charts.example, version: 1.2.3}\n", False),
    ("helmCharts:\n  - {name: op, repo: https://charts.example}\n", True),
    ("helmCharts:\n  - {name: op, repo: https://charts.example, version: '^1.2'}\n", True),
    ("images:\n  - {name: app, newTag: latest}\n", True),
])
def test_pins_in_kustomizations(tmp_path: Path, body: str, flagged: bool):
    repo = _repo(tmp_path, {"k8s/components/apps/x/app/kustomization.yaml": body}, [])
    assert bool(rc.pin_offenders(repo)) is flagged, rc.pin_offenders(repo)


@pytest.mark.parametrize("image,flagged", [
    ("app:1.2.3", False), ("registry.example:5000/app:1.2", False), ("app@sha256:" + "a" * 64, False),
    ("app:latest", True), ("app", True), ("registry.example:5000/app", True),
])
def test_pins_in_pod_and_custom_resource_images(tmp_path: Path, image: str, flagged: bool):
    pod = f"kind: Pod\nspec:\n  containers: [{{name: a, image: '{image}'}}]\n"
    cr = f"apiVersion: acme.example/v1\nkind: Store\nspec:\n  image: '{image}'\n"
    repo = _repo(tmp_path, {"k8s/base/apps/a/pod.yaml": pod, "k8s/components/apps/x/cr.yaml": cr}, [])
    assert len(rc.pin_offenders(repo)) == (2 if flagged else 0)


def test_pins_in_helm_values_image_maps(tmp_path: Path):
    repo = _repo(tmp_path, {"k8s/components/apps/x/values.yaml": "image:\n  repository: acme/app\n  tag: latest\n",
                            "k8s/components/apps/y/values.yaml": "image:\n  repository: acme/app\n  tag: 1.2.3\n"}, [])
    assert list(rc.pin_offenders(repo)) == ["k8s/components/apps/x/values.yaml"]
