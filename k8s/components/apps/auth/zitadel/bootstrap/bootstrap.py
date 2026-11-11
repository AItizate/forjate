#!/usr/bin/env python3
"""
Zitadel bootstrap: create-or-update, and loud when it cannot converge.

Reads /config/bootstrap.yaml and reconciles organizations, project, roles,
Actions and flow triggers, OIDC applications (client credentials stored in K8s
Secrets; public clients store only the client-id), human users, service users
and external identity providers (Google, GitHub, Azure AD, generic OIDC)
enabled on the login policy.

Semantics (what "idempotent" means here):
  - Everything in the YAML is created when missing and UPDATED when it differs
    (roles, apps, grants, actions, IdPs, project flags). Re-running changes nothing
    when nothing differs.
  - Nothing is ever removed. Entries deleted from the YAML (an app, a grant, an IdP)
    stay in Zitadel until removed by hand.
  - A client secret is never rotated while its K8s Secret is intact. It is
    regenerated only when the Secret is missing (the API cannot read it back).
  - Exit code 0 only when every item converged. Any failed item makes the script
    exit 1 AFTER trying the rest; an invalid config exits 2 before any API call.

Auth: JWT bearer assertion signed in memory with the IAM_OWNER service account
key (Secret "zitadel-admin-sa", written by the chart's setup Job).

Env:
  ZITADEL_URL         base URL to reach Zitadel (default: the in-cluster Service)
  ZITADEL_HOST        Host header (default: host of `instance_url` in the config;
                      it must be a registered instance domain)
  ZITADEL_AUDIENCE    JWT audience (default: `instance_url`, the issuer)
  ZITADEL_KEY_FILE    service account key JSON (default /secrets/sa-key.json)
  ZITADEL_WAIT_SECONDS how long to wait for Zitadel to be ready (default 600)
  POD_NAMESPACE       namespace in which OIDC client Secrets are written
  <name>_env          every `*_env` key of the config (client_id_env,
                      client_secret_env, initial_password_env) names an env var;
                      the Job takes them from the Secret "zitadel-bootstrap-env"
"""
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

CONFIG_FILE = os.environ.get("CONFIG_FILE", "/config/bootstrap.yaml")
KEY_FILE = os.environ.get("ZITADEL_KEY_FILE", "/secrets/sa-key.json")
NAMESPACE = os.environ.get("POD_NAMESPACE", "default")
SA_DIR = Path(os.environ.get("K8S_SA_DIR", "/var/run/secrets/kubernetes.io/serviceaccount"))
K8S_API = os.environ.get("K8S_API", "https://kubernetes.default.svc")
TIMEOUT = 30

s = None  # requests.Session, created by setup_session()
ZITADEL_URL = None
FAILURES = []

# Zitadel answers 400/412 when an update changes nothing.
NOOP = re.compile(r"no changes|not changed|notchanged|not_changed", re.I)


# --------------------------------------------------------------------- errors

def say(msg):
    print(msg, flush=True)


