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
