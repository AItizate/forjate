"""Tests of the deterministic gates (#41): every script in scripts/gates/checks/*.sh with a fixture that
passes and one that fails, and the runner (scripts/gates/gates.py) around them.

A gate that never fails is decoration: the #21 nightly failed on a yq expression that read differently
across 4.x releases and on a Job that did not wait for its dependency, and no check had ever been shown
to fail. Each case here builds a throwaway use case, runs the real script with the contract gates.py sets
(UC_DIR, STAGE_DIR, STAGE, ...) and asserts the exit code and, for a failure, the reason it names.

The toolchain is the pinned one (.github/toolchain.env): the scripts refuse another yq, so run
scripts/toolchain/install.sh once. kustomize (or kubectl), kubeconform and git are needed by some cases;
CI installs them, a laptop without one skips that case (in CI a missing tool fails instead).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest
import yaml

HERE = Path(__file__).resolve().parent
BUILDER = HERE.parent
REPO = BUILDER.parents[3]
CHECKS = REPO / "scripts" / "gates" / "checks"
GATES_PY = REPO / "scripts" / "gates" / "gates.py"
TOOLCHAIN_DIR = REPO / "scripts" / "toolchain"
FIXTURE = HERE / "fixtures" / "db-migration-a-to-b"
USECASES = REPO / "k8s" / "overlays" / "usecases"

PASS, FAIL, SKIP = 0, 1, 2


# ------------------------------------------------------------------------------------------ helpers
def need(*tools: str, any_of: bool = False) -> None:
    """Skip locally, fail in CI, when a tool the case needs is missing."""
    found = [shutil.which(t) for t in tools]
    ok = any(found) if any_of else all(found)
    if not ok:
        msg = f"{' or '.join(tools) if any_of else ' and '.join(tools)} not installed"
        if os.environ.get("CI"):
            pytest.fail(msg)
        pytest.skip(msg)


def need_kustomize() -> None:
    need("kustomize", "kubectl", any_of=True)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def script(path: Path, body: str) -> Path:
    write(path, "#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def doc(kind: str, name: str, namespace: str | None = None, api: str = "v1", **rest) -> dict:
    md: dict = {"name": name}
    if namespace:
        md["namespace"] = namespace
    return {"apiVersion": api, "kind": kind, "metadata": md, **rest}


class UC:
    """A throwaway use case named demo, laid out the way gates.py's contract describes it."""

    name = "demo"
    ns = "uc-demo"

    def __init__(self, tmp: Path, stage: str = "walk"):
        self.root = tmp / self.name
        self.root.mkdir()
        self.stage = stage
        self.bin = tmp / "bin"   # fake executables first on PATH (kubectl for the live-log checks)
        self.bin.mkdir()
        self.extra_env: dict[str, str] = {}

    @property
    def stage_dir(self) -> Path:
        return self.root / "stages" / self.stage

    def record(self, area: str, **settings) -> None:
        """Merge settings (and choice=[...]) into .builder/decisions/<area>.yaml at self.stage."""
        p = self.root / ".builder" / "decisions" / f"{area}.yaml"
        d = yaml.safe_load(p.read_text()) if p.exists() else {"spec": {"stages": {}}}
        st = d["spec"]["stages"].setdefault(self.stage, {"settings": {}})
        for key in ("choice", "psa_exceptions"):  # stage keys; everything else is a setting
            if key in settings:
                st[key] = settings.pop(key)
        st.setdefault("settings", {}).update(settings)
        write(p, yaml.safe_dump(d, sort_keys=False))

    def build_stage(self, *docs: dict) -> None:
        """stages/<stage>/ as a kustomization over one file holding the documents."""
        write(self.stage_dir / "all.yaml", yaml.safe_dump_all(docs, sort_keys=False))
        write(self.stage_dir / "kustomization.yaml", "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - all.yaml\n")

    def env(self, **extra) -> dict[str, str]:
        e = dict(os.environ)
        e.pop("FORJATE_TOOLCHAIN", None)  # a case never inherits the escape hatch
        e.update(
            REPO=str(REPO), UC_NAME=self.name, UC_DIR=str(self.root), UC_NS=self.ns, TRANSITION="crawl->walk",
            SOURCE_STAGE="crawl", STAGE=self.stage, STAGE_DIR=str(self.stage_dir), GATE_ID="G-TEST-1",
            GATE_TEXT="test", CHECKS_DIR=str(CHECKS),
            # python3 resolves to the interpreter running the tests: pyyaml and jsonschema are there
            PATH=os.pathsep.join([str(self.bin), str(Path(sys.executable).parent), e.get("PATH", "")]),
        )
        e.update(self.extra_env)
        e.update(extra)
        return e

    def run(self, check: str, **extra_env) -> tuple[int, str]:
        p = subprocess.run(["bash", str(CHECKS / f"{check}.sh")], env=self.env(**extra_env), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=REPO)
        return p.returncode, p.stdout.strip()


@pytest.fixture
def uc(tmp_path: Path) -> UC:
    return UC(tmp_path)


# ------------------------------------------------------------------ app fixtures (pytest-based checks)
def make_app(uc: UC, tests: str) -> None:
    """A minimal app/ whose tests run through app-tests.sh. The venv is a stub around the interpreter running
    these tests: app-tests.sh would otherwise create one and pip-install the app from the network."""
    app = uc.root / "app"
    write(app / "pyproject.toml", '[project]\nname = "demo"\nversion = "0"\n[tool.pytest.ini_options]\nmarkers = ["eval", "injection", "redaction"]\n')
    write(app / "tests" / "test_demo.py", tests)
    script(app / ".venv" / "bin" / "python", f'exec "{sys.executable}" "$@"\n')
    script(app / ".venv" / "bin" / "pip", "exit 0\n")


