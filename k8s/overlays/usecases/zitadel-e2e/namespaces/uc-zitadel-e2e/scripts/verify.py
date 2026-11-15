#!/usr/bin/env python3
"""Verify phase of the zitadel-e2e use case: what the mocked tests of the component cannot see.

Six behaviours of auth/zitadel, asserted against the live instance. Every check runs; the
summary decides the exit status. The Job log is public CI output, so nothing secret is ever
printed: tokens, the first user's password and client secrets stay in variables.

  1  discovery and the JWKS answer 200 through the issuer URL
  2  the bootstrap is idempotent: a second run creates nothing and rewrites nothing
  3  the `groups` claim reaches the id_token of a seeded user with a project role
  4  IdP linking settings: auto_linking applies them, is_linking_allowed: false exits 2
  5  a FirstInstance admin email shared with a user: exit 1, `belongs to 2 users`
  6  self-registration is off by default and on with login_policy.allow_register: true

Standard library plus PyYAML (both in alpine/k8s). The admin token comes from the JWT-bearer
grant with the key of Secret zitadel-admin-sa, signed here with a few lines of RSA arithmetic
(the image has neither PyJWT nor an openssl binary). The login for assertion 3 is the
production path without the browser: authorize -> session API (password check) -> auth
request callback -> code exchange.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

ISSUER = os.environ["ISSUER"].rstrip("/")
LOGIN_URL = os.environ["LOGIN_URL"].rstrip("/")
KEY_FILE = os.environ["ADMIN_SA_KEY_FILE"]
LOGIN_KEY_FILE = os.environ["LOGIN_SERVICE_KEY_FILE"]
ANA_PASSWORD = os.environ["ANA_INITIAL_PASSWORD"]
SCRIPTS = os.environ.get("SCRIPTS", "/scripts")
TIMEOUT = 30

# What bootstrap.yaml of this use case declares (the tenant file next to this script).
ORG, PROJECT, APP, IDP = "e2e", "platform", "portal", "Google"
APP_REDIRECT = "https://portal.example.test/callback"
SEEDED_USER, SEEDED_ROLE = "ana", "admin"
FIRST_ADMIN = "admin"  # FirstInstance.Org.Human.UserName

PASSED = FAILED = 0
TOKEN = ""


# --------------------------------------------------------------------- report

def section(title):
    print(f"\n== {title}", flush=True)


def check(description, ok, detail=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [PASS] {description}", flush=True)
    else:
        FAILED += 1
        print(f"  [FAIL] {description}" + (f": {detail}" if detail else ""), flush=True)
    return bool(ok)


def excerpt(log, pattern, limit=4):
    """The lines of a bootstrap log that matter, for a failure message."""
    lines = [line.strip() for line in log.splitlines() if re.search(pattern, line, re.I)]
    return " | ".join(lines[:limit]) or "(no such line)"


# ----------------------------------------------------------------------- http

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http(method, url, json_body=None, form=None, headers=None):
    """(status, lower-cased headers, text). Status 0 when nothing answers."""
    data, hdrs = None, dict(headers or {})
    if json_body is not None:
        data, hdrs["Content-Type"] = json.dumps(json_body).encode(), "application/json"
    elif form is not None:
        data, hdrs["Content-Type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with _OPENER.open(request, timeout=TIMEOUT) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode()
    except (urllib.error.URLError, OSError) as e:
        return 0, {}, str(e)


def api(method, path, body=None, org=None, token=None):
    """A call to the Zitadel API, by default as the IAM_OWNER service account: (status, json)."""
    headers = {"Authorization": f"Bearer {token or TOKEN}"}
    if org:
        headers["x-zitadel-orgid"] = org
    if body is None and method in ("POST", "PUT"):
        body = {}
    status, _, text = http(method, ISSUER + path, json_body=body, headers=headers)
    try:
        return status, (json.loads(text) if text else {})
    except ValueError:
        return status, {"raw": text[:200]}


def search(path, queries=None, org=None):
    """A list call, one explicit page (Zitadel >= 4.19.5 drops the implicit limit)."""
    body = {"query": {"limit": 1000}}
    if queries:
        body["queries"] = queries
    return api("POST", path, body, org)


def name_query(name, key="nameQuery", field="name"):
    return {key: {field: name, "method": "TEXT_QUERY_METHOD_EQUALS"}}


# ------------------------------------------------------------- JWT, RSA, base64

def b64u(raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def unb64u(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _der(buf, pos):
    """(start, end) of the content of the DER element at pos."""
    length, pos = buf[pos + 1], pos + 2
    if length & 0x80:
        count = length & 0x7F
        length, pos = int.from_bytes(buf[pos:pos + count], "big"), pos + count
    return pos, pos + length


def _der_items(der):
    pos, end = _der(der, 0)
    items = []
    while pos < end:
        start, stop = _der(der, pos)
        items.append(der[start:stop])
        pos = stop
    return items


def rsa_private(pem):
    """(n, d) of a PKCS#1 or PKCS#8 RSA private key in PEM."""
    der = base64.b64decode("".join(line for line in pem.splitlines() if line and not line.startswith("-----")))
    items = _der_items(der)
    if "BEGIN PRIVATE KEY" in pem:  # PKCS#8: version, algorithm, OCTET STRING holding the PKCS#1 key
        items = _der_items(items[2])
    return int.from_bytes(items[1], "big"), int.from_bytes(items[3], "big")


