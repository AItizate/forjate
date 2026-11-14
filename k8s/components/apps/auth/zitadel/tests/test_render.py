"""Argo CD semantics of the rendered zitadel-stack bundle (finding B1).

Argo CD v3.6.1 (gitops-engine pkg/sync/hook/helm/hook.go) treats an object as a
hook as soon as the `helm.sh/hook` KEY exists, whatever its value, and a hook
without a recognised phase is neither synced nor run. These tests fail if a
`helm.sh/hook*` key (blank or not) survives the render, and pin the hook and
sync-wave ordering that replaces it.
"""
from conftest import by_kind


def annotations(obj):
    return obj["metadata"].get("annotations") or {}


def wave(obj):
    return int(annotations(obj).get("argocd.argoproj.io/sync-wave", "0"))


def test_no_helm_hook_key_survives_anywhere(bundle):
    offenders = [
        (o["kind"], o["metadata"]["name"], k)
        for o in bundle
        for k in annotations(o)
        if k.startswith("helm.sh/hook")
    ]
    assert not offenders, f"helm.sh/hook* keys must be deleted, not blanked: {offenders}"


def test_init_and_setup_are_argo_sync_hooks_recreated_each_sync(bundle):
    for name in ("zitadel-init", "zitadel-setup"):
        a = annotations(by_kind(bundle, "Job", name))
        assert a["argocd.argoproj.io/hook"] == "Sync"
        # Recreated, never patched: a chart bump that changes the Job template
        # must not hit "field is immutable".
        assert a["argocd.argoproj.io/hook-delete-policy"] == "BeforeHookCreation"


def test_wave_order_postgres_then_init_then_setup_then_deployment(bundle):
    postgres = by_kind(bundle, "StatefulSet", "zitadel-postgres")
    init = by_kind(bundle, "Job", "zitadel-init")
    setup = by_kind(bundle, "Job", "zitadel-setup")
    deploy = by_kind(bundle, "Deployment", "zitadel")
    ingress = by_kind(bundle, "Ingress", "zitadel")
    assert wave(postgres) < wave(init) < wave(setup) < wave(deploy)
    assert wave(ingress) >= wave(deploy), "the console is not published before setup ran"


def test_config_objects_are_plain_resources_in_the_first_wave(bundle):
    # They are mounted by the Jobs, so they must exist (and be pruned/diffed by
    # Argo) before wave 1.
    for kind, name in (("ServiceAccount", "zitadel"), ("ConfigMap", "zitadel-config-yaml")):
        obj = by_kind(bundle, kind, name)
        assert "argocd.argoproj.io/hook" not in annotations(obj)
        assert wave(obj) < wave(by_kind(bundle, "Job", "zitadel-init"))


# ------------------------------------------------ chart 10 / Zitadel v4 (issue #60)

def test_the_chart_cleanup_job_is_not_rendered(bundle):
    """With its helm hook keys stripped it would be a plain Job that deletes Secrets
    (kubectl delete secret --selector managed-by=Zitadel) on every sync."""
    assert not [o for o in bundle if o["kind"] == "Job" and "cleanup" in o["metadata"]["name"]]


def test_zitadel_and_login_run_the_pinned_v4_images(bundle):
    from conftest import by_kind as k

    for obj, prefix in ((k(bundle, "Deployment", "zitadel"), "ghcr.io/zitadel/zitadel:"),
                        (k(bundle, "Deployment", "zitadel-login"), "ghcr.io/zitadel/zitadel-login:")):
        images = [c["image"] for c in obj["spec"]["template"]["spec"]["containers"]]
        assert images == [f"{prefix}v4.20.2"]
    for job in ("zitadel-init", "zitadel-setup"):
        containers = by_kind(bundle, "Job", job)["spec"]["template"]["spec"]["containers"]
        assert {c["image"] for c in containers if c["name"] == job} == {"ghcr.io/zitadel/zitadel:v4.20.2"}


def test_login_starts_with_zitadel_and_not_before(bundle):
    assert wave(by_kind(bundle, "Deployment", "zitadel-login")) >= wave(by_kind(bundle, "Deployment", "zitadel"))


def test_login_keypair_is_a_tenant_secret_and_the_component_has_no_foreign_crds(bundle):
    """The chart's own Secret draws a new random key on every build (permanent
    OutOfSync), so the Secret is the tenant's. The component must not need the CRDs of
    another component (cert-manager, ...) to render or apply."""
    assert not [o for o in bundle if o["kind"] == "Secret"], "a build must not render any Secret"
    core = {"v1", "apps/v1", "batch/v1", "networking.k8s.io/v1", "rbac.authorization.k8s.io/v1"}
    assert {o["apiVersion"] for o in bundle} <= core | {"apps/v1"}, sorted({o["apiVersion"] for o in bundle})


def test_the_render_is_deterministic(bundle):
    from conftest import BUNDLE, render

    assert render(BUNDLE) == bundle


def test_ingress_routes_login_v2_to_the_login_service(bundle):
    paths = {p["path"]: p["backend"]["service"] for r in by_kind(bundle, "Ingress", "zitadel")["spec"]["rules"]
             for p in r["http"]["paths"]}
    assert paths["/ui/v2/login"] == {"name": "zitadel-login", "port": {"number": 3000}}
    assert paths["/"] == {"name": "zitadel", "port": {"number": 8080}}


def test_login_service_exists_and_is_plain_http(bundle):
    svc = by_kind(bundle, "Service", "zitadel-login")
    assert [p["port"] for p in svc["spec"]["ports"]] == [3000]


def test_the_example_overlay_sets_the_login_domain(example):
    login = by_kind(example, "Deployment", "zitadel-login")
    env = {e["name"]: e.get("value") for e in login["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["ZITADEL_EXTERNALDOMAIN"] == "zitadel.acme.dev"