TEST_OK = "def test_ok():\n    assert True\n"
TEST_BAD = "def test_bad():\n    assert False, 'regression'\n"


def marked(marker: str, ok: bool) -> str:
    return f"import pytest\n\n@pytest.mark.{marker}\n" + (TEST_OK if ok else TEST_BAD)


# ---------------------------------------------------------------------------------- live-log checks
def fake_live_cluster(uc: UC, logs: str) -> None:
    """kubectl that says the namespace exists and prints canned logs."""
    kc = write(uc.root.parent / "kubeconfig", "apiVersion: v1\nkind: Config\n")
    write(uc.root.parent / "logs.txt", logs)
    script(uc.bin / "kubectl", 'case " $* " in\n  *" get ns "*) exit 0 ;;\n  *" logs "*) cat "' + str(uc.root.parent / "logs.txt") + '" ;;\nesac\n')
    uc.extra_env["KUBECONFIG_UC"] = str(kc)


NO_LIVE = {"KUBECONFIG_UC": "/nonexistent/kubeconfig"}


# ------------------------------------------------------------------------------------ the case table
@dataclass
class Case:
    check: str
    kind: str                         # "pass" | "fail" | "skip"
    build: Callable[[UC], None]
    contains: str                     # a phrase the script prints: the reason it passed, failed or skipped
    env: dict | None = None
    needs: Callable[[], None] | None = None
    id: str = ""

    def __post_init__(self):
        self.id = self.id or f"{self.check}-{self.kind}"


CASES: list[Case] = []


def case(check: str, kind: str, contains: str, *, env: dict | None = None, needs: Callable[[], None] | None = None, id: str = ""):
    def deco(fn: Callable[[UC], None]):
        CASES.append(Case(check, kind, fn, contains, env, needs, id))
        return fn
    return deco


# --- app-tests / eval-regression / injection-suite / redaction-check ---------------------------------
@case("app-tests", "pass", "app tests passed")
def _(uc): make_app(uc, TEST_OK)


@case("app-tests", "fail", "app tests failed")
def _(uc): make_app(uc, TEST_BAD)


@case("app-tests", "skip", "no app/")
def _(uc): pass


for _check, _marker in (("eval-regression", "eval"), ("injection-suite", "injection"), ("redaction-check", "redaction")):
    def _mk(marker=_marker):
        return (lambda uc: make_app(uc, marked(marker, True)),
                lambda uc: make_app(uc, marked(marker, False)),
                lambda uc: make_app(uc, TEST_OK))
    _ok, _bad, _unmarked = _mk()
    CASES.append(Case(_check, "pass", _ok, "app tests passed"))
    CASES.append(Case(_check, "fail", _bad, "app tests failed"))
    CASES.append(Case(_check, "skip", _unmarked, f"no tests marked '{_marker}'"))


# --- argocd-revision-check -------------------------------------------------------------------------------
def application(revision: str, self_heal: bool) -> dict:
    return doc("Application", "demo", "argocd", api="argoproj.io/v1alpha1", spec={
        "source": {"repoURL": "ssh://git@github.com/acme/iac.git", "targetRevision": revision, "path": "k8s"},
        "syncPolicy": {"automated": {"selfHeal": self_heal}}})


@case("argocd-revision-check", "pass", "track a tag")
def _(uc): uc.build_stage(application("v1.2.0", True))


@case("argocd-revision-check", "fail", "targetRevision 'main' is a branch", id="argocd-revision-check-fail-branch")
def _(uc): uc.build_stage(application("main", True))


@case("argocd-revision-check", "fail", "selfHeal is false", id="argocd-revision-check-fail-selfheal")
def _(uc): uc.build_stage(application("v1.2.0", False))


# --- auth-check ------------------------------------------------------------------------------------------
def ingress(name: str, middleware: str | None) -> dict:
    ann = {"traefik.ingress.kubernetes.io/router.middlewares": middleware} if middleware else {}
    return doc("Ingress", name, UC.ns, api="networking.k8s.io/v1", spec={"rules": [{"host": "demo.example.com"}]}) | (
        {"metadata": {"name": name, "namespace": UC.ns, **({"annotations": ann} if ann else {})}})


@case("auth-check", "pass", "behind the auth middleware chain", needs=need_kustomize)
def _(uc):
    uc.record("security", auth_in_front="oauth2-proxy")
    # the documents around the Ingress carry no annotations: an empty field must not shift the columns of the row
    uc.build_stage(doc("ConfigMap", "cfg", UC.ns, data={"a": "b"}), ingress("web", "uc-demo-oauth2-proxy@kubernetescrd"),
                   ingress("login-gotrue", None))


@case("auth-check", "fail", "Ingress web has no auth middleware", needs=need_kustomize)
def _(uc):
    uc.record("security", auth_in_front="oauth2-proxy")
    uc.build_stage(doc("ConfigMap", "cfg", UC.ns, data={"a": "b"}), ingress("web", None))


@case("auth-check", "fail", "no Ingress is rendered", needs=need_kustomize, id="auth-check-fail-no-ingress")
def _(uc):
    uc.record("security", auth_in_front="oauth2-proxy")
    uc.build_stage(doc("ConfigMap", "cfg", UC.ns, data={"a": "b"}))


@case("auth-check", "pass", "auth_in_front is none", needs=need_kustomize, id="auth-check-pass-none")
def _(uc):
    uc.record("security", auth_in_front="none")
    uc.build_stage(ingress("web", None))