_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


def _emsa(signing_input, size):
    t = _SHA256 + hashlib.sha256(signing_input).digest()
    return b"\x00\x01" + b"\xff" * (size - len(t) - 3) + b"\x00" + t


def rs256_sign(signing_input, n, d):
    size = (n.bit_length() + 7) // 8
    return pow(int.from_bytes(_emsa(signing_input, size), "big"), d, n).to_bytes(size, "big")


def rs256_verify(signing_input, signature, n, e):
    size = (n.bit_length() + 7) // 8
    return pow(int.from_bytes(signature, "big"), e, n).to_bytes(size, "big") == _emsa(signing_input, size)


def admin_token():
    """An IAM_OWNER access token: JWT-bearer grant with the key of the setup Job's service account."""
    key = json.loads(open(KEY_FILE).read())
    now = int(time.time())
    claims = {"iss": key["userId"], "sub": key["userId"], "aud": ISSUER, "iat": now, "exp": now + 3600}
    signing_input = (b64u(json.dumps({"alg": "RS256", "kid": key["keyId"], "typ": "JWT"})) + "." + b64u(json.dumps(claims)))
    n, d = rsa_private(key["key"])
    assertion = signing_input + "." + b64u(rs256_sign(signing_input.encode(), n, d))
    status, _, text = http("POST", ISSUER + "/oauth/v2/token", form={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "scope": "openid urn:zitadel:iam:org:project:id:zitadel:aud",
        "assertion": assertion,
    })
    if status != 200:
        raise RuntimeError(f"token endpoint answered {status}: {text[:200]}")
    return json.loads(text)["access_token"]


def login_client_token():
    """The bearer the Login V2 service itself uses: a JWT of the system user `login-client` (role
    IAM_LOGIN_CLIENT, SystemAPIUsers of the chart), signed with the keypair of Secret
    zitadel-login-service-key. Only this identity may complete an auth request with a session."""
    now = int(time.time())
    claims = {"iss": "login-client", "sub": "login-client", "aud": ISSUER, "iat": now, "exp": now + 3600}
    signing_input = b64u(json.dumps({"alg": "RS256", "typ": "JWT"})) + "." + b64u(json.dumps(claims))
    n, d = rsa_private(open(LOGIN_KEY_FILE).read())
    return signing_input + "." + b64u(rs256_sign(signing_input.encode(), n, d))


def verify_jwt(token, jwks):
    """The claims of an RS256 JWT whose signature is one of the JWKS keys, else None."""
    header_b64, payload_b64, signature_b64 = token.split(".")
    kid = json.loads(unb64u(header_b64)).get("kid")
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") == kid and jwk.get("kty") == "RSA":
            n, e = int.from_bytes(unb64u(jwk["n"]), "big"), int.from_bytes(unb64u(jwk["e"]), "big")
            if rs256_verify(f"{header_b64}.{payload_b64}".encode(), unb64u(signature_b64), n, e):
                return json.loads(unb64u(payload_b64))
    return None


# ----------------------------------------------------------------- kubernetes

def kubectl(*args, stdin=None):
    return subprocess.run(["kubectl", *args], capture_output=True, text=True, input=stdin)