def fatal(msg, r=None):
    """Nothing after this can work (no org, no token): stop now with exit 1."""
    if r is not None:
        say(f"  HTTP {r.status_code}: {r.text[:300]}")
    print(f"ERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def failed(msg, r=None):
    """An item did not converge: remember it, keep going, exit 1 at the end."""
    if r is not None:
        say(f"  HTTP {r.status_code}: {r.text[:300]}")
    say(f"  FAILED: {msg}")
    FAILURES.append(msg)


def is_noop(r):
    return (not r.ok) and bool(NOOP.search(r.text))


def exists(r):
    return r.status_code == 409 or "ALREADY_EXISTS" in r.text or "already exists" in r.text.lower()


# ----------------------------------------------------------------------- http

def setup_session(host):
    global s
    s = requests.Session()
    s.headers.update({"Host": host, "Content-Type": "application/json"})


def _org(org_id):
    return {"x-zitadel-orgid": org_id} if org_id else {}


def post(path, body=None, org_id=None):
    return s.post(f"{ZITADEL_URL}{path}", headers=_org(org_id), json=body or {}, timeout=TIMEOUT)


def put(path, body=None, org_id=None):
    return s.put(f"{ZITADEL_URL}{path}", headers=_org(org_id), json=body or {}, timeout=TIMEOUT)


def delete(path, org_id=None):
    return s.delete(f"{ZITADEL_URL}{path}", headers=_org(org_id), timeout=TIMEOUT)


def wait_for_zitadel():
    """Poll /debug/ready until it answers, with a deadline (a Job must not hang a sync)."""
    deadline = time.time() + int(os.environ.get("ZITADEL_WAIT_SECONDS", "600"))
    while True:
        try:
            if s.get(f"{ZITADEL_URL}/debug/ready", timeout=5).ok:
                say("Zitadel is ready")
                return
        except requests.RequestException as e:
            say(f"Zitadel not reachable yet ({type(e).__name__})")
        if time.time() >= deadline:
            fatal("Zitadel was not ready before ZITADEL_WAIT_SECONDS")
        time.sleep(5)


def make_jwt(key, audience):
    import jwt  # PyJWT, installed by the Job's init container

    iat = int(time.time())
    return jwt.encode(
        {"iss": key["userId"], "sub": key["userId"], "aud": audience, "iat": iat, "exp": iat + 3600},
        key["key"], algorithm="RS256", headers={"kid": key["keyId"]},
    )


def authenticate(audience):
    key = json.loads(Path(KEY_FILE).read_text())
    r = s.post(
        f"{ZITADEL_URL}/oauth/v2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "scope": "openid urn:zitadel:iam:org:project:id:zitadel:aud",
            "assertion": make_jwt(key, audience),
        },
        timeout=TIMEOUT,
    )
    if not r.ok:
        fatal("Failed to get an access token (is `instance_url` the issuer?)", r)
    s.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    say("Authenticated")


# --------------------------------------------------------------- config checks

FLOW_TYPES = {"complement_token": 2}
TRIGGER_TYPES = {"pre_userinfo_creation": 4, "pre_access_token_creation": 5}

IDP_TYPES = {
    "google": ("google", ["openid", "profile", "email"]),
    "github": ("github", ["openid", "user:email"]),
    "azure": ("azure", ["openid", "profile", "email"]),
    "generic_oidc": ("generic_oidc", ["openid", "profile", "email"]),
}
AUTO_LINKING = {
    "email": "AUTO_LINKING_OPTION_EMAIL",
    "username": "AUTO_LINKING_OPTION_USERNAME",
}
AZURE_TENANT_TYPES = {
    "AZURE_AD_TENANT_TYPE_COMMON",
    "AZURE_AD_TENANT_TYPE_ORGANIZATIONS",
    "AZURE_AD_TENANT_TYPE_CONSUMERS",
}
# Providers whose email claim the IdP does not guarantee to be verified and unique to
# the person: any tenant of Entra ID, any OIDC server. Linking on it is account takeover.
LOOSE_IDPS = {"azure", "generic_oidc"}


def organizations(cfg):
    """`organizations:` list. The singular `organization:` was documented before the
    script read it, so it stays accepted as a one-element, default list."""
    if cfg.get("organizations"):
        return cfg["organizations"]
    if cfg.get("organization"):
        say("NOTICE: `organization:` is deprecated, use `organizations: [{name, is_default: true}]`")
        return [{**cfg["organization"], "is_default": True}]
    return []


def validate_config(cfg):
    """Everything that can be checked without Zitadel. Returns a list of errors."""
    errors = []
    if not cfg.get("instance_url"):
        errors.append("instance_url is required (the public issuer URL, https://zitadel.<your-domain>)")
    for u in cfg.get("users", []):
        if "initial_password" in u:
            errors.append(
                f"user {u.get('username')}: `initial_password` is no longer accepted, a password in the "
                "ConfigMap is a password in git. Use `initial_password_env: VAR` with VAR in the "
                "Secret zitadel-bootstrap-env"
            )
    for f in cfg.get("flows", []):
        if f.get("type") not in FLOW_TYPES:
            errors.append(f"flow type {f.get('type')!r} unknown (known: {sorted(FLOW_TYPES)})")
        for t in f.get("triggers", []):
            if t not in TRIGGER_TYPES:
                errors.append(f"flow trigger {t!r} unknown (known: {sorted(TRIGGER_TYPES)})")
    for idp in cfg.get("identity_providers", []):
        errors.extend(validate_idp(idp))
    return errors


