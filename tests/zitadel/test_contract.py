"""One "what the tenant must provide" contract (findings M2, M6, M8, M1, M7, m1).

contract.yaml is the list. These tests make the rendered pods, the docs, the
oauth2-proxy template and the buildable example overlay agree with it, so a name
cannot drift in one place only (the first version had five different spellings).
"""
import re

import pytest
import yaml

from conftest import COMPONENT, EXAMPLE, ROOT, by_kind

CONTRACT = yaml.safe_load((COMPONENT / "contract.yaml").read_text())
DOCS = (ROOT / "docs/apps/zitadel.md").read_text()
# The migration section must name the old things (rbac, ClusterRole, sa-key.json); nowhere else may.
_m = re.search(r"^## Migrating an existing instance\n.*?(?=^## )", DOCS, re.S | re.M)
MIGRATION = _m.group(0) if _m else ""
DOCS_OUTSIDE_MIGRATION = DOCS.replace(MIGRATION, "")
PODS = ("Deployment", "StatefulSet", "Job")


def pod_specs(objs):
    for o in objs:
        if o["kind"] in PODS:
            yield o, o["spec"]["template"]["spec"]


def secret_refs(objs):
    """(name, key|None, optional, where) for everything a pod reads from a Secret."""
    refs = []
    for o, spec in pod_specs(objs):
        where = f"{o['kind']} {o['metadata']['name']}"
        for c in spec.get("containers", []) + spec.get("initContainers", []):
            for e in c.get("env", []):
                r = (e.get("valueFrom") or {}).get("secretKeyRef")
                if r:
                    refs.append((r["name"], r["key"], bool(r.get("optional")), where))
            for f in c.get("envFrom", []):
                if "secretRef" in f:
                    refs.append((f["secretRef"]["name"], None, bool(f["secretRef"].get("optional")), where))
        for v in spec.get("volumes", []):
            if "secret" in v:
                s = v["secret"]
                for item in s.get("items") or [{"key": None}]:
                    refs.append((s["secretName"], item["key"], bool(s.get("optional")), where))
    return refs


def contract_keys():
    known = {s["name"]: set(s["keys"]) for s in CONTRACT["secrets"]}
    known.update({g["name"]: set(g["keys"]) for g in CONTRACT["generated"] if "<" not in g["name"]})
    return known


# ----------------------------------------------------- pods vs contract (M6)

def test_every_secret_a_pod_reads_is_in_the_contract(bundle):
    known = contract_keys()
    for name, key, _, where in secret_refs(bundle):
        assert name in known, f"{where} reads Secret {name!r}, which contract.yaml does not list"
        if key is not None and "<ENV_NAME>" not in known[name]:
            assert key in known[name], f"{where} reads {name}/{key}, not in contract.yaml"


def test_every_required_secret_in_the_contract_is_read_by_a_pod(bundle):
    read = {name for name, *_ in secret_refs(bundle)}
    for s in CONTRACT["secrets"]:
        assert s["name"] in read, f"contract.yaml lists {s['name']} but no rendered pod reads it"


def test_optional_means_optional_on_the_pod_too(bundle):
    optional = {s["name"] for s in CONTRACT["secrets"] if s.get("optional")}
    optional |= {g["name"] for g in CONTRACT["generated"] if g.get("optional_on_pod")}
    for name, _, opt, where in secret_refs(bundle):
        assert opt == (name in optional), f"{where}: {name} optional={opt}, contract says {name in optional}"


def test_masterkey_and_db_config_keys_match_what_the_chart_reads(bundle):
    refs = {(n, k) for n, k, *_ in secret_refs(bundle)}
    assert ("zitadel-masterkey", "masterkey") in refs
    assert any(n == "zitadel-db-config" for n, *_ in secret_refs(bundle))
    postgres = by_kind(bundle, "StatefulSet", "zitadel-postgres")
    env_from = postgres["spec"]["template"]["spec"]["containers"][0]["envFrom"][0]["secretRef"]["name"]
    assert env_from == "zitadel-postgres-secret"
    cfg = yaml.safe_load(by_kind(bundle, "ConfigMap", "zitadel-config-yaml")["data"]["zitadel-config-yaml"])
    assert cfg["Database"]["postgres"]["Host"] == "zitadel-postgres"
    assert by_kind(bundle, "Service", "zitadel-postgres")