def read_secret(name):
    """{"rv": resourceVersion, "data": {key: value}} of a Secret in this namespace."""
    r = kubectl("get", "secret", name, "-o", "json")
    if r.returncode != 0:
        raise RuntimeError(f"Secret {name}: {r.stderr.strip()[:200]}")
    obj = json.loads(r.stdout)
    return {"rv": obj["metadata"]["resourceVersion"],
            "data": {k: base64.b64decode(v).decode() for k, v in (obj.get("data") or {}).items()}}


def bootstrap_secrets():
    """Every Secret the bootstrap wrote (label managed-by=zitadel-bootstrap), by name."""
    r = kubectl("get", "secrets", "-l", "app.kubernetes.io/managed-by=zitadel-bootstrap", "-o", "json")
    if r.returncode != 0:
        raise RuntimeError(f"list Secrets: {r.stderr.strip()[:200]}")
    return {o["metadata"]["name"]: {"rv": o["metadata"]["resourceVersion"], "data": o.get("data") or {}}
            for o in json.loads(r.stdout)["items"]}


def run_bootstrap(run_name, mutate=None):
    """Run the bootstrap Job once (scripts/run-hook.sh). With `mutate`, on the tenant's
    bootstrap.yaml with that change applied. Returns (exit code of bootstrap.py, log)."""
    command = ["sh", f"{SCRIPTS}/run-hook.sh", "zitadel-bootstrap", run_name]
    config_map = f"{run_name}-config"
    if mutate:
        live = kubectl("get", "configmap", "zitadel-bootstrap-config", "-o", r"jsonpath={.data.bootstrap\.yaml}")
        config = yaml.safe_load(live.stdout)
        mutate(config)
        path = f"/tmp/{run_name}.yaml"
        with open(path, "w") as f:
            yaml.safe_dump(config, f, sort_keys=False)
        kubectl("delete", "configmap", config_map, "--ignore-not-found")
        made = kubectl("create", "configmap", config_map, f"--from-file=bootstrap.yaml={path}")
        if made.returncode != 0:
            raise RuntimeError(f"ConfigMap {config_map}: {made.stderr.strip()[:200]}")
        command.append(config_map)
    try:
        p = subprocess.run(command, capture_output=True, text=True, env={**os.environ, "HOOK_LOG_TAIL": "300"})
    finally:
        if mutate:
            kubectl("delete", "configmap", config_map, "--ignore-not-found")
    return p.returncode, p.stdout + p.stderr


# --------------------------------------------------------------- zitadel state

def must(status_data, what):
    status, data = status_data
    if status != 200:
        raise RuntimeError(f"{what}: HTTP {status} {json.dumps(data)[:200]}")
    return data


def user_ids():
    """{username: userId} of every user of the instance."""
    return {u["username"]: u["userId"] for u in must(search("/v2/users"), "list users").get("result", [])
            if u.get("username")}


def idp_templates():
    """{name: template} of the instance IdP templates."""
    return {t["name"]: t for t in must(search("/admin/v1/idps/templates/_search"), "list IdP templates").get("result", [])}


def login_policy():
    return must(api("GET", "/admin/v1/policies/login"), "read the login policy").get("policy", {})


def snapshot():
    """Everything a second bootstrap run must leave as it is."""
    org = must(search("/v2/organizations/_search", [name_query(ORG)]), "find the organization")["result"][0]["id"]
    project = must(search("/management/v1/projects/_search", [name_query(PROJECT)], org), "find the project")["result"][0]["id"]
    apps = must(search(f"/management/v1/projects/{project}/apps/_search", org=org), "list the apps").get("result", [])
    policy = login_policy()
    return {
        "org": org,
        "project": project,
        "apps": {a["name"]: [a["id"], (a.get("oidcConfig") or {}).get("clientId")] for a in apps},
        "users": user_ids(),
        "idps": {n: t["id"] for n, t in idp_templates().items()},
        "login policy changed": (policy.get("details") or {}).get("changeDate"),
        "client Secrets": bootstrap_secrets(),
    }


def differences(before, after):
    return [key for key in before if before[key] != after.get(key)]


# ------------------------------------------------------------------ assertions