def validate_idp(idp):
    name, kind = idp.get("name", "?"), idp.get("type")
    if kind not in IDP_TYPES:
        return [f"IdP {name}: unknown type {kind!r} (known: {sorted(IDP_TYPES)})"]
    errors = []
    opts = idp.get("options", {})
    if kind == "generic_oidc" and not idp.get("issuer"):
        errors.append(f"IdP {name}: generic_oidc needs `issuer`")
    if kind == "azure":
        tenant_id, tenant_type = idp.get("tenant_id"), idp.get("tenant_type")
        if bool(tenant_id) == bool(tenant_type):
            errors.append(
                f"IdP {name}: azure needs exactly one of `tenant_id` (your Entra tenant) or an explicit "
                "`tenant_type`. There is no default: COMMON accepts any Microsoft account on earth"
            )
        elif tenant_type and tenant_type not in AZURE_TENANT_TYPES:
            errors.append(f"IdP {name}: tenant_type {tenant_type!r} unknown (known: {sorted(AZURE_TENANT_TYPES)})")
    linking = opts.get("auto_linking")
    if linking == "email" and kind in LOOSE_IDPS and not idp.get("trust_idp_email"):
        errors.append(
            f"IdP {name}: auto_linking=email on a {kind} provider refused. The email claim of an Entra tenant "
            "or a generic OIDC server is not proof of who the person is, and the first login would be linked "
            "to (and become) the Zitadel user with that email, admins included. Set `trust_idp_email: true` "
            "on the entry only if you control the IdP and know it verifies emails"
        )
    if linking == "username" and not idp.get("trust_idp_username"):
        errors.append(
            f"IdP {name}: auto_linking=username refused for every external provider. The username/login is "
            "chosen by whoever registers it (a GitHub login, an Entra UPN), so anyone who registers the "
            "login `admin`, or the login of a user in your closed set, is linked to that Zitadel user on "
            "first login and inherits its grants. Use auto_linking=email on google/github. Set "
            "`trust_idp_username: true` only for an IdP you operate, where usernames are assigned by you"
        )
    if opts.get("auto_linking") and opts["auto_linking"] not in AUTO_LINKING:
        errors.append(f"IdP {name}: auto_linking {opts['auto_linking']!r} unknown (known: {sorted(AUTO_LINKING)})")
    return errors


# ---------------------------------------------------------------- org/project

def ensure_org(name):
    r = post("/v2/organizations/_search", {
        "queries": [{"nameQuery": {"name": name, "method": "TEXT_QUERY_METHOD_EQUALS"}}]
    })
    if not r.ok:
        fatal(f"search org {name}", r)
    if r.json().get("result"):
        oid = r.json()["result"][0]["id"]
        say(f"Org exists: {name} ({oid})")
        return oid
    r = post("/v2/organizations", {"name": name})
    if not r.ok:
        fatal(f"create org {name}", r)
    oid = r.json()["organizationId"]
    say(f"Org created: {name} ({oid})")
    return oid


def ensure_project(name, org_id):
    flags = {"projectRoleAssertion": True, "projectRoleCheck": True}
    r = post("/management/v1/projects/_search", {
        "queries": [{"nameQuery": {"name": name, "method": "TEXT_QUERY_METHOD_EQUALS"}}]
    }, org_id=org_id)
    if not r.ok:
        fatal(f"search project {name}", r)
    if r.json().get("result"):
        pid = r.json()["result"][0]["id"]
        u = put(f"/management/v1/projects/{pid}", {"name": name, **flags}, org_id=org_id)
        if not (u.ok or is_noop(u)):
            failed(f"update project {name}", u)
        say(f"Project exists: {name} ({pid})")
        return pid
    r = post("/management/v1/projects", {"name": name, **flags}, org_id=org_id)
    if not r.ok:
        fatal(f"create project {name}", r)
    pid = r.json()["id"]
    say(f"Project created: {name} ({pid})")
    return pid