def test_config_maps_mounted_by_pods_exist_in_the_render(bundle):
    names = {o["metadata"]["name"] for o in bundle if o["kind"] == "ConfigMap"}
    for o, spec in pod_specs(bundle):
        for v in spec.get("volumes", []):
            if "configMap" in v:
                assert v["configMap"]["name"] in names, f"{o['metadata']['name']} mounts a missing ConfigMap"
    assert CONTRACT["configmaps"][0]["name"] == "zitadel-bootstrap-config"


# ------------------------------------------------------------ docs vs contract

def test_docs_name_every_secret_and_key_of_the_contract():
    assert "contract.yaml" in DOCS
    for s in CONTRACT["secrets"]:
        assert s["name"] in DOCS, f"docs/apps/zitadel.md does not mention {s['name']}"
        for k in s["keys"]:
            if "<" not in k:
                assert k in DOCS, f"docs/apps/zitadel.md does not mention the key {k} of {s['name']}"
    for g in CONTRACT["generated"]:
        assert g["name"].split("<")[0] in DOCS


@pytest.mark.parametrize("stale", [
    "zitadel-oidc-credentials", "ZITADEL_MASTERKEY", "postgres-password", "clusterrole", "ClusterRole",
    "rbac/", "sa-key.json", "default admin credentials", "organization:\n", "namespace: zitadel\n    behavior",
    "Tenant IaC Factory", "zitadel-postgres-postgresql", "client_credentials",
])
def test_docs_have_none_of_the_names_the_first_version_got_wrong(stale):
    assert stale not in DOCS_OUTSIDE_MIGRATION


def test_docs_have_a_migration_path_for_existing_instances():
    # N3: FirstInstance never re-runs on an instance that already exists.
    assert MIGRATION, "docs/apps/zitadel.md needs a 'Migrating an existing instance' section"
    for needle in ("zitadel-admin-password", "sa-key.json", "zitadel-admin-sa.json", "zitadel-admin",
                   "default password", "initial_password"):
        assert needle in MIGRATION, f"the migration section does not mention {needle}"
    assert "## Recovering the bootstrap service account key" in DOCS


def test_docs_and_contract_state_the_admin_password_policy():
    for text in (DOCS, (COMPONENT / "contract.yaml").read_text()):
        assert "password policy" in text


def test_docs_workload_names_exist_in_the_render(example):
    names = {(o["kind"].lower(), o["metadata"]["name"]) for o in example}
    # only the commands aimed at the Zitadel namespace; oauth2-proxy lives elsewhere
    zitadel_lines = "\n".join(l for l in DOCS.splitlines() if "-n zitadel" in l)
    found = re.findall(r"\b(deploy|statefulset|job)/([\w-]+)", zitadel_lines)
    assert found
    for kind, name in found:
        kind = {"deploy": "deployment"}.get(kind, kind)
        assert (kind, name) in names, f"docs mention {kind}/{name}, which the stack does not render"


def test_headers_point_at_the_contract_and_name_only_contract_secrets():
    for path in (COMPONENT / "kustomization.yaml", ROOT / "k8s/components/bundles/zitadel-stack/kustomization.yaml",
                 COMPONENT / "bootstrap/kustomization.yaml"):
        text = path.read_text()
        for name in re.findall(r'Secret "([\w-]+)"', text):
            assert name in contract_keys(), f"{path.name} mentions Secret {name}, not in the contract"
    assert "contract.yaml" in (COMPONENT / "kustomization.yaml").read_text()
    assert "contract.yaml" in (ROOT / "k8s/components/bundles/zitadel-stack/kustomization.yaml").read_text()


# ---------------------------------------------------------- bundle content (M2)