def assert_discovery():
    section("1. Discovery and JWKS answer 200 through the issuer URL")
    status, _, text = http("GET", ISSUER + "/.well-known/openid-configuration")
    doc = json.loads(text) if status == 200 else {}
    check(f"GET {ISSUER}/.well-known/openid-configuration -> 200", status == 200, f"HTTP {status}")
    check("the document's issuer is the issuer URL", doc.get("issuer") == ISSUER, f"issuer {doc.get('issuer')!r}")
    jwks_uri = doc.get("jwks_uri", "")
    check("jwks_uri is under the issuer URL", jwks_uri.startswith(ISSUER + "/"), f"jwks_uri {jwks_uri!r}")
    status, _, text = http("GET", jwks_uri or ISSUER + "/oauth/v2/keys")
    keys = json.loads(text).get("keys", []) if status == 200 else []
    check("the advertised jwks_uri -> 200 with at least one RSA key", status == 200 and any(k.get("kty") == "RSA" for k in keys),
          f"HTTP {status}, {len(keys)} key(s)")
    return doc


def assert_idempotent(before):
    section("2. The bootstrap is idempotent: a second run creates nothing, rewrites nothing")
    rc, log = run_bootstrap("zitadel-bootstrap-again")
    check("the second run exits 0", rc == 0, f"exit {rc}: {excerpt(log, 'FAILED|ERROR')}")
    check("no `created` line in its log", not re.search(r"\bcreated\b", log, re.I), excerpt(log, r"\bcreated\b"))
    check("no client secret regenerated", "REGENERATED" not in log, excerpt(log, "REGENERATED"))
    check("login policy: read, not written (`allowRegister unchanged`)", "Login policy allowRegister unchanged" in log,
          excerpt(log, "Login policy"))
    check("features: read, not written (`loginV2 unchanged`)", "Feature loginV2 unchanged" in log, excerpt(log, "Feature"))
    after = snapshot()
    changed = differences(before, after)
    check("same org, project, apps, users and IdP ids; login policy untouched", not [c for c in changed if c != "client Secrets"],
          "changed: " + ", ".join(changed))
    check("same zitadel-oidc-<app> Secrets (resourceVersion and data: not rewritten)", before["client Secrets"] == after["client Secrets"]
          and any(n == f"zitadel-oidc-{APP}" for n in after["client Secrets"]),
          f"Secrets before {sorted(before['client Secrets'])}, after {sorted(after['client Secrets'])}")
    return rc


def login_as_seeded_user(ids, jwks):
    """The authorization-code flow, with the session API in place of the Login V2 pages."""
    client = read_secret(f"zitadel-oidc-{APP}")["data"]
    state = "e2e-" + os.urandom(6).hex()
    query = urllib.parse.urlencode({"client_id": client["client-id"], "redirect_uri": APP_REDIRECT,
                                    "response_type": "code", "scope": "openid profile email", "state": state})
    status, headers, _ = http("GET", f"{ISSUER}/oauth/v2/authorize?{query}")
    location = headers.get("location", "")
    request_id = (urllib.parse.parse_qs(urllib.parse.urlparse(location).query).get("authRequest") or [""])[0]
    check("authorize redirects to the Login V2 page with an auth request", status in (302, 303) and "/ui/v2/login" in location and request_id,
          f"HTTP {status}, Location {location[:120]!r}")
    if not request_id:
        return None, None
    login = login_client_token()
    status, session = api("POST", "/v2/sessions", {"checks": {"user": {"userId": ids[SEEDED_USER]}, "password": {"password": ANA_PASSWORD}}},
                          token=login)
    # No body in the message: a session carries a token.
    check(f"{SEEDED_USER} signs in with the password of zitadel-bootstrap-env (session API, as the login service)",
          status in (200, 201) and session.get("sessionToken"), f"HTTP {status} {session.get('message', '')}")
    if not session.get("sessionToken"):
        return request_id, None
    status, callback = api("POST", f"/v2/oidc/auth_requests/{request_id}",
                           {"session": {"sessionId": session["sessionId"], "sessionToken": session["sessionToken"]}}, token=login)
    target = urllib.parse.urlparse(callback.get("callbackUrl", ""))
    params = urllib.parse.parse_qs(target.query)
    code = (params.get("code") or [""])[0]
    check("the auth request completes with a callback URL carrying a code and the state",
          status == 200 and code and (params.get("state") or [""])[0] == state and callback["callbackUrl"].startswith(APP_REDIRECT),
          f"HTTP {status} {json.dumps(callback)[:200]}")
    if not code:
        return request_id, None
    basic = base64.b64encode(f"{urllib.parse.quote(client['client-id'], safe='')}:{urllib.parse.quote(client['client-secret'], safe='')}".encode()).decode()
    status, _, text = http("POST", ISSUER + "/oauth/v2/token", headers={"Authorization": f"Basic {basic}"},
                           form={"grant_type": "authorization_code", "code": code, "redirect_uri": APP_REDIRECT})
    id_token = json.loads(text).get("id_token") if status == 200 else None
    check("the code is exchanged for an id_token", bool(id_token), f"HTTP {status}: {text[:200] if status != 200 else 'no id_token'}")
    return request_id, (verify_jwt(id_token, jwks) if id_token else None)