def ensure_role(project_id, org_id, role):
    body = {"displayName": role.get("display_name", role["key"]), "group": role.get("group", "")}
    r = post(f"/management/v1/projects/{project_id}/roles", {"roleKey": role["key"], **body}, org_id=org_id)
    if r.ok:
        say(f"  Role created: {role['key']}")
    elif exists(r):
        u = put(f"/management/v1/projects/{project_id}/roles/{role['key']}", body, org_id=org_id)
        if u.ok or is_noop(u):
            say(f"  Role exists: {role['key']}")
        else:
            failed(f"update role {role['key']}", u)
    else:
        failed(f"create role {role['key']}", r)


# ------------------------------------------------------------------ OIDC apps

def oidc_body(app):
    return {
        "redirectUris": app.get("redirect_uris", []),
        "postLogoutRedirectUris": app.get("post_logout_redirect_uris", []),
        "responseTypes": app.get("response_types", ["OIDC_RESPONSE_TYPE_CODE"]),
        "grantTypes": app.get("grant_types", ["OIDC_GRANT_TYPE_AUTHORIZATION_CODE"]),
        "authMethodType": app.get("auth_method", "OIDC_AUTH_METHOD_TYPE_BASIC"),
        "appType": app.get("app_type", "OIDC_APP_TYPE_WEB"),
        "accessTokenType": app.get("access_token_type", "OIDC_TOKEN_TYPE_JWT"),
        # Without these, Zitadel does not include the
        # urn:zitadel:iam:org:project:roles claim in the tokens, and
        # oauth2-proxy's allowed-group check rejects every login.
        "accessTokenRoleAssertion": app.get("access_token_role_assertion", True),
        "idTokenRoleAssertion": app.get("id_token_role_assertion", True),
        "idTokenUserinfoAssertion": app.get("id_token_userinfo_assertion", True),
    }


def ensure_oidc_app(project_id, org_id, app):
    """Create the app or update its OIDC config. Returns (app_id, client_id, client_secret);
    client_secret is only known right after creation."""
    r = post(f"/management/v1/projects/{project_id}/apps/_search", {
        "queries": [{"nameQuery": {"name": app["name"], "method": "TEXT_QUERY_METHOD_EQUALS"}}]
    }, org_id=org_id)
    if not r.ok:
        failed(f"search app {app['name']}", r)
        return None, None, None
    if r.json().get("result"):
        existing = r.json()["result"][0]
        aid = existing["id"]
        cid = existing.get("oidcConfig", {}).get("clientId")
        u = put(f"/management/v1/projects/{project_id}/apps/{aid}/oidc_config", oidc_body(app), org_id=org_id)
        if u.ok:
            say(f"App updated: {app['name']} ({aid}) clientId={cid}")
        elif is_noop(u):
            say(f"App exists: {app['name']} ({aid}) clientId={cid}")
        else:
            failed(f"update app {app['name']}", u)
        return aid, cid, None
    r = post(f"/management/v1/projects/{project_id}/apps/oidc", {"name": app["name"], **oidc_body(app)}, org_id=org_id)
    if not r.ok:
        failed(f"create app {app['name']}", r)
        return None, None, None
    j = r.json()
    say(f"App created: {app['name']} ({j['appId']}) clientId={j.get('clientId')}")
    return j["appId"], j.get("clientId"), j.get("clientSecret")


def regenerate_client_secret(project_id, org_id, app_id, app_name):
    r = post(f"/management/v1/projects/{project_id}/apps/{app_id}/oidc_config/_generate_client_secret", org_id=org_id)
    if not r.ok:
        failed(f"regenerate the client secret of {app_name}", r)
        return None
    say(f"  WARNING: client secret of {app_name} REGENERATED (its Secret was missing); "
        "copies of the old secret elsewhere are now invalid")
    return r.json().get("clientSecret")