def test_bundle_carries_what_its_header_claims(bundle):
    by = {(o["kind"], o["metadata"]["name"]) for o in bundle}
    for want in [("Job", "zitadel-bootstrap"), ("Role", "zitadel-bootstrap"), ("RoleBinding", "zitadel-bootstrap"),
                 ("ServiceAccount", "zitadel-bootstrap"), ("ConfigMap", "zitadel-bootstrap-config"),
                 ("Ingress", "zitadel"), ("StatefulSet", "zitadel-postgres")]:
        assert want in by, f"zitadel-stack should render {want}"


def test_no_cluster_scoped_object_anywhere(bundle):
    # Fixed-name cluster objects collide between tenants (finding M1).
    cluster = [o for o in bundle if o["kind"] in ("ClusterRole", "ClusterRoleBinding", "CustomResourceDefinition",
                                                  "ValidatingWebhookConfiguration", "IngressClass")]
    assert not cluster, [(o["kind"], o["metadata"]["name"]) for o in cluster]


def test_bootstrap_role_is_namespaced_and_limited_to_secrets(bundle):
    role = by_kind(bundle, "Role", "zitadel-bootstrap")
    assert [r["resources"] for r in role["rules"]] == [["secrets"]]
    assert set(role["rules"][0]["verbs"]) == {"get", "create", "patch"}
    binding = by_kind(bundle, "RoleBinding", "zitadel-bootstrap")
    assert binding["subjects"][0]["name"] == "zitadel-bootstrap"
    assert not [o for o in bundle if o["kind"] == "RoleBinding" and o["metadata"]["name"] == "zitadel-bootstrap"
                and o["roleRef"]["kind"] != "Role"]


def test_bootstrap_job_is_hardened_and_installs_nothing_at_start(bundle):
    job = by_kind(bundle, "Job", "zitadel-bootstrap")
    spec = job["spec"]["template"]["spec"]
    assert job["spec"]["activeDeadlineSeconds"]
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    for c in spec["containers"] + spec["initContainers"]:
        assert re.search(r":\d+\.\d+\.\d+", c["image"]), f"{c['image']} is a floating tag"
        sc = c["securityContext"]
        assert sc["allowPrivilegeEscalation"] is False and sc["readOnlyRootFilesystem"] is True
        assert sc["capabilities"]["drop"] == ["ALL"]
        assert c["resources"]["requests"] and c["resources"]["limits"]
    main = " ".join(spec["containers"][0]["command"])
    assert "pip install" not in main and "apk add" not in main
    assert spec["containers"][0]["envFrom"][0]["secretRef"]["optional"] is True
    # N3: a missing zitadel-admin-sa must reach bootstrap.py (fail fast with the
    # instructions), not park the pod in ContainerCreating until the deadline.
    sa_volume = next(v for v in spec["volumes"] if v["name"] == "admin-sa-key")
    assert sa_volume["secret"]["optional"] is True