def assert_groups_claim(ids, jwks):
    section("3. The groups claim is in the id_token of a seeded user with a project role")
    _, claims = login_as_seeded_user(ids, jwks)
    check("the id_token is signed by a key of the JWKS", claims is not None)
    if claims is None:
        return
    groups = claims.get("groups")
    check(f"claim groups == [{SEEDED_ROLE!r}] (the role of the user's grant on project {PROJECT})", groups == [SEEDED_ROLE],
          f"groups {groups!r}, claims {sorted(claims)}")


def provider_options(template):
    """The linking options of an IdP template, wherever the API nests them (v1 admin API:
    template["config"]["options"]). Proto3 JSON leaves a `false` out: read a missing flag as false."""
    flat = {}

    def walk(node):
        for key, value in node.items():
            if isinstance(value, dict):
                walk(value)
            else:
                flat[key] = value

    walk(template)
    return flat


def shape(value):
    """Key names only, for a failure message: {key: {nested keys}}."""
    return {k: shape(v) if isinstance(v, dict) else None for k, v in value.items()}


def assert_linking(templates):
    section("4. Linking settings reach the IdP template; auto_linking with is_linking_allowed: false exits 2")
    template = templates.get(IDP)
    check(f"IdP template {IDP} exists (placeholder credentials)", template is not None, f"templates: {sorted(templates)}")
    if template is not None:
        options = provider_options(template)
        check("auto_linking: email -> isLinkingAllowed=true", options.get("isLinkingAllowed") is True, f"isLinkingAllowed {options.get('isLinkingAllowed')!r}, template keys {shape(template)}")
        check("... isCreationAllowed=false (linking never creates users)", options.get("isCreationAllowed", False) is False, f"isCreationAllowed {options.get('isCreationAllowed')!r}")
        check("... autoLinking=AUTO_LINKING_OPTION_EMAIL", options.get("autoLinking") == "AUTO_LINKING_OPTION_EMAIL", f"autoLinking {options.get('autoLinking')!r}")

    def linking_off(config):
        for idp in config["identity_providers"]:
            idp["options"]["is_linking_allowed"] = False

    rc, log = run_bootstrap("zitadel-bootstrap-linking-off", linking_off)
    check("auto_linking with is_linking_allowed: false exits 2 (config error, before any API call)", rc == 2, f"exit {rc}: {excerpt(log, 'ERROR|FAILED')}")
    check("... and says why", "is_linking_allowed" in log and "CONFIG ERROR" in log, excerpt(log, "CONFIG ERROR"))
    after = idp_templates().get(IDP)
    check("... and the template is left as it was", after == template, "the template changed")


def assert_self_registration():
    section("6. Self-registration is off by default, and on only with login_policy.allow_register: true")
    allow = login_policy().get("allowRegister", False)
    check("GET /admin/v1/policies/login: allowRegister=false after the first run (Zitadel ships true)", allow is False, f"allowRegister {allow!r}")
    rc, log = run_bootstrap("zitadel-bootstrap-register-on", lambda config: config.update({"login_policy": {"allow_register": True}}))
    check("a run with login_policy.allow_register: true exits 0", rc == 0, f"exit {rc}: {excerpt(log, 'FAILED|ERROR')}")
    allow = login_policy().get("allowRegister", False)
    check("... and allowRegister=true", allow is True, f"allowRegister {allow!r}")
    rc, log = run_bootstrap("zitadel-bootstrap-register-off")
    allow = login_policy().get("allowRegister", False)
    check("the tenant's bootstrap.yaml again switches it off on the next run", rc == 0 and allow is False, f"exit {rc}, allowRegister {allow!r}")