# --------------------------------------------------------------------- K8s API

def k8s(method, name="", body=None, patch=False):
    token = (SA_DIR / "token").read_text().strip()
    kwargs = {"headers": {"Authorization": f"Bearer {token}"}, "verify": str(SA_DIR / "ca.crt"), "timeout": TIMEOUT}
    if patch:
        kwargs["headers"]["Content-Type"] = "application/merge-patch+json"
        kwargs["data"] = json.dumps(body)
    elif body is not None:
        kwargs["headers"]["Content-Type"] = "application/json"
        kwargs["json"] = body
    url = f"{K8S_API}/api/v1/namespaces/{NAMESPACE}/secrets" + (f"/{name}" if name else "")
    return requests.request(method, url, **kwargs)


def reconcile_oidc_secret(app, project_id, org_id, app_id, client_id, client_secret, issuer):
    """Make the Secret zitadel-oidc-<app> hold client-id, issuer-url and (confidential
    clients) client-secret, without rotating a secret that is still intact."""
    if not client_id:
        failed(f"app {app['name']}: no clientId to store")
        return
    name = f"zitadel-oidc-{app['name']}"
    public = app.get("auth_method") == "OIDC_AUTH_METHOD_TYPE_NONE"
    cur = k8s("GET", name)
    if cur.status_code == 404:
        current = None
    elif cur.ok:
        current = {k: base64.b64decode(v).decode() for k, v in (cur.json().get("data") or {}).items()}
    else:
        failed(f"read Secret {name}", cur)
        return
    desired = {"client-id": client_id, "issuer-url": issuer}
    if client_secret:
        desired["client-secret"] = client_secret
    elif not public and not (current and current.get("client-secret")):
        regenerated = regenerate_client_secret(project_id, org_id, app_id, app["name"])
        if not regenerated:
            return
        desired["client-secret"] = regenerated
    if current is None:
        body = {
            "apiVersion": "v1", "kind": "Secret",
            "metadata": {"name": name, "labels": {"app.kubernetes.io/managed-by": "zitadel-bootstrap"}},
            "type": "Opaque", "stringData": desired,
        }
        r = k8s("POST", body=body)
        verb = "created"
    elif any(current.get(k) != v for k, v in desired.items()):
        r = k8s("PATCH", name, {"stringData": desired}, patch=True)
        verb = "updated"
    else:
        say(f"  Secret {name} up to date")
        return
    if r.ok:
        say(f"  Secret {name} {verb}")
    else:
        failed(f"write Secret {name}", r)


# -------------------------------------------------------------- actions/flows

def ensure_action(act, org_id):
    r = post("/management/v1/actions/_search", {
        "queries": [{"actionNameQuery": {"name": act["name"], "method": "TEXT_QUERY_METHOD_EQUALS"}}]
    }, org_id=org_id)
    if not r.ok:
        failed(f"search action {act['name']}", r)
        return None
    body = {
        "name": act["name"],
        "script": act["script"],
        "timeout": act.get("timeout", "10s"),
        # An action that fails and is not allowed to fail blocks every login.
        "allowedToFail": act.get("allowed_to_fail", True),
    }
    if r.json().get("result"):
        aid = r.json()["result"][0]["id"]
        u = put(f"/management/v1/actions/{aid}", body, org_id=org_id)
        if u.ok:
            say(f"Action updated: {act['name']} ({aid})")
        elif is_noop(u):
            say(f"Action exists: {act['name']} ({aid})")
        else:
            failed(f"update action {act['name']}", u)
        return aid
    r = post("/management/v1/actions", body, org_id=org_id)
    if not r.ok:
        failed(f"create action {act['name']}", r)
        return None
    aid = r.json()["id"]
    say(f"Action created: {act['name']} ({aid})")
    return aid