# --- env-example-check -----------------------------------------------------------------------------------
KUSTOMIZATION_WITH_SECRET = "secretGenerator:\n  - name: app-secret\n    envs:\n      - secrets/app.env\n"
EXAMPLE_FULL = "# To generate: openssl rand -hex 32\n# To seal: kubeseal --format yaml < secret.yaml\nTOKEN=CHANGE_ME\n"


@case("env-example-check", "pass", "carry a .env.example")
def _(uc):
    write(uc.root / "kustomization.yaml", KUSTOMIZATION_WITH_SECRET)
    write(uc.root / "secrets" / "app.env.example", EXAMPLE_FULL)


@case("env-example-check", "fail", "missing", id="env-example-check-fail-missing-example")
def _(uc): write(uc.root / "kustomization.yaml", KUSTOMIZATION_WITH_SECRET)


@case("env-example-check", "fail", "lacks '# To seal:' header", id="env-example-check-fail-no-recipe")
def _(uc):
    write(uc.root / "kustomization.yaml", KUSTOMIZATION_WITH_SECRET)
    write(uc.root / "secrets" / "app.env.example", "# To generate: openssl rand -hex 32\nTOKEN=CHANGE_ME\n")


@case("env-example-check", "fail", "a .env file is tracked by git", needs=lambda: need("git"), id="env-example-check-fail-tracked-env")
def _(uc):
    write(uc.root / "kustomization.yaml", KUSTOMIZATION_WITH_SECRET)
    write(uc.root / "secrets" / "app.env.example", EXAMPLE_FULL)
    write(uc.root / "secrets" / "app.env", "TOKEN=abc\n")
    for args in (["init", "-q"], ["add", "-f", "secrets/app.env"]):
        subprocess.run(["git", "-C", str(uc.root), *args], check=True, capture_output=True)


# --- image-policy-check ----------------------------------------------------------------------------------
def workload(image: str) -> dict:
    return doc("Deployment", "api", UC.ns, api="apps/v1", spec={"template": {"spec": {"containers": [{"name": "api", "image": image}]}}}) | {
        "metadata": {"name": "api", "namespace": UC.ns, "labels": {"forjate.io/usecase": UC.name}}}


@case("image-policy-check", "pass", "pinned by digest", needs=need_kustomize)
def _(uc):
    uc.record("security", image_policy="pinned-digest")
    uc.build_stage(workload("ghcr.io/acme/api@sha256:" + "a" * 64))


@case("image-policy-check", "fail", "is not pinned by digest", needs=need_kustomize)
def _(uc):
    uc.record("security", image_policy="pinned-digest")
    uc.build_stage(workload("ghcr.io/acme/api:1.2.3"))


@case("image-policy-check", "pass", "image_policy is any", needs=need_kustomize, id="image-policy-check-pass-any")
def _(uc):
    uc.record("security", image_policy="any")
    uc.build_stage(workload("ghcr.io/acme/api:latest"))


# --- licence-inventory -----------------------------------------------------------------------------------
@case("licence-inventory", "pass", "all in the licence inventory")
def _(uc):
    uc.record("compliance", licences=["postgres", "minio"], choice=["postgres"])
    uc.record("architecture", choice=["minio"])


@case("licence-inventory", "fail", "redis not in the licence inventory")
def _(uc):
    uc.record("compliance", licences=["postgres"], choice=["postgres"])
    uc.record("architecture", choice=["redis"])


@case("licence-inventory", "skip", "no compliance record")
def _(uc): uc.record("architecture", choice=["redis"])


# --- litellm-egress-check --------------------------------------------------------------------------------
LITELLM_LOCAL = "model_list:\n  - model_name: m\n    litellm_params:\n      model: ollama/qwen\n      api_base: http://ollama-service.ai-tools.svc.cluster.local:11434\n"


@case("litellm-egress-check", "pass", "only to in-cluster endpoints")
def _(uc): write(uc.root / "configs" / "litellm-config.yaml", LITELLM_LOCAL)


@case("litellm-egress-check", "fail", "leaves the cluster", id="litellm-egress-check-fail-external-base")
def _(uc): write(uc.root / "configs" / "litellm-config.yaml", LITELLM_LOCAL.replace("http://ollama-service.ai-tools.svc.cluster.local:11434", "https://api.openai.com/v1"))


@case("litellm-egress-check", "fail", "provider key literal", id="litellm-egress-check-fail-key")
def _(uc): write(uc.root / "configs" / "litellm-config.yaml", LITELLM_LOCAL + "      api_key: sk-live-0123456789abcdef\n")


@case("litellm-egress-check", "skip", "no LiteLLM config")
def _(uc): pass


# --- log-content-scan / log-dataclass-scan -----------------------------------------------------------------
CLEAN_LOGS = "intake_done data_class=financial processed=20\nreview_queued data_class=financial reason=amount_mismatch\n"


@case("log-content-scan", "pass", "none carry IBAN, email or phone")
def _(uc): fake_live_cluster(uc, CLEAN_LOGS)


@case("log-content-scan", "fail", "look like payload", id="log-content-scan-fail-email")
def _(uc): fake_live_cluster(uc, CLEAN_LOGS + "supplier contact ana@proveedor.example for invoice 17\n")


@case("log-content-scan", "fail", "look like payload", id="log-content-scan-fail-iban")
def _(uc): fake_live_cluster(uc, CLEAN_LOGS + "paid to ES9121000418450200051332\n")


@case("log-content-scan", "skip", "no live environment", env=NO_LIVE)
def _(uc): pass


@case("log-dataclass-scan", "pass", "carry data_class=")
def _(uc): fake_live_cluster(uc, CLEAN_LOGS)


@case("log-dataclass-scan", "fail", "no log line carries data_class=", id="log-dataclass-scan-fail-no-class")
def _(uc): fake_live_cluster(uc, "intake_done processed=20\n")