def test_requirements_are_fully_pinned_and_hashed():
    text = (COMPONENT / "bootstrap/requirements.txt").read_text()
    body = re.sub(r"\\\n", " ", "\n".join(l for l in text.splitlines() if not l.startswith("#")))
    reqs = [l.split() for l in body.splitlines() if l.strip()]
    assert reqs
    for r in reqs:
        assert re.fullmatch(r"[\w.\-]+==\d[\w.]*", r[0]), r[0]
        assert len(r) > 1 and all(re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", h) for h in r[1:]), r[0]


def test_job_installs_with_hashes_and_binary_wheels_only(bundle):
    init = by_kind(bundle, "Job", "zitadel-bootstrap")["spec"]["template"]["spec"]["initContainers"][0]
    assert "--require-hashes" in init["command"] and "--only-binary=:all:" in init["command"]


# ------------------------------------------------------------------ labels (m1)

def test_labels_follow_the_forjate_convention(bundle):
    for o in bundle:
        labels = o["metadata"].get("labels") or {}
        if o["kind"] == "Namespace":
            continue
        assert labels.get("app.kubernetes.io/ait-bundle") == "zitadel-stack", (o["kind"], o["metadata"]["name"])
        assert labels.get("app.kubernetes.io/ait-component"), (o["kind"], o["metadata"]["name"])
    assert by_kind(bundle, "Deployment", "zitadel")["metadata"]["labels"]["app.kubernetes.io/ait-component"] == "zitadel"


# ------------------------------------------------- oauth2-proxy template (M8)

def test_oauth2_template_verifies_tls_and_reads_the_secret_the_bootstrap_writes():
    values = yaml.safe_load((COMPONENT / "oauth2-proxy-integration/oauth2-values-zitadel.yaml").read_text())
    assert "ssl-insecure-skip-verify" not in values["extraArgs"]
    refs = {(e["valueFrom"]["secretKeyRef"]["name"], e["valueFrom"]["secretKeyRef"]["key"])
            for e in values["extraEnv"] if e["name"] != "OAUTH2_PROXY_COOKIE_SECRET"}
    assert refs == {("zitadel-oidc-oauth2-proxy", "client-id"), ("zitadel-oidc-oauth2-proxy", "client-secret")}
    # ... which is what the bootstrap writes for the application named oauth2-proxy
    default = yaml.safe_load(yaml.safe_load((COMPONENT / "bootstrap/configmap.yaml").read_text())["data"]["bootstrap.yaml"])
    assert "oauth2-proxy" in [a["name"] for a in default["applications"]]
    assert values["extraArgs"]["oidc-groups-claim"] == "groups"


# ------------------------------------------------------- the example builds

def test_example_overlay_builds_in_one_namespace_with_no_placeholder_host(example):
    # N2: every object, Helm output included, carries the namespace; the contract's patch
    # (labelSelector part-of=zitadel-stack) is what puts it there.
    for o in example:
        if o["kind"] == "Namespace":
            continue
        assert o["metadata"].get("namespace") == "zitadel", (o["kind"], o["metadata"]["name"])
    binding = by_kind(example, "RoleBinding", "zitadel-bootstrap")
    assert binding["subjects"][0]["namespace"] == "zitadel"
    text = yaml.safe_dump_all([o for o in example if o["metadata"]["name"] != "zitadel-config-yaml"])
    assert "zitadel.example.com" not in text, "a placeholder host survived the documented patches"


def test_bundle_keeps_part_of_zitadel_stack_next_to_ait_bundle(bundle):
    # Known remote tenants select on part-of=zitadel-stack to force metadata.namespace.
    for o in bundle:
        labels = o["metadata"].get("labels") or {}
        assert labels.get("app.kubernetes.io/part-of") == "zitadel-stack", (o["kind"], o["metadata"]["name"])
        assert labels.get("app.kubernetes.io/ait-bundle") == "zitadel-stack"


def test_contract_namespace_patch_is_the_one_the_example_uses():
    patch = yaml.safe_load(CONTRACT["namespace"]["patch"])["patches"][0]
    assert patch["target"]["labelSelector"] == "app.kubernetes.io/part-of=zitadel-stack"
    example = yaml.safe_load((EXAMPLE / "kustomization.yaml").read_text())
    assert any(p.get("target", {}).get("labelSelector") == patch["target"]["labelSelector"]
               and "/metadata/namespace" in p["patch"] for p in example["patches"])
    assert "part-of=zitadel-stack" in DOCS


def test_example_replaces_the_bootstrap_config_with_the_tenants(example):
    cm = by_kind(example, "ConfigMap", "zitadel-bootstrap-config")
    cfg = yaml.safe_load(cm["data"]["bootstrap.yaml"])
    assert cfg["instance_url"] == "https://zitadel.acme.dev"
    assert cfg["organizations"][0]["name"] == "acme"


def test_example_ships_an_example_for_every_secret_of_the_contract():
    shipped = {p.name.split(".")[0] for p in (EXAMPLE / "secrets").iterdir() if ".example" in p.name}
    assert shipped == {s["name"] for s in CONTRACT["secrets"]}


def test_example_bootstrap_config_passes_the_scripts_own_validation(w_module):
    cfg = yaml.safe_load((EXAMPLE / "bootstrap.yaml").read_text())
    assert w_module.validate_config(cfg) == []