def remove_user(username, created=None):
    """Delete a user and wait until the (eventually consistent) user list stops showing it.
    `created` is the match of the bootstrap's `User created: <name> (<id>)` line, when there is one:
    right after a create the list may not show the user yet, the id is the reliable handle."""
    user_id = created.group(1) if created else user_ids().get(username)
    if user_id:
        api("DELETE", f"/v2/users/{user_id}")
    deadline = time.time() + 30
    while username in user_ids():
        if time.time() > deadline:
            return False
        time.sleep(2)
    return True


def assert_unique_emails(ids, second_run_rc):
    section("5. The FirstInstance admin's email must not belong to another user")
    users = must(search("/v2/users", [{"typeQuery": {"type": "TYPE_HUMAN"}}]), "list human users").get("result", [])
    # The login name of the first admin carries the instance domain: admin@zitadel.<ExternalDomain>.
    admin = next((u for u in users if u.get("username") == FIRST_ADMIN or str(u.get("username", "")).startswith(FIRST_ADMIN + "@")), None)
    email = ((admin or {}).get("human") or {}).get("email", {}).get("email", "")
    if not check(f"the FirstInstance admin ({FIRST_ADMIN}) is a human user with an email", bool(email), f"human users: {sorted(u.get('username', '?') for u in users)}"):
        return
    check("positive run: distinct emails, auto_linking: email active -> exit 0", second_run_rc == 0, f"exit {second_run_rc}")

    def share_the_admin_email(config):
        config["users"].append({"username": "dup-admin", "first_name": "Dup", "last_name": "Admin", "email": email, "email_verified": True})

    remove_user("dup-admin")  # a leftover of an interrupted run would fail every bootstrap run
    log = ""
    try:
        rc, log = run_bootstrap("zitadel-bootstrap-dup-email", share_the_admin_email)
        check("negative run: a user with the admin's email -> exit 1", rc == 1, f"exit {rc}: {excerpt(log, 'FAILED|ERROR')}")
        check("... and the log says `belongs to 2 users`", "belongs to 2 users" in log, excerpt(log, "email|FAILED"))
    finally:
        # Leave the instance as found: the next run (a second `up`) must see distinct emails.
        check("the duplicate user is removed again", remove_user("dup-admin", re.search(r"User created: dup-admin \((\d+)\)", log)))


def assert_login_service():
    section("Login V2 service answers")
    status, _, _ = http("GET", LOGIN_URL + "/ui/v2/login/healthy")
    check("zitadel-login /healthy -> 200", status == 200, f"HTTP {status}")


# ------------------------------------------------------------------------ main

def guarded(function, *args):
    try:
        return function(*args)
    except Exception as e:  # one broken section must not hide the others
        check(f"{function.__name__} ran to the end", False, f"{type(e).__name__}: {e}")
        return None


def main():
    global TOKEN
    deadline = time.time() + 180
    while http("GET", ISSUER + "/debug/ready")[0] != 200 and time.time() < deadline:
        time.sleep(3)

    guarded(assert_discovery)
    jwks = json.loads(http("GET", ISSUER + "/oauth/v2/keys")[2] or "{}")

    section("Admin API token")
    try:
        TOKEN = admin_token()
    except Exception as e:
        check("the key of Secret zitadel-admin-sa gets an IAM_OWNER token (JWT-bearer grant)", False, f"{type(e).__name__}: {e}")
        print(f"\nRESULT: {PASSED} passed, {FAILED} failed (no token: the checks that need the admin API were skipped)")
        sys.exit(1)
    check("the key of Secret zitadel-admin-sa gets an IAM_OWNER token (JWT-bearer grant)", bool(TOKEN))

    before = guarded(snapshot)
    second_run_rc = guarded(assert_idempotent, before) if before else None
    ids = guarded(user_ids) or {}
    templates = guarded(idp_templates) or {}
    guarded(assert_groups_claim, ids, jwks)
    guarded(assert_linking, templates)
    guarded(assert_unique_emails, ids, second_run_rc)
    guarded(assert_self_registration)
    guarded(assert_login_service)

    print(f"\nKPI checks_passed={PASSED}")
    print(f"RESULT: {PASSED} passed, {FAILED} failed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