@case("log-dataclass-scan", "fail", "look like payload", id="log-dataclass-scan-fail-payload")
def _(uc): fake_live_cluster(uc, CLEAN_LOGS + "contact ana@proveedor.example\n")


@case("log-dataclass-scan", "skip", "no live environment", env=NO_LIVE)
def _(uc): pass


# --- netpol-check / netpol-matrix-check --------------------------------------------------------------------
def netpols(*, dns: bool = True, egress: bool = True) -> list[dict]:
    out = [doc("NetworkPolicy", "default-deny", UC.ns, api="networking.k8s.io/v1", spec={"podSelector": {}, "policyTypes": ["Ingress", "Egress"] if egress else ["Ingress"]})]
    if dns:
        out.append(doc("NetworkPolicy", "allow-dns", UC.ns, api="networking.k8s.io/v1", spec={"podSelector": {}, "policyTypes": ["Egress"], "egress": [{"ports": [{"port": 53, "protocol": "UDP"}]}]}))
    return out


@case("netpol-check", "pass", "default-deny + allow-dns", needs=need_kustomize)
def _(uc): uc.build_stage(*netpols())


@case("netpol-check", "fail", "no allow-dns", needs=need_kustomize)
def _(uc): uc.build_stage(*netpols(dns=False))


@case("netpol-check", "fail", "expected Ingress and Egress", needs=need_kustomize, id="netpol-check-fail-ingress-only")
def _(uc): uc.build_stage(*netpols(egress=False))


@case("netpol-check", "fail", "no policy mentions imap.proveedor.example", needs=need_kustomize, id="netpol-check-fail-allowlist")
def _(uc):
    uc.record("security", egress_allowlist=["imap.proveedor.example:993  # mailbox"])
    uc.build_stage(*netpols())


def per_workload_policy() -> dict:
    return doc("NetworkPolicy", "api-egress", UC.ns, api="networking.k8s.io/v1", spec={"podSelector": {"matchLabels": {"app": "api"}}, "policyTypes": ["Egress"]})


@case("netpol-matrix-check", "pass", "every workload has its own NetworkPolicy", needs=need_kustomize)
def _(uc):
    uc.record("security", egress_matrix="required")
    uc.record("architecture", workloads=["api"])
    uc.build_stage(*netpols(), per_workload_policy())


@case("netpol-matrix-check", "fail", "no NetworkPolicy selects app=worker", needs=need_kustomize)
def _(uc):
    uc.record("security", egress_matrix="required")
    uc.record("architecture", workloads=["api", "worker"])
    uc.build_stage(*netpols(), per_workload_policy())


@case("netpol-matrix-check", "skip", "not required")
def _(uc): uc.record("security", egress_matrix="none")


# --- psa-check ---------------------------------------------------------------------------------------------
def namespace(name: str, level: str | None) -> dict:
    return doc("Namespace", name) | {"metadata": {"name": name, **({"labels": {"pod-security.kubernetes.io/enforce": level}} if level else {})}}


@case("psa-check", "pass", "PSA enforce=restricted", needs=need_kustomize)
def _(uc):
    uc.record("security", psa_level="restricted")
    uc.build_stage(namespace(UC.ns, "restricted"))


@case("psa-check", "fail", "has no pod-security.kubernetes.io/enforce label", needs=need_kustomize)
def _(uc):
    uc.record("security", psa_level="restricted")
    uc.build_stage(namespace(UC.ns, None))


@case("psa-check", "fail", "enforce label is 'baseline', security record says 'restricted'", needs=need_kustomize, id="psa-check-fail-level")
def _(uc):
    uc.record("security", psa_level="restricted")
    uc.build_stage(namespace(UC.ns, "baseline"))


@case("psa-check", "fail", "enforces 'privileged', the security record's exception says 'baseline'", needs=need_kustomize, id="psa-check-fail-exception")
def _(uc):
    uc.record("security", psa_level="restricted", psa_exceptions=[{"namespace": "uc-demo-db", "level": "baseline"}])
    uc.build_stage(namespace(UC.ns, "restricted"), namespace("uc-demo-db", "privileged"))


# --- ref-pinning-check -------------------------------------------------------------------------------------
@case("ref-pinning-check", "pass", "pinned to a tag or commit")
def _(uc):
    write(uc.root / "kustomization.yaml", "resources:\n  - ssh://git@github.com/AItizate/forjate.git//k8s/base?ref=v1.2.0\n  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/x?ref=0a1b2c3d4e5f\n")


@case("ref-pinning-check", "fail", "branch ref", id="ref-pinning-check-fail-branch")
def _(uc): write(uc.root / "kustomization.yaml", "resources:\n  - ssh://git@github.com/AItizate/forjate.git//k8s/base?ref=main\n")


@case("ref-pinning-check", "fail", "branch ref", id="ref-pinning-check-fail-feature-branch")
def _(uc): write(uc.root / "stages" / "walk" / "kustomization.yaml", "resources:\n  - ssh://git@github.com/AItizate/forjate.git//k8s/base?ref=feat/use-case-builder\n")


# --- scaffold-check (the script around scaffold-check.py; the rules are tested in test_scaffold_check.py) -------
def copy_golden_app(uc: UC, name: str = "support-copilot") -> None:
    src = USECASES / name
    ignore = shutil.ignore_patterns(".venv", "__pycache__", "*.egg-info", ".pytest_cache")
    shutil.copytree(src / ".builder", uc.root / ".builder")
    shutil.copytree(src / "app", uc.root / "app", ignore=ignore)


@case("scaffold-check", "pass", "scaffold matches the records")
def _(uc): copy_golden_app(uc)