def set_flow_triggers(flow, action_ids, org_id):
    wanted = flow.get("actions", [])
    missing = [n for n in wanted if not action_ids.get(n)]
    if missing:
        failed(f"flow {flow['type']}: action(s) {missing} not available, trigger left untouched")
        return
    ids = [action_ids[n] for n in wanted]
    for trig in flow.get("triggers", []):
        r = post(f"/management/v1/flows/{FLOW_TYPES[flow['type']]}/trigger/{TRIGGER_TYPES[trig]}",
                 {"actionIds": ids}, org_id=org_id)
        if r.ok or is_noop(r):
            say(f"  Flow {flow['type']}/{trig} -> {wanted}")
        else:
            failed(f"set flow {flow['type']}/{trig}", r)


# ------------------------------------------------------------------ users

def grant_roles(user_id, project_id, role_keys, org_id):
    """Make the user's grant on the project carry exactly role_keys."""
    if not role_keys or not project_id:
        return
    r = post("/management/v1/users/grants/_search", {
        "queries": [{"userIdQuery": {"userId": user_id}}, {"projectIdQuery": {"projectId": project_id}}]
    }, org_id=org_id)
    if not r.ok:
        failed(f"search grants of {user_id}", r)
        return
    found = r.json().get("result") or []
    if not found:
        c = post(f"/management/v1/users/{user_id}/grants", {"projectId": project_id, "roleKeys": role_keys}, org_id=org_id)
        if c.ok:
            say(f"  Granted {role_keys} to {user_id}")
        else:
            failed(f"grant {role_keys} to {user_id}", c)
    elif sorted(found[0].get("roleKeys", [])) != sorted(role_keys):
        u = put(f"/management/v1/users/{user_id}/grants/{found[0]['id']}", {"roleKeys": role_keys}, org_id=org_id)
        if u.ok or is_noop(u):
            say(f"  Grant of {user_id} set to {role_keys}")
        else:
            failed(f"update grant of {user_id}", u)
    else:
        say(f"  Roles {role_keys} already granted to {user_id}")


def find_user(username, org_id):
    queries = [{"userNameQuery": {"userName": username, "method": "TEXT_QUERY_METHOD_EQUALS"}}]
    if org_id:
        # v2 list endpoints filter by query; the x-zitadel-orgid header is ignored.
        queries.append({"organizationIdQuery": {"organizationId": org_id}})
    r = post("/v2/users", {"queries": queries}, org_id=org_id)
    if not r.ok:
        failed(f"search user {username}", r)
        return None, True
    if r.json().get("result"):
        return r.json()["result"][0]["userId"], False
    return None, False


def ensure_human(u, project_id, orgs_by_name, default_org_id):
    org_id = orgs_by_name.get(u.get("organization"), default_org_id)
    existing, err = find_user(u["username"], org_id)
    if err:
        return None
    if existing:
        say(f"User exists: {u['username']} ({existing})")
        grant_roles(existing, project_id, u.get("roles", []), org_id)
        return existing
    password = None
    if u.get("initial_password_env"):
        password = os.environ.get(u["initial_password_env"])
        if not password:
            failed(f"user {u['username']}: env {u['initial_password_env']} is empty or unset "
                   "(is it in the Secret zitadel-bootstrap-env?)")
            return None
    # v2 AddHumanUser. The v1 users/human/_import endpoint ignores
    # initialPassword and leaves users in state INITIAL with an unverified email.
    first, last = u.get("first_name", ""), u.get("last_name", "")
    body = {
        "username": u["username"],
        "profile": {
            "givenName": first,
            "familyName": last,
            "displayName": f"{first} {last}".strip() or u["username"],
            "preferredLanguage": u.get("preferred_language", "en"),
        },
        "email": {"email": u["email"], "isVerified": u.get("email_verified", False)},
    }
    if org_id:
        body["organization"] = {"orgId": org_id}
    if password:
        body["password"] = {"password": password, "changeRequired": u.get("password_change_required", True)}
    r = post("/v2/users/human", body)
    if not r.ok:
        failed(f"create user {u['username']}", r)
        return None
    uid = r.json().get("userId")
    say(f"User created: {u['username']} ({uid})")
    grant_roles(uid, project_id, u.get("roles", []), org_id)
    return uid


