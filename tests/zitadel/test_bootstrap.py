"""bootstrap.py against a mocked Zitadel and a mocked Secrets API.

Covers what the review found missing (M3, M4, M5, M10, m6, B3 guards): a fresh run,
an idempotent re-run, create-or-update, secrets that are lost or must not rotate,
and the exit code of every kind of failure.
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest
import yaml

from fakes import Kubernetes, Zitadel
from conftest import COMPONENT

SCRIPT = COMPONENT / "bootstrap/bootstrap.py"
ISSUER = "https://zitadel.example.com"


class World:
    def __init__(self, tmp_path, monkeypatch):
        self.tmp, self.monkeypatch = tmp_path, monkeypatch
        self.z, self.k = Zitadel(), Kubernetes()

        class RequestException(Exception):
            pass

        fake = types.ModuleType("requests")
        fake.Session = self.z.make_session
        fake.request = self.k.request
        fake.RequestException = RequestException
        monkeypatch.setitem(sys.modules, "requests", fake)

        sa = tmp_path / "sa"
        sa.mkdir()
        (sa / "token").write_text("sa-token")
        (sa / "ca.crt").write_text("ca")
        (tmp_path / "key.json").write_text('{"userId":"u1","keyId":"k1","key":"PEM"}')
        for k, v in {"POD_NAMESPACE": "zitadel", "K8S_SA_DIR": str(sa), "ZITADEL_KEY_FILE": str(tmp_path / "key.json"),
                     "ZITADEL_URL": "http://zitadel:8080"}.items():
            monkeypatch.setenv(k, v)
        spec = importlib.util.spec_from_file_location("zbootstrap", SCRIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.mod.make_jwt = lambda key, aud: "signed.jwt"
        monkeypatch.setattr(self.mod.time, "sleep", lambda s: None)

    def run(self, cfg):
        """Run main(); return the exit code (0 when main returns)."""
        path = self.tmp / "bootstrap.yaml"
        path.write_text(yaml.safe_dump({"instance_url": ISSUER, **cfg}))
        self.mod.CONFIG_FILE = str(path)
        self.mod.FAILURES.clear()
        self.z.calls.clear()
        self.k.calls.clear()
        try:
            self.mod.main()
        except SystemExit as e:
            return 0 if e.code is None else (e.code if isinstance(e.code, int) else 1)
        return 0

    def writes(self):
        return [c for c in self.z.calls if c[0] in ("POST", "PUT", "DELETE") and "_search" not in c[1]
                and c[1] not in ("/oauth/v2/token", "/v2/users", "/admin/v1/policies/login/idps/_search")]


@pytest.fixture
def w(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


CONFIG = {
    "organizations": [{"name": "acme", "is_default": True}],
    "project": {"name": "platform", "roles": [
        {"key": "admin", "display_name": "Administrator"}, {"key": "viewer"}]},
    "applications": [
        {"name": "oauth2-proxy", "redirect_uris": ["https://auth.example.com/oauth2/callback"]},
        {"name": "argocd-cli", "app_type": "OIDC_APP_TYPE_NATIVE", "auth_method": "OIDC_AUTH_METHOD_TYPE_NONE",
         "redirect_uris": ["http://localhost:8085/auth/callback"]},
    ],
    "users": [{"username": "ana", "email": "ana@example.com", "initial_password_env": "ANA_PASSWORD",
               "roles": ["admin"]}],
    "service_users": [{"username": "agent", "roles": ["viewer"]}],
}


def cfg(**over):
    c = yaml.safe_load(yaml.safe_dump(CONFIG))
    c.update(over)
    return c


@pytest.fixture(autouse=True)
def passwords(monkeypatch):
    monkeypatch.setenv("ANA_PASSWORD", "s3cret-from-a-secret")


# ------------------------------------------------------------ fresh + re-run

def test_fresh_run_converges_and_stores_credentials(w):
    assert w.run(cfg()) == 0
    assert w.k.secrets["zitadel-oidc-oauth2-proxy"]["client-secret"].startswith("secret-")
    assert w.k.secrets["zitadel-oidc-oauth2-proxy"]["issuer-url"] == ISSUER
    # public client: only the client-id (and issuer), never a secret
    assert "client-secret" not in w.k.secrets["zitadel-oidc-argocd-cli"]
    assert {r[1] for r in w.z.roles} == {"admin", "viewer"}
    assert sorted(g["roleKeys"][0] for g in w.z.grants.values()) == ["admin", "viewer"]


def test_rerun_is_a_no_op(w):
    assert w.run(cfg()) == 0
    state = (dict(w.z.apps), dict(w.z.users), dict(w.z.grants), {k: dict(v) for k, v in w.k.secrets.items()})
    assert w.run(cfg()) == 0
    assert (dict(w.z.apps), dict(w.z.users), dict(w.z.grants), w.k.secrets) == state
    creates = [c for c in w.writes() if c[0] == "POST" and not c[1].endswith("/roles")]
    assert not creates, f"re-run created things: {creates}"
    assert not [c for c in w.k.calls if c[0] != "GET"], "re-run wrote Secrets that were up to date"


# -------------------------------------------------------------- create-or-update

def test_changed_redirect_uri_is_applied_without_rotating_the_secret(w):
    w.run(cfg())
    before = w.k.secrets["zitadel-oidc-oauth2-proxy"]["client-secret"]
    c = cfg()
    c["applications"][0]["redirect_uris"] = ["https://auth.example.com/oauth2/callback", "https://other/cb"]
    assert w.run(c) == 0
    proxy = next(a for a in w.z.apps.values() if a["redirectUris"][0].startswith("https://auth"))
    assert proxy["redirectUris"] == ["https://auth.example.com/oauth2/callback", "https://other/cb"]
    assert w.k.secrets["zitadel-oidc-oauth2-proxy"]["client-secret"] == before


def test_changed_role_display_name_and_grant_are_updated(w):
    w.run(cfg())
    c = cfg()
    c["project"]["roles"][0]["display_name"] = "Root"
    c["users"][0]["roles"] = ["admin", "viewer"]
    assert w.run(c) == 0
    assert next(r for k, r in w.z.roles.items() if k[1] == "admin")["displayName"] == "Root"
    ana = next(i for i, u in w.z.users.items() if u["username"] == "ana")
    assert sorted(next(g for g in w.z.grants.values() if g["user"] == ana)["roleKeys"]) == ["admin", "viewer"]


def test_action_update_and_flow(w):
    c = cfg(actions=[{"name": "groupsClaim", "script": "function groupsClaim(){}"}],
            flows=[{"type": "complement_token", "triggers": ["pre_userinfo_creation"], "actions": ["groupsClaim"]}])
    assert w.run(c) == 0
    c["actions"][0]["script"] = "function groupsClaim(){ return; }"
    assert w.run(c) == 0
    assert next(iter(w.z.actions.values()))["script"].endswith("return; }")
    assert w.z.flows == {("2", "4"): [next(iter(w.z.actions))]}


# -------------------------------------------------------------- lost secrets

def test_lost_confidential_secret_is_regenerated(w):
    w.run(cfg())
    del w.k.secrets["zitadel-oidc-oauth2-proxy"]
    assert w.run(cfg()) == 0
    assert w.k.secrets["zitadel-oidc-oauth2-proxy"]["client-secret"].startswith("regen-")


def test_lost_public_secret_is_recreated_without_regenerating(w):
    w.run(cfg())
    del w.k.secrets["zitadel-oidc-argocd-cli"]
    assert w.run(cfg()) == 0
    assert w.k.secrets["zitadel-oidc-argocd-cli"]["client-id"].startswith("cid-")
    assert not [c for c in w.z.calls if "_generate_client_secret" in c[1]]


def test_intact_secret_is_never_rotated(w):
    w.run(cfg())
    w.run(cfg())
    assert not [c for c in w.z.calls if "_generate_client_secret" in c[1]]


def test_only_get_create_patch_are_used_on_secrets(w):
    w.run(cfg())
    del w.k.secrets["zitadel-oidc-oauth2-proxy"]
    w.run(cfg())
    # The namespaced Role grants get/create/update/patch; the fake raises on any other verb.
    assert {c[0] for c in w.k.calls} <= {"GET", "POST", "PATCH"}


# ----------------------------------------------------------------- exit codes

@pytest.mark.parametrize("pattern, what", [
    (r"POST /management/v1/projects/\w+/roles$", "role"),
    (r"POST /management/v1/actions$", "action"),
    (r"POST /management/v1/users/machine", "service user"),
    (r"POST /v2/users/human", "user"),
    (r"POST /management/v1/users/\w+/grants$", "grant"),
    (r"POST /management/v1/projects/\w+/apps/oidc", "app"),
])
def test_a_failed_item_exits_1_but_the_rest_still_runs(w, pattern, what):
    c = cfg(actions=[{"name": "a", "script": "x"}])
    w.z.fail.append((pattern, 500))
    assert w.run(c) == 1, f"a failing {what} must fail the Job"
    assert w.z.projects, "items before the failing one ran"
    if what not in ("app", "user", "service user", "grant"):
        assert w.z.apps, "items after the failing one still ran"


def test_failed_flow_and_idp_calls_exit_1(w, monkeypatch):
    monkeypatch.setenv("G_ID", "id")
    monkeypatch.setenv("G_SECRET", "s")
    google = {"name": "Google", "type": "google", "client_id_env": "G_ID", "client_secret_env": "G_SECRET"}
    w.z.fail.append((r"POST /admin/v1/idps/google$", 500))
    assert w.run(cfg(identity_providers=[google])) == 1
    w.z.fail.clear()
    w.z.fail.append((r"POST /admin/v1/policies/login/idps$", 500))
    assert w.run(cfg(identity_providers=[google])) == 1
    w.z.fail.clear()
    c = cfg(actions=[{"name": "a", "script": "x"}],
            flows=[{"type": "complement_token", "triggers": ["pre_userinfo_creation"], "actions": ["a"]}])
    w.z.fail.append((r"POST /management/v1/flows/", 500))
    assert w.run(c) == 1


def test_secret_write_failure_exits_1(w):
    w.k.fail = True
    assert w.run(cfg()) == 1


def test_user_without_its_password_env_exits_1_and_is_not_created(w, monkeypatch):
    monkeypatch.delenv("ANA_PASSWORD")
    assert w.run(cfg()) == 1
    assert not [u for u in w.z.users.values() if u["username"] == "ana"]


def test_token_failure_is_fatal(w):
    w.z.fail.append((r"POST /oauth/v2/token", 401))
    assert w.run(cfg()) == 1
    assert not w.writes()


def test_zitadel_that_never_gets_ready_fails_instead_of_hanging(w, monkeypatch):
    w.z.ready = False
    monkeypatch.setenv("ZITADEL_WAIT_SECONDS", "0")
    assert w.run(cfg()) == 1


def test_invalid_config_exits_2_before_any_api_call(w):
    assert w.run(cfg(users=[{"username": "x", "email": "x@y.z", "initial_password": "plain"}])) == 2
    assert not w.z.calls


# --------------------------------------------------------- organizations (M5)

def test_organizations_list_creates_the_org_and_scopes_the_project(w):
    assert w.run(cfg()) == 0
    org_id = next(iter(w.z.orgs))
    assert w.z.orgs[org_id] == "acme"
    assert next(iter(w.z.projects.values()))["org"] == org_id


def test_singular_organization_key_is_still_honoured(w):
    c = cfg()
    c.pop("organizations")
    c["organization"] = {"name": "acme"}
    assert w.run(c) == 0
    assert list(w.z.orgs.values()) == ["acme"]
    assert next(iter(w.z.projects.values()))["org"] is not None


def test_no_org_configured_uses_the_service_account_org_and_says_so(w, capsys):
    c = cfg()
    c.pop("organizations")
    assert w.run(c) == 0
    assert not w.z.orgs and next(iter(w.z.projects.values()))["org"] is None
    assert "service account's own organization" in capsys.readouterr().out


def test_user_lookup_is_scoped_by_organization_id_query(w):
    w.run(cfg())
    searches = [c for c in w.z.calls if c[:2] == ("POST", "/v2/users")]
    assert searches and all(
        any("organizationIdQuery" in q for q in c[2]["queries"]) for c in searches)


# ------------------------------------------------------------ passwords (M10)

def test_initial_password_comes_from_the_env_and_is_never_logged(w, capsys):
    assert w.run(cfg()) == 0
    ana = next(u for u in w.z.users.values() if u["username"] == "ana")
    assert ana["password"] == "s3cret-from-a-secret"
    out = capsys.readouterr()
    assert "s3cret-from-a-secret" not in out.out + out.err


def test_default_bootstrap_config_is_valid_and_has_no_plaintext_password(w):
    import re
    text = (COMPONENT / "bootstrap/configmap.yaml").read_text()
    # not even in the commented examples a tenant copies from
    assert not re.search(r"^\s*#?\s*(-\s+)?initial_password:", text, re.M)
    cm = yaml.safe_load(text)
    assert w.mod.validate_config(yaml.safe_load(cm["data"]["bootstrap.yaml"])) == []


# ---------------------------------------------------------- IdP defaults (B3)

def idp(**over):
    base = {"name": "Entra", "type": "azure", "client_id_env": "G_ID", "client_secret_env": "G_SECRET"}
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def idp_env(monkeypatch):
    monkeypatch.setenv("G_ID", "client-id")
    monkeypatch.setenv("G_SECRET", "client-secret")


def test_azure_needs_an_explicit_tenant(w):
    assert w.run(cfg(identity_providers=[idp()])) == 2
    assert w.run(cfg(identity_providers=[idp(tenant_id="t-1", tenant_type="AZURE_AD_TENANT_TYPE_COMMON")])) == 2
    assert not w.z.idps


def test_azure_defaults_are_a_single_tenant_with_unverified_email(w):
    assert w.run(cfg(identity_providers=[idp(tenant_id="11111111-2222")])) == 0
    created = next(iter(w.z.idps.values()))
    assert created["tenant"] == {"tenantId": "11111111-2222"}
    assert created["emailVerified"] is False
    assert created["providerOptions"]["autoLinking"] == "AUTO_LINKING_OPTION_UNSPECIFIED"
    assert created["providerOptions"]["isAutoCreation"] is False


@pytest.mark.parametrize("kind, extra", [
    ("azure", {"tenant_id": "t-1"}),
    ("generic_oidc", {"issuer": "https://idp.example.com"}),
])
@pytest.mark.parametrize("linking", ["email", "username"])
def test_auto_linking_is_refused_for_loose_idps(w, kind, extra, linking):
    entry = idp(type=kind, options={"auto_linking": linking}, **extra)
    assert w.run(cfg(identity_providers=[entry])) == 2
    assert not w.z.calls


def test_loose_idp_auto_linking_needs_the_loud_flag_and_warns(w, capsys):
    entry = idp(tenant_id="t-1", options={"auto_linking": "email"}, trust_idp_email=True)
    assert w.run(cfg(identity_providers=[entry])) == 0
    assert "WARNING" in capsys.readouterr().out
    assert next(iter(w.z.idps.values()))["providerOptions"]["autoLinking"] == "AUTO_LINKING_OPTION_EMAIL"


@pytest.mark.parametrize("kind, extra", [
    ("google", {}), ("github", {}),
    ("azure", {"tenant_id": "t-1"}),
    ("generic_oidc", {"issuer": "https://idp.example.com"}),
])
def test_auto_linking_username_is_refused_for_every_external_idp(w, kind, extra):
    # N1: a GitHub login (or an Entra UPN) is chosen by whoever registers it; linking
    # on it lets anyone who registers `admin` take over the Zitadel user `admin`.
    entry = idp(type=kind, options={"auto_linking": "username"}, **extra)
    assert w.run(cfg(identity_providers=[entry])) == 2
    assert not w.z.calls and not w.z.idps


def test_trust_email_does_not_unlock_username_linking(w):
    entry = idp(tenant_id="t-1", options={"auto_linking": "username"}, trust_idp_email=True)
    assert w.run(cfg(identity_providers=[entry])) == 2


@pytest.mark.parametrize("kind, extra", [("github", {}), ("azure", {"tenant_id": "t-1"})])
def test_username_linking_needs_its_own_loud_flag_and_warns(w, kind, extra, capsys):
    entry = idp(type=kind, options={"auto_linking": "username"}, trust_idp_username=True, **extra)
    assert w.run(cfg(identity_providers=[entry])) == 0
    assert "trust_idp_username=true" in capsys.readouterr().out
    assert next(iter(w.z.idps.values()))["providerOptions"]["autoLinking"] == "AUTO_LINKING_OPTION_USERNAME"


@pytest.mark.parametrize("kind", ["google", "github"])
def test_auto_linking_email_stays_available_for_idps_that_verify_emails(w, kind, capsys):
    entry = idp(type=kind, options={"auto_linking": "email"})
    assert w.run(cfg(identity_providers=[entry])) == 0
    assert "CVE-2026-56666" in capsys.readouterr().out


def test_unknown_idp_type_and_missing_issuer_are_config_errors(w):
    assert w.run(cfg(identity_providers=[idp(type="okta")])) == 2
    assert w.run(cfg(identity_providers=[idp(type="generic_oidc")])) == 2


def test_idp_without_credentials_is_skipped_loudly_not_failed(w, monkeypatch, capsys):
    monkeypatch.delenv("G_ID")
    assert w.run(cfg(identity_providers=[idp(tenant_id="t")])) == 0
    assert "SKIPPED" in capsys.readouterr().out and not w.z.idps


def test_idp_rerun_and_login_policy(w):
    c = cfg(identity_providers=[idp(tenant_id="t-1")])
    assert w.run(c) == 0 and len(w.z.login_idps) == 1
    assert w.run(c) == 0 and len(w.z.idps) == 1
    c["identity_providers"][0]["enabled_in_login_policy"] = False
    assert w.run(c) == 0 and not w.z.login_idps


# ------------------------------------------------------------------ auth

def test_jwt_claims_use_the_issuer_as_audience(monkeypatch):
    seen = {}
    fake = types.ModuleType("jwt")
    fake.encode = lambda claims, key, algorithm, headers: seen.update(c=claims, k=key, a=algorithm, h=headers) or "t"
    monkeypatch.setitem(sys.modules, "jwt", fake)
    monkeypatch.setitem(sys.modules, "requests", types.ModuleType("requests"))
    spec = importlib.util.spec_from_file_location("zb2", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.make_jwt({"userId": "u1", "keyId": "k1", "key": "PEM"}, ISSUER)
    assert seen["c"]["iss"] == seen["c"]["sub"] == "u1" and seen["c"]["aud"] == ISSUER
    assert (seen["a"], seen["h"], seen["k"]) == ("RS256", {"kid": "k1"}, "PEM")


def test_host_header_and_audience_derive_from_instance_url(w):
    w.run(cfg())
    assert w.mod.s.headers["Host"] == "zitadel.example.com"


# ------------------------------------------------------ round 2 (N3, N5, m3)

def test_private_key_jwt_app_never_asks_for_a_client_secret(w):
    c = cfg()
    c["applications"].append({"name": "svc", "auth_method": "OIDC_AUTH_METHOD_TYPE_PRIVATE_KEY_JWT",
                              "redirect_uris": ["https://svc.example.com/cb"]})
    assert w.run(c) == 0
    assert "client-secret" not in w.k.secrets["zitadel-oidc-svc"]
    del w.k.secrets["zitadel-oidc-svc"]
    assert w.run(c) == 0, "a lost Secret of a key-authenticated app must not fail every run"
    assert not [x for x in w.z.calls if "_generate_client_secret" in x[1] and "app5" in x[1]]
    assert w.k.secrets["zitadel-oidc-svc"]["client-id"]


def test_missing_service_account_key_fails_fast_with_the_instructions(w, capsys):
    # N3: an instance that existed before FirstInstance was configured has no
    # zitadel-admin-sa Secret. The Job must say so at once, not wait for the deadline.
    (w.tmp / "key.json").unlink()
    assert w.run(cfg()) == 1
    assert not w.z.calls, "no API call, no waiting for Zitadel"
    err = capsys.readouterr().err
    assert "zitadel-admin-sa" in err and "zitadel-admin-sa.json" in err
    assert "Migrating an existing instance" in err


def test_action_script_is_scoped_to_the_configured_project(w):
    script = 'ctx.v1.user.grants.grants.filter((g) => g.projectId === "{{project_id}}")'
    assert w.run(cfg(actions=[{"name": "groupsClaim", "script": script}])) == 0
    pid = next(iter(w.z.projects))
    assert next(iter(w.z.actions.values()))["script"] == script.replace("{{project_id}}", pid)