@case("scaffold-check", "fail", "non-root USER")
def _(uc):
    copy_golden_app(uc)
    df = uc.root / "app" / "Dockerfile"
    df.write_text(df.read_text() + "\nUSER root\n")


@case("scaffold-check", "skip", "no app/")
def _(uc): pass


# --- secret-scan -------------------------------------------------------------------------------------------
@case("secret-scan", "pass", "secret-scan clean")
def _(uc):
    write(uc.root / "configs" / "litellm.yaml", "model_list:\n  - litellm_params:\n      api_key: os.environ/KEY\n")
    write(uc.root / "kustomization.yaml", "secretGenerator:\n  - name: s\n    envs: [secrets/app.env]\n")


@case("secret-scan", "fail", "found plaintext credentials", id="secret-scan-fail-literal")
def _(uc): write(uc.root / "kustomization.yaml", "configMapGenerator:\n  - name: cfg\n    literals:\n      - OPENAI_API_KEY=sk-live-0123456789abcdef0123456789abcdef\n")


@case("secret-scan", "fail", "found plaintext credentials", id="secret-scan-fail-patch")
def _(uc): write(uc.root / "patches" / "env.yaml", "env:\n  - name: DB\n    value: postgres://app:S3cr3tPassw0rdValue@db:5432/x\n")


# --- secrets-check -----------------------------------------------------------------------------------------
def plain_secret() -> dict:
    return doc("Secret", "app-secret", UC.ns, stringData={"TOKEN": "abc123"})


def sealed_secret() -> dict:
    return doc("SealedSecret", "app-secret", UC.ns, api="bitnami.com/v1alpha1", spec={"encryptedData": {"TOKEN": "AgBy3i4OJSWK"}})


@case("secrets-check", "pass", "SealedSecret(s), no plain Secret", needs=need_kustomize)
def _(uc):
    uc.record("security", secrets_mechanism="sealed-secrets")
    uc.build_stage(sealed_secret())


@case("secrets-check", "fail", "plain Secret(s) still rendered", needs=need_kustomize)
def _(uc):
    uc.record("security", secrets_mechanism="sealed-secrets")
    uc.build_stage(sealed_secret(), plain_secret())


@case("secrets-check", "fail", "no SealedSecret in the built stage", needs=need_kustomize, id="secrets-check-fail-no-sealed")
def _(uc):
    uc.record("security", secrets_mechanism="sealed-secrets")
    uc.build_stage(doc("ConfigMap", "cfg", UC.ns, data={"a": "b"}))


@case("secrets-check", "fail", "unknown secrets_mechanism", needs=need_kustomize, id="secrets-check-fail-unknown")
def _(uc):
    uc.record("security", secrets_mechanism="sticky-notes")
    uc.build_stage(sealed_secret())


# --- stage-overlay-builds ----------------------------------------------------------------------------------
def overlay(uc: UC, *, stage_documents: list[dict] | None) -> None:
    """A Crawl root and, unless stage_documents is None, a stage that recomposes it (a stage cannot list its parent
    directory: kustomize refuses the cycle) and adds the documents."""
    cm = yaml.safe_dump(doc("ConfigMap", "cfg", UC.ns, data={"stage": "crawl"}))
    header = "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - cm.yaml\n"
    write(uc.root / "kustomization.yaml", header)
    write(uc.root / "cm.yaml", cm)
    if stage_documents is not None:
        write(uc.stage_dir / "kustomization.yaml", header + ("  - extra.yaml\n" if stage_documents else ""))
        write(uc.stage_dir / "cm.yaml", cm)
        if stage_documents:
            write(uc.stage_dir / "extra.yaml", yaml.safe_dump_all(stage_documents))


@case("stage-overlay-builds", "pass", "build and differ from the root", needs=need_kustomize)
def _(uc): overlay(uc, stage_documents=[doc("ConfigMap", "walk-only", UC.ns, data={"a": "b"})])


@case("stage-overlay-builds", "fail", "builds to the same manifest as the Crawl root", needs=need_kustomize)
def _(uc): overlay(uc, stage_documents=[])


@case("stage-overlay-builds", "fail", "no stages/ overlays exist", needs=need_kustomize, id="stage-overlay-builds-fail-no-stages")
def _(uc): overlay(uc, stage_documents=None)


@case("stage-overlay-builds", "fail", "does not build", needs=need_kustomize, id="stage-overlay-builds-fail-broken")
def _(uc):
    overlay(uc, stage_documents=[doc("ConfigMap", "walk-only", UC.ns)])
    write(uc.stage_dir / "kustomization.yaml", "resources:\n  - ../../\n  - missing.yaml\n")


def use_fixture_usecase(uc: UC) -> None:
    """validate.py wants the directory to carry the use case's name: become the fixture."""
    uc.name, uc.ns = FIXTURE.name, f"uc-{FIXTURE.name}"
    uc.root = uc.root.parent / FIXTURE.name
    shutil.copytree(FIXTURE / ".builder", uc.root / ".builder")


# --- validate-builder (validate.py around a use case's .builder) ---------------------------------------------
@case("validate-builder", "pass", "validate.py clean")
def _(uc): use_fixture_usecase(uc)


@case("validate-builder", "fail", "validate.py reported errors")
def _(uc):
    use_fixture_usecase(uc)
    p = uc.root / ".builder" / "decisions" / "data-store.yaml"
    d = yaml.safe_load(p.read_text())
    d["spec"]["stages"]["crawl"]["choice"] = ["apps/databases/no-such-database"]
    p.write_text(yaml.safe_dump(d, sort_keys=False))