def ensure_machine(svc, project_id, default_org_id):
    existing, err = find_user(svc["username"], default_org_id)
    if err:
        return None
    if existing:
        say(f"Service user exists: {svc['username']} ({existing})")
        grant_roles(existing, project_id, svc.get("roles", []), default_org_id)
        return existing
    r = post("/management/v1/users/machine", {
        "userName": svc["username"],
        "name": svc.get("name", svc["username"]),
        "description": svc.get("description", ""),
    }, org_id=default_org_id)
    if not r.ok:
        failed(f"create service user {svc['username']}", r)
        return None
    uid = r.json()["userId"]
    say(f"Service user created: {svc['username']} ({uid})")
    grant_roles(uid, project_id, svc.get("roles", []), default_org_id)
    return uid


# ----------------------------------------------------------------- IdPs

def idp_body(idp, client_id, client_secret):
    opts = idp.get("options", {})
    body = {
        "name": idp["name"],
        "clientId": client_id,
        "clientSecret": client_secret,
        "scopes": idp.get("scopes", IDP_TYPES[idp["type"]][1]),
        # Everything is off unless the config asks for it: only users that
        # already exist can sign in, and they are matched by auto_linking.
        "providerOptions": {
            "isLinkingAllowed": opts.get("is_linking_allowed", False),
            "isCreationAllowed": opts.get("is_creation_allowed", False),
            "isAutoCreation": opts.get("is_auto_creation", False),
            "isAutoUpdate": opts.get("is_auto_update", False),
            "autoLinking": AUTO_LINKING.get(opts.get("auto_linking"), "AUTO_LINKING_OPTION_UNSPECIFIED"),
        },
    }
    if idp["type"] == "generic_oidc":
        body["issuer"] = idp["issuer"]
    if idp["type"] == "azure":
        # validate_config guarantees exactly one of tenant_id / tenant_type.
        if idp.get("tenant_id"):
            body["tenant"] = {"tenantId": idp["tenant_id"]}
        else:
            body["tenant"] = {"tenantType": idp["tenant_type"]}
        # An Entra `email` claim is user-editable unless the tenant verifies it.
        body["emailVerified"] = idp.get("email_verified", False)
    return body


def ensure_login_policy_idp(idp_id, enabled):
    # An IdP template is only offered on the login page once it is linked
    # to the login policy.
    r = post("/admin/v1/policies/login/idps/_search", {})
    if not r.ok:
        failed(f"read the login policy IdPs for {idp_id}", r)
        return
    linked = any(i.get("idpId") == idp_id for i in r.json().get("result", []))
    if enabled and not linked:
        r = post("/admin/v1/policies/login/idps", {"idpId": idp_id, "ownerType": "IDP_OWNER_TYPE_SYSTEM"})
        if r.ok:
            say(f"  IdP {idp_id} added to the login policy")
        else:
            failed(f"add IdP {idp_id} to the login policy", r)
    elif not enabled and linked:
        r = delete(f"/admin/v1/policies/login/idps/{idp_id}")
        if r.ok:
            say(f"  IdP {idp_id} removed from the login policy")
        else:
            failed(f"remove IdP {idp_id} from the login policy", r)
    else:
        say(f"  IdP {idp_id} login policy unchanged (enabled={enabled})")


