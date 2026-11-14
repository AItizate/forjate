"""No default admin credentials, no manual UI step (finding B2).

Zitadel cmd/setup/steps.yaml (v2 and v4) creates `zitadel-admin` / `Password1!` for the
first instance unless FirstInstance says otherwise, and the Ingress is public. The
rendered stack must take the password from a Secret and let the chart write the
bootstrap service account key.
"""
import yaml

from conftest import by_kind

PASSWORD_ENV = "ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD"


def zitadel_config(bundle):
    cm = by_kind(bundle, "ConfigMap", "zitadel-config-yaml")
    return yaml.safe_load(cm["data"]["zitadel-config-yaml"])


def containers(job):
    return {c["name"]: c for c in job["spec"]["template"]["spec"]["containers"]}


def test_no_default_password_anywhere_in_the_render(bundle):
    assert "Password1!" not in yaml.safe_dump_all(bundle)


def test_admin_password_comes_from_a_required_secret_not_a_literal(bundle):
    setup = by_kind(bundle, "Job", "zitadel-setup")
    env = {e["name"]: e for e in containers(setup)["zitadel-setup"]["env"]}
    entry = env[PASSWORD_ENV]
    assert "value" not in entry, "the password must not be a literal"
    ref = entry["valueFrom"]["secretKeyRef"]
    assert (ref["name"], ref["key"]) == ("zitadel-admin-password", "password")
    # `optional: true` would let Zitadel fall back to its built-in default.
    assert not ref.get("optional")


def test_first_instance_creates_a_machine_user_with_a_json_key(bundle):
    machine = zitadel_config(bundle)["FirstInstance"]["Org"]["Machine"]
    assert machine["Machine"]["Username"] == "zitadel-admin-sa"
    assert machine["MachineKey"]["Type"] == 1


def test_default_instance_only_selects_login_v2(bundle):
    # DefaultInstance is what the FIRST instance reads its features from (the first
    # admin comes from FirstInstance, never from here). Keep it to the one key we mean.
    assert zitadel_config(bundle)["DefaultInstance"] == {"Features": {"LoginV2": {"Required": True}}}


def test_no_machine_pat_sidecar_and_no_pat_config(bundle):
    cfg = zitadel_config(bundle)
    assert "Pat" not in cfg["FirstInstance"]["Org"]["Machine"]
    setup = by_kind(bundle, "Job", "zitadel-setup")
    assert "zitadel-machine-pat" not in containers(setup)
    env = [e["name"] for c in setup["spec"]["template"]["spec"]["containers"] for e in c.get("env", [])]
    assert "ZITADEL_FIRSTINSTANCE_PATPATH" not in env


def test_machine_key_expiry_is_pinned_far_away(bundle):
    key = zitadel_config(bundle)["FirstInstance"]["Org"]["Machine"]["MachineKey"]
    assert str(key["ExpirationDate"]) >= "2035"


def test_service_ping_is_off(bundle):
    assert zitadel_config(bundle)["ServicePing"] == {"Enabled": False}


def test_machine_key_is_written_to_the_secret_the_bootstrap_job_reads(bundle):
    setup = by_kind(bundle, "Job", "zitadel-setup")
    writer = containers(setup)["zitadel-machinekey"]
    script = " ".join(writer["command"])
    assert "create secret generic zitadel-admin-sa" in script
    assert "--from-file=zitadel-admin-sa.json=" in script
    # The chart renders `-n <release namespace>` (= "default" under kustomize); a
    # consumer overlay only re-namespaces objects, so the flag must be gone.
    assert " -n " not in script
    assert not writer["image"].startswith("bitnami/")
    assert ":" in writer["image"] and not writer["image"].endswith(":latest")

    job = by_kind(bundle, "Job", "zitadel-bootstrap") if any(
        o["kind"] == "Job" and o["metadata"]["name"] == "zitadel-bootstrap" for o in bundle
    ) else None
    if job:
        volume = next(v for v in job["spec"]["template"]["spec"]["volumes"] if v["name"] == "admin-sa-key")
        assert volume["secret"]["secretName"] == "zitadel-admin-sa"
        assert volume["secret"]["items"][0]["key"] == "zitadel-admin-sa.json"


def test_chart_role_lets_the_setup_service_account_create_the_secret(bundle):
    role = by_kind(bundle, "Role", "zitadel")
    secrets = [r for r in role["rules"] if "secrets" in r["resources"]][0]
    assert "create" in secrets["verbs"]