# --- validate-kustomize ------------------------------------------------------------------------------------
@case("validate-kustomize", "pass", "builds and passes kubeconform", needs=lambda: (need_kustomize(), need("kubeconform")))
def _(uc): uc.build_stage(doc("ConfigMap", "cfg", UC.ns, data={"a": "b"}))


@case("validate-kustomize", "fail", "kustomize build", needs=need_kustomize)
def _(uc):
    uc.build_stage(doc("ConfigMap", "cfg", UC.ns, data={"a": "b"}))
    write(uc.stage_dir / "kustomization.yaml", "resources:\n  - missing.yaml\n")


# --- validate-usecases -------------------------------------------------------------------------------------
def use_case_contract(name: str = "demo") -> str:
    return yaml.safe_dump({"apiVersion": "forjate.io/v0", "kind": "UseCase", "metadata": {"name": name},
                           "spec": {"isolation": "shared", "ttl": "2h", "jobs": {"seed": {"name": "demo-seed"}, "verify": {"name": "demo-verify"}}}})


def use_case_overlay(uc: UC, *, suspend: bool = True, name: str = "demo") -> None:
    write(uc.root / "usecase.yaml", use_case_contract(name))
    jobs = [doc("Job", n, UC.ns, api="batch/v1", spec={"suspend": suspend, "template": {"spec": {"restartPolicy": "Never", "containers": [{"name": "c", "image": "busybox:1"}]}}})
            for n in ("demo-seed", "demo-verify")]
    write(uc.root / "all.yaml", yaml.safe_dump_all(jobs))
    write(uc.root / "kustomization.yaml", "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n  - all.yaml\n")


@case("validate-usecases", "pass", "contract matches the overlay", needs=need_kustomize)
def _(uc): use_case_overlay(uc)


@case("validate-usecases", "fail", "must ship suspended", needs=need_kustomize)
def _(uc): use_case_overlay(uc, suspend=False)


@case("validate-usecases", "fail", "metadata.name != demo", needs=need_kustomize, id="validate-usecases-fail-name")
def _(uc): use_case_overlay(uc, name="other")


@case("validate-usecases", "fail", "no usecase.yaml", id="validate-usecases-fail-no-contract")
def _(uc): pass


# --------------------------------------------------------------------------------------------- the tests
EXIT = {"pass": PASS, "fail": FAIL, "skip": SKIP}


@pytest.mark.parametrize("c", CASES, ids=lambda c: c.id)
def test_check_case(c: Case, uc: UC):
    if c.needs:
        c.needs()
    c.build(uc)
    rc, out = uc.run(c.check, **(c.env or {}))
    assert rc == EXIT[c.kind], f"{c.id}: expected exit {EXIT[c.kind]} ({c.kind}), got {rc}\n{out}"
    assert c.contains in out, f"{c.id}: expected {c.contains!r} in the output\n{out}"
    last = out.splitlines()[-1] if out else ""
    assert last.split(":", 1)[0] in {"pass": "PASS", "fail": "FAIL", "skip": "SKIPPED"}[c.kind], f"{c.id}: the last line is the verdict gates.py shows\n{out}"


def test_every_check_script_has_a_passing_and_a_failing_case():
    """A new script in scripts/gates/checks/ is not done until a fixture shows it can pass and one shows it can fail."""
    scripts = sorted(p.stem for p in CHECKS.glob("*.sh") if not p.name.startswith("_"))
    assert len(scripts) >= 20
    for s in scripts:
        kinds = {c.kind for c in CASES if c.check == s}
        assert {"pass", "fail"} <= kinds, f"{s}: cases cover {sorted(kinds) or 'nothing'}; add a passing and a failing fixture to test_gates.py"
    assert {c.check for c in CASES} <= set(scripts), "a case names a script that does not exist"


# ------------------------------------------------------------------------------------------- toolchain
def fake_repo_with_pin(tmp: Path, version: str) -> Path:
    repo = tmp / "repo"
    (repo / "scripts" / "toolchain").mkdir(parents=True)
    (repo / ".github").mkdir()
    shutil.copy(TOOLCHAIN_DIR / "toolchain.sh", repo / "scripts" / "toolchain" / "toolchain.sh")
    (repo / ".github" / "toolchain.env").write_text(f"# pin\nYQ_VERSION={version}\n")
    return repo