def ensure_identity_provider(idp):
    kind = idp["type"]
    opts = idp.get("options", {})
    client_id = os.environ.get(idp.get("client_id_env", ""))
    client_secret = os.environ.get(idp.get("client_secret_env", ""))
    if not (client_id and client_secret):
        say(f"IdP {idp['name']}: SKIPPED, credentials not provided "
            f"({idp.get('client_id_env')}, {idp.get('client_secret_env')})")
        return
    if opts.get("auto_linking"):
        say(f"  NOTICE: {idp['name']} auto-links by {opts['auto_linking']}. Zitadel < 4.15.3 does not check that "
            "the IdP verified the email (CVE-2026-56666); only enable this for IdPs that verify emails")
    if idp.get("trust_idp_email"):
        say(f"  WARNING: {idp['name']} has trust_idp_email=true: whoever can set the email at that IdP "
            "becomes the Zitadel user with that email")
    if idp.get("trust_idp_username"):
        say(f"  WARNING: {idp['name']} has trust_idp_username=true: whoever can pick a username at that IdP "
            "becomes the Zitadel user with that username")
    body = idp_body(idp, client_id, client_secret)
    path = IDP_TYPES[kind][0]
    # /admin/v1/idps/_search returns no results for instance-level IdPs;
    # the working endpoint is /admin/v1/idps/templates/_search.
    r = post("/admin/v1/idps/templates/_search", {
        "queries": [{"idpNameQuery": {"name": idp["name"], "method": "TEXT_QUERY_METHOD_EQUALS"}}]
    })
    if not r.ok:
        failed(f"search IdP {idp['name']}", r)
        return
    if r.json().get("result"):
        idp_id = r.json()["result"][0]["id"]
        u = put(f"/admin/v1/idps/{path}/{idp_id}", body)
        if u.ok:
            say(f"IdP updated: {idp['name']} ({idp_id})")
        elif is_noop(u):
            say(f"IdP unchanged: {idp['name']} ({idp_id})")
        else:
            failed(f"update IdP {idp['name']}", u)
            return
    else:
        c = post(f"/admin/v1/idps/{path}", body)
        if not c.ok:
            failed(f"create IdP {idp['name']}", c)
            return
        idp_id = c.json().get("id")
        say(f"IdP created: {idp['name']} ({idp_id})")
    ensure_login_policy_idp(idp_id, idp.get("enabled_in_login_policy", True))


# ------------------------------------------------------------------- main

def main():
    global ZITADEL_URL
    cfg = yaml.safe_load(Path(CONFIG_FILE).read_text()) or {}
    errors = validate_config(cfg)
    if errors:
        for e in errors:
            print(f"CONFIG ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    issuer = cfg["instance_url"].rstrip("/")
    ZITADEL_URL = os.environ.get("ZITADEL_URL") or f"http://zitadel.{NAMESPACE}.svc.cluster.local:8080"
    setup_session(os.environ.get("ZITADEL_HOST") or urlparse(issuer).netloc)
    wait_for_zitadel()
    authenticate(os.environ.get("ZITADEL_AUDIENCE") or issuer)

    orgs_by_name, default_org_id = {}, None
    for o in organizations(cfg):
        oid = ensure_org(o["name"])
        orgs_by_name[o["name"]] = oid
        if o.get("is_default") and default_org_id is None:
            default_org_id = oid
    if default_org_id is None and orgs_by_name:
        default_org_id = next(iter(orgs_by_name.values()))
    if default_org_id is None:
        say("No organization configured: using the service account's own organization")

    proj = cfg.get("project") or {}
    project_id = ensure_project(proj["name"], default_org_id) if proj.get("name") else None
    for role in proj.get("roles", []):
        ensure_role(project_id, default_org_id, role)

    action_ids = {a["name"]: ensure_action(a, default_org_id) for a in cfg.get("actions", [])}
    for flow in cfg.get("flows", []):
        set_flow_triggers(flow, action_ids, default_org_id)

    for app in cfg.get("applications", []):
        if not project_id:
            failed(f"app {app['name']}: no `project:` configured")
            continue
        app_id, cid, csec = ensure_oidc_app(project_id, default_org_id, app)
        if app_id:
            reconcile_oidc_secret(app, project_id, default_org_id, app_id, cid, csec, issuer)

    for u in cfg.get("users", []):
        ensure_human(u, project_id, orgs_by_name, default_org_id)
    for svc in cfg.get("service_users", []):
        ensure_machine(svc, project_id, default_org_id)

    for idp in cfg.get("identity_providers", []):
        ensure_identity_provider(idp)

    if FAILURES:
        say(f"=== Bootstrap FAILED: {len(FAILURES)} item(s) did not converge ===")
        for f in FAILURES:
            say(f"  - {f}")
        sys.exit(1)
    say("=== Bootstrap complete ===")


if __name__ == "__main__":
    main()
