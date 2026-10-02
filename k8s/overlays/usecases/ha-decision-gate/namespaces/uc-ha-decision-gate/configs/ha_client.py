"""Minimal Home Assistant REST client — standard library only.

Shared by the seed, run and verify Jobs. Nothing here is installed at runtime:
the image is plain python:slim and this file arrives as a ConfigMap, which keeps
the Jobs reproducible and the pod filesystem read-only.

Authentication deliberately re-runs the login flow in every Job instead of
passing a token between them. HA's onboarding can only happen once, but
username/password login can happen any number of times, so each Job mints its
own short-lived access token from the credentials in hass-secret. That removes
the shared PVC and the token hand-off that would otherwise have to be the first
thing to go wrong.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("HA_BASE_URL", "http://hass:8123")
# HA requires client_id to be a URL on the same host as redirect_uri.
CLIENT_ID = f"{BASE}/"


class HAError(RuntimeError):
    pass


def _request(method, path, body=None, token=None, form=False, timeout=30):
    url = f"{BASE}{path}"
    headers = {}
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise HAError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HAError(f"{method} {path} -> {exc.reason}") from exc
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def wait_until_up(attempts=120, delay=5):
    """Block until HA is serving.

    First boot installs requirements and builds the entity registry, so this is
    minutes, not seconds.

    The probe has to work before any user exists, which rules out /api/ — that
    endpoint answers 401 until a token is presented, so polling it waits forever
    on an instance that is actually healthy. /manifest.json is served
    unauthenticated both before and after onboarding.
    """
    last = None
    for _ in range(attempts):
        try:
            _request("GET", "/manifest.json", timeout=10)
            return
        except HAError as exc:
            last = exc
            time.sleep(delay)
    raise HAError(f"Home Assistant never came up: {last}")


def _token_from_auth_code(code):
    payload = _request(
        "POST",
        "/auth/token",
        body={"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID},
        form=True,
    )
    token = (payload or {}).get("access_token")
    if not token:
        raise HAError(f"no access_token in /auth/token response: {payload}")
    return token


def onboarding_pending():
    """True when the owner account has not been created yet.

    HA reports onboarding as a list of steps; the `user` step is the one that
    matters, because it is what mints the first credentials.
    """
    steps = _request("GET", "/api/onboarding") or []
    for step in steps:
        if step.get("step") == "user":
            return not step.get("done", False)
    # An HA that no longer reports the step has already been onboarded.
    return False


def onboard(username, password, name="Forjate", language="en"):
    """Create the owner account. Returns an access token.

    Only valid once per HA instance — callers check onboarding_pending() first.
    """
    payload = _request(
        "POST",
        "/api/onboarding/users",
        body={
            "client_id": CLIENT_ID,
            "name": name,
            "username": username,
            "password": password,
            "language": language,
        },
    )
    code = (payload or {}).get("auth_code")
    if not code:
        raise HAError(f"no auth_code in onboarding response: {payload}")
    token = _token_from_auth_code(code)

    # The remaining steps only set location and analytics preferences. They are
    # not needed for the states API, so a failure here must not fail the seed.
    for path, body in (
        ("/api/onboarding/core_config", {}),
        ("/api/onboarding/analytics", {"base": False, "diagnostics": False}),
    ):
        try:
            _request("POST", path, body=body, token=token)
        except HAError:
            pass
    return token


def login(username, password):
    """Exchange username/password for a short-lived access token."""
    flow = _request(
        "POST",
        "/auth/login_flow",
        body={
            "client_id": CLIENT_ID,
            "handler": ["homeassistant", None],
            "redirect_uri": CLIENT_ID,
            "type": "authorize",
        },
    )
    flow_id = (flow or {}).get("flow_id")
    if not flow_id:
        raise HAError(f"no flow_id in /auth/login_flow response: {flow}")

    step = _request(
        "POST",
        f"/auth/login_flow/{flow_id}",
        body={"client_id": CLIENT_ID, "username": username, "password": password},
    )
    if (step or {}).get("type") != "create_entry" or not (step or {}).get("result"):
        raise HAError(f"login was rejected: {step}")
    return _token_from_auth_code(step["result"])


def authenticate():
    """Onboard if this is a fresh instance, otherwise log in."""
    username = os.environ["HA_USERNAME"]
    password = os.environ["HA_PASSWORD"]
    if onboarding_pending():
        return onboard(username, password)
    return login(username, password)


def set_state(token, entity_id, state, attributes=None):
    return _request(
        "POST",
        f"/api/states/{entity_id}",
        body={"state": str(state), "attributes": attributes or {}},
        token=token,
    )


def get_state(token, entity_id):
    return _request("GET", f"/api/states/{entity_id}", token=token)


def get_states(token):
    return _request("GET", "/api/states", token=token) or []