def fake_yq(bin_dir: Path, version: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script(bin_dir / "yq", f'echo "yq (https://github.com/mikefarah/yq/) version v{version}"\n')


def toolchain_check(repo: Path, bin_dir: Path, **env) -> subprocess.CompletedProcess:
    e = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin", **env}
    e.pop("FORJATE_TOOLCHAIN", None) if "FORJATE_TOOLCHAIN" not in env else None
    return subprocess.run(["bash", "-c", f'source "{repo}/scripts/toolchain/toolchain.sh" && toolchain_check yq'], capture_output=True, text=True, env=e)


def test_toolchain_accepts_the_pinned_yq_and_refuses_another(tmp_path: Path):
    repo = fake_repo_with_pin(tmp_path, "4.44.3")
    fake_yq(tmp_path / "ok", "4.44.3")
    assert toolchain_check(repo, tmp_path / "ok").returncode == 0
    fake_yq(tmp_path / "newer", "4.53.6")
    r = toolchain_check(repo, tmp_path / "newer")
    assert r.returncode == 1
    assert "yq is 4.53.6, CI pins 4.44.3" in r.stderr and "scripts/toolchain/install.sh" in r.stderr


def test_toolchain_warns_instead_of_refusing_when_asked(tmp_path: Path):
    repo = fake_repo_with_pin(tmp_path, "4.44.3")
    fake_yq(tmp_path / "newer", "4.53.6")
    r = toolchain_check(repo, tmp_path / "newer", FORJATE_TOOLCHAIN="warn")
    assert r.returncode == 0 and "WARNING: yq is 4.53.6" in r.stderr


def test_toolchain_refuses_a_missing_yq(tmp_path: Path):
    repo = fake_repo_with_pin(tmp_path, "4.44.3")
    # A PATH of its own: the system one may carry a yq (the GitHub runners ship 4.5x)
    bare = tmp_path / "bare"
    bare.mkdir()
    for tool in ("bash", "sed", "head", "tr", "dirname"):
        (bare / tool).symlink_to(shutil.which(tool))
    e = {**os.environ, "PATH": str(bare)}
    e.pop("FORJATE_TOOLCHAIN", None)
    r = subprocess.run([str(bare / "bash"), "-c", f'source "{repo}/scripts/toolchain/toolchain.sh" && toolchain_check yq'], capture_output=True, text=True, env=e)
    assert r.returncode == 1 and "yq is not installed" in r.stderr


def test_the_pin_is_one_file_the_workflows_read():
    pin = (REPO / ".github" / "toolchain.env").read_text()
    assert "YQ_VERSION=" in pin
    for wf in (REPO / ".github" / "workflows").glob("*.yml"):
        text = wf.read_text()
        assert "yq/releases/download/v4." not in text, f"{wf.name} hard-codes a yq version; read it from .github/toolchain.env"
        if "yq/releases/download" in text:
            assert "toolchain.env" in text, f"{wf.name} installs yq without reading .github/toolchain.env"


def test_a_check_refuses_to_run_on_another_yq(uc: UC, tmp_path: Path):
    repo = fake_repo_with_pin(tmp_path, "9.9.9")
    uc.extra_env["REPO"] = str(repo)
    rc, out = uc.run("ref-pinning-check")
    assert rc == FAIL and "CI pins 9.9.9" in out
    rc, out = uc.run("ref-pinning-check", FORJATE_TOOLCHAIN="warn")
    assert rc == PASS and "WARNING: yq" in out


def test_the_eval_runner_checks_the_toolchain():
    text = (REPO / "plugins" / "forjate" / "evals" / "run.sh").read_text()
    assert "toolchain_check yq" in text
    assert text.index("toolchain_check yq") < text.index("evals_file=")


# ---------------------------------------------------------------------------------------- the runner
def load_gates_module():
    spec = importlib.util.spec_from_file_location("gates_under_test", GATES_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def gate(gid: str, ctype: str, ref: str = "", owner: str = "security") -> dict:
    g: dict = {"id": gid, "text": f"gate {gid}", "owner": owner}
    g["check"] = {"type": ctype, **({"ref": ref} if ref else {})}
    return g


def runner_uc(tmp: Path, gates: list[dict], transition: str = "crawl->walk") -> Path:
    uc = tmp / "demo"
    write(uc / ".builder" / "gates.yaml", yaml.safe_dump({"apiVersion": "forjate.io/v0", "kind": "Gates", "metadata": {"usecase": "demo", "version": 1},
                                                          "spec": {"transitions": {transition: {"approver": "CFO", "gates": gates}}}}, sort_keys=False))
    return uc


def run_gates(uc: Path, *args: str, **env) -> subprocess.CompletedProcess:
    e = {**os.environ, "KUBECONFIG_UC": "/nonexistent/kubeconfig", **env}
    e.pop("FORJATE_TOOLCHAIN", None) if "FORJATE_TOOLCHAIN" not in env else None
    return subprocess.run([sys.executable, str(GATES_PY), "run", "demo", "--usecase-dir", str(uc), "--transition", "crawl->walk", *args],
                          capture_output=True, text=True, env=e, cwd=REPO)


def statuses(p: subprocess.CompletedProcess) -> dict[str, str]:
    return {g["id"]: g["status"] for g in json.loads(p.stdout)["gates"]}


def test_runner_exit_zero_when_every_ci_gate_passes(tmp_path: Path):
    uc = runner_uc(tmp_path, [gate("G-SEC-1", "ci", "secret-scan"), gate("G-SEC-2", "ci", "ref-pinning-check")])
    p = run_gates(uc, "--json")
    assert p.returncode == 0, p.stdout + p.stderr
    assert statuses(p) == {"G-SEC-1": "pass", "G-SEC-2": "pass"}


def test_runner_exit_one_when_a_ci_gate_fails_and_names_the_reason(tmp_path: Path):
    uc = runner_uc(tmp_path, [gate("G-SEC-1", "ci", "secret-scan"), gate("G-OPS-1", "ci", "ref-pinning-check")])
    write(uc / "kustomization.yaml", "resources:\n  - ssh://git@github.com/AItizate/forjate.git//k8s/base?ref=main\n")
    p = run_gates(uc, "--json")
    assert p.returncode == 1
    got = json.loads(p.stdout)
    assert statuses(p) == {"G-SEC-1": "pass", "G-OPS-1": "fail"}
    assert "branch ref" in next(g["detail"] for g in got["gates"] if g["id"] == "G-OPS-1")
    assert got["exit"] == 1


def test_runner_fails_a_gate_whose_check_script_does_not_exist(tmp_path: Path):
    p = run_gates(runner_uc(tmp_path, [gate("G-SEC-1", "ci", "no-such-check")]), "--json")
    assert p.returncode == 1   # validate.py rejects the ref earlier; the runner still fails it rather than skipping
    assert "no check script for ref 'no-such-check'" in json.loads(p.stdout)["gates"][0]["detail"]


def test_runner_shows_a_skipped_check_and_does_not_block(tmp_path: Path):
    p = run_gates(runner_uc(tmp_path, [gate("G-SEC-7", "ci", "log-content-scan")]), "--json")
    assert p.returncode == 0 and statuses(p) == {"G-SEC-7": "skipped"}


def test_runner_metric_is_pending_until_measured_then_passes(tmp_path: Path):
    uc = runner_uc(tmp_path, [gate("G-BIZ-1", "metric", "straight_through_rate", "business")])
    assert statuses(run_gates(uc, "--json")) == {"G-BIZ-1": "pending"}
    write(uc / ".builder" / "metrics.yaml", yaml.safe_dump({"straight_through_rate": {"value": "0.85", "source": "verify-job-log:v", "measured_at": "2026-10-31T00:00:00+00:00"}}))
    p = run_gates(uc, "--json")
    assert statuses(p) == {"G-BIZ-1": "pass"} and "straight_through_rate=0.85" in json.loads(p.stdout)["gates"][0]["detail"]


def test_runner_lists_manual_gates_and_never_blocks_on_them(tmp_path: Path):
    p = run_gates(runner_uc(tmp_path, [gate("G-COMP-2", "manual", "decisions/compliance.yaml", "compliance")]), "--json")
    assert p.returncode == 0 and statuses(p) == {"G-COMP-2": "manual"}


def test_runner_verify_job_is_skipped_without_a_live_environment(tmp_path: Path):
    p = run_gates(runner_uc(tmp_path, [gate("G-ARCH-1", "verify-job", "demo-verify", "architecture")]), "--json")
    assert p.returncode == 0 and statuses(p) == {"G-ARCH-1": "skipped"}
    assert "ephemeral.sh up demo" in json.loads(p.stdout)["gates"][0]["detail"]


def test_runner_only_filters_by_check_type(tmp_path: Path):
    uc = runner_uc(tmp_path, [gate("G-SEC-1", "ci", "secret-scan"), gate("G-COMP-2", "manual", "x", "compliance")])
    assert statuses(run_gates(uc, "--json", "--only", "ci")) == {"G-SEC-1": "pass"}
    assert statuses(run_gates(uc, "--json", "--only", "manual")) == {"G-COMP-2": "manual"}


def test_runner_table_output_and_missing_gates_file(tmp_path: Path):
    uc = runner_uc(tmp_path, [gate("G-SEC-1", "ci", "secret-scan")])
    p = run_gates(uc)
    assert p.returncode == 0 and "# gates: demo crawl->walk (approver: CFO)" in p.stdout and "| G-SEC-1 | ci | secret-scan | **pass** |" in p.stdout
    p = run_gates(tmp_path / "nothing")
    assert p.returncode == 2 and "gates.yaml missing" in p.stderr


def test_runner_unknown_transition_in_gates_yaml_is_an_error(tmp_path: Path):
    uc = runner_uc(tmp_path, [gate("G-SEC-1", "ci", "secret-scan")], transition="walk->run")
    p = run_gates(uc)
    assert p.returncode != 0 and "no transition crawl->walk" in p.stderr


def test_runner_normalises_transitions():
    g = load_gates_module()
    assert g.norm_transition("crawl->walk") == "crawl->walk"
    assert g.norm_transition("crawl-walk") == "crawl->walk"
    assert g.norm_transition("walk_run") == "walk->run"
    with pytest.raises(Exception):
        g.norm_transition("walk->crawl")


def test_runner_captures_kpi_and_eval_lines_of_the_verify_log(tmp_path: Path):
    g = load_gates_module()
    uc = runner_uc(tmp_path, [gate("G-BIZ-1", "metric", "straight_through_rate", "business")])
    r = g.Runner("demo", uc, "crawl->walk")
    r.capture_metrics("noise\n  KPI straight_through_rate=0.85\nEVAL field_accuracy=0.97 extra\nKPI broken\n", "demo-verify")
    saved = yaml.safe_load((uc / ".builder" / "metrics.yaml").read_text())
    assert saved["straight_through_rate"]["value"] == "0.85" and saved["field_accuracy"]["value"] == "0.97"
    assert saved["straight_through_rate"]["source"] == "verify-job-log:demo-verify" and "broken" not in saved


def test_runner_refuses_another_yq_before_running_any_gate(tmp_path: Path, monkeypatch):
    g = load_gates_module()
    repo = fake_repo_with_pin(tmp_path, "9.9.9")
    fake_yq(tmp_path / "bin", "4.53.6")
    monkeypatch.setattr(g, "REPO", repo)
    monkeypatch.setattr(g, "TOOLCHAIN", repo / "scripts" / "toolchain" / "toolchain.sh")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}/usr/bin{os.pathsep}/bin")
    monkeypatch.delenv("FORJATE_TOOLCHAIN", raising=False)
    assert "CI pins 9.9.9" in (g.toolchain_preflight() or "")
    monkeypatch.setenv("FORJATE_TOOLCHAIN", "warn")
    assert g.toolchain_preflight() is None


def test_runner_puts_the_pinned_yq_first(tmp_path: Path, monkeypatch):
    g = load_gates_module()
    repo = fake_repo_with_pin(tmp_path, "4.44.3")
    fake_yq(repo / ".tools" / "bin", "4.44.3")
    fake_yq(tmp_path / "system", "4.53.6")
    monkeypatch.setattr(g, "REPO", repo)
    monkeypatch.setattr(g, "TOOLCHAIN", repo / "scripts" / "toolchain" / "toolchain.sh")
    monkeypatch.setenv("PATH", f"{tmp_path / 'system'}{os.pathsep}/usr/bin{os.pathsep}/bin")
    monkeypatch.delenv("FORJATE_TOOLCHAIN", raising=False)
    assert g.toolchain_preflight() is None
    assert os.environ["PATH"].startswith(str(repo / ".tools" / "bin"))
