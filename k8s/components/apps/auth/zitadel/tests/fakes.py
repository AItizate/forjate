"""In-memory stand-ins for the Zitadel API and the Kubernetes Secrets API.

They implement just the endpoints bootstrap.py calls, with the behaviour that
matters for convergence: create answers 409 when the thing exists, update answers
400 "No changes" when nothing differs, a client secret is only shown on creation.
`fail` makes any request whose "METHOD path" matches a regex answer with an error.
"""
import base64
import itertools
import json
import re


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = json.dumps(self._body)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


NOCHANGE = (400, {"message": "No changes (COMMAND-1)"})


class Zitadel:
    """State plus a router. `calls` records (method, path, body, orgid)."""

    def __init__(self):
        self.ids = itertools.count(1)
        self.orgs, self.projects, self.roles, self.apps = {}, {}, {}, {}
        self.actions, self.users, self.grants, self.idps = {}, {}, {}, {}
        self.login_idps, self.flows = set(), {}
        self.features = {}
        # Zitadel's shipped instance login policy: self-registration on.
        self.login_policy = {"allowUsernamePassword": True, "allowExternalIdp": True, "allowRegister": True,
                             "passwordlessType": "PASSWORDLESS_TYPE_ALLOWED", "isDefault": True,
                             "details": {"sequence": "1"}}
        self.calls, self.fail = [], []
        self.ready = True

    def nid(self, prefix):
        return f"{prefix}{next(self.ids)}"

    # --- session interface (what bootstrap.py uses on requests.Session)
    def make_session(self):
        z = self

        class Session:
            headers = {}

            def __init__(self):
                self.headers = {}

            def request(self, method, url, headers=None, json=None, data=None, timeout=None):
                path = re.sub(r"^https?://[^/]+", "", url)
                body = json if json is not None else data
                z.calls.append((method, path, body, (headers or {}).get("x-zitadel-orgid")))
                key = f"{method} {path}"
                for pattern, status in z.fail:
                    if re.search(pattern, key):
                        return Resp(status, {"message": "injected failure"})
                return z.route(method, path, body or {}, (headers or {}).get("x-zitadel-orgid"))

            def get(self, url, **kw):
                return self.request("GET", url, **kw)

            def post(self, url, **kw):
                return self.request("POST", url, **kw)

            def put(self, url, **kw):
                return self.request("PUT", url, **kw)

            def delete(self, url, **kw):
                return self.request("DELETE", url, **kw)

        return Session()

    # --- helpers
    def names(self, body):
        q = (body.get("queries") or [{}])[0]
        for v in q.values():
            if isinstance(v, dict):
                return v.get("name") or v.get("userName")
        return None

    def route(self, method, path, body, org):
        m = re.fullmatch
        if (method, path) == ("GET", "/debug/ready"):
            return Resp(200 if self.ready else 503)
        if (method, path) == ("POST", "/oauth/v2/token"):
            return Resp(200, {"access_token": "tok"})
        if path == "/v2/features/instance":
            if method == "GET":
                return Resp(200, dict(self.features))
            self.features.update(body)
            return Resp(200, {})
        if path == "/admin/v1/policies/login":
            if method == "GET":
                return Resp(200, {"policy": dict(self.login_policy)})
            if {k: v for k, v in self.login_policy.items() if k not in ("details", "isDefault")} == body:
                return Resp(*NOCHANGE)
            self.login_policy = {**body, "isDefault": True, "details": {"sequence": "2"}}
            return Resp(200, {})
        if (method, path) == ("POST", "/v2/organizations/_search"):
            n = self.names(body)
            return Resp(200, {"result": [{"id": i} for i, name in self.orgs.items() if name == n]})
        if (method, path) == ("POST", "/v2/organizations"):
            i = self.nid("org")
            self.orgs[i] = body["name"]
            return Resp(200, {"organizationId": i})
        if (method, path) == ("POST", "/management/v1/projects/_search"):
            n = self.names(body)
            return Resp(200, {"result": [{"id": i} for i, p in self.projects.items() if p["name"] == n]})
        if (method, path) == ("POST", "/management/v1/projects"):
            i = self.nid("prj")
            self.projects[i] = {**body, "org": org}
            return Resp(200, {"id": i})
        if g := m(r"/management/v1/projects/(\w+)", path):
            if method == "PUT":
                p = self.projects[g[1]]
                new = {**p, **body}
                if new == p:
                    return Resp(*NOCHANGE)
                self.projects[g[1]] = new
                return Resp(200)
        if g := m(r"/management/v1/projects/(\w+)/roles", path):
            key = body["roleKey"]
            if (g[1], key) in self.roles:
                return Resp(409, {"message": "ALREADY_EXISTS"})
            self.roles[(g[1], key)] = body
            return Resp(200)
        if g := m(r"/management/v1/projects/(\w+)/roles/(\w+)", path):
            cur = self.roles[(g[1], g[2])]
            new = {**cur, **body}
            if new == cur:
                return Resp(*NOCHANGE)
            self.roles[(g[1], g[2])] = new
            return Resp(200)
        if g := m(r"/management/v1/projects/(\w+)/apps/_search", path):
            n = self.names(body)
            return Resp(200, {"result": [
                {"id": i, "oidcConfig": {"clientId": a["clientId"]}}
                for i, a in self.apps.items() if a["name"] == n and a["project"] == g[1]]})
        if g := m(r"/management/v1/projects/(\w+)/apps/oidc", path):
            i = self.nid("app")
            cid = f"cid-{i}"
            public = body["authMethodType"] in ("OIDC_AUTH_METHOD_TYPE_NONE", "OIDC_AUTH_METHOD_TYPE_PRIVATE_KEY_JWT")
            self.apps[i] = {**body, "project": g[1], "clientId": cid, "secret": None if public else f"secret-{i}"}
            out = {"appId": i, "clientId": cid}
            if not public:
                out["clientSecret"] = self.apps[i]["secret"]
            return Resp(200, out)
        if g := m(r"/management/v1/projects/(\w+)/apps/(\w+)/oidc_config", path):
            a = self.apps[g[2]]
            new = {**a, **body}
            if new == a:
                return Resp(*NOCHANGE)
            self.apps[g[2]] = new
            return Resp(200)
        if g := m(r"/management/v1/projects/(\w+)/apps/(\w+)/oidc_config/_generate_client_secret", path):
            a = self.apps[g[2]]
            if a["secret"] is None:
                # what Zitadel answers for apps that authenticate without a secret
                return Resp(400, {"message": "app is not a confidential client"})
            a["secret"] = f"regen-{next(self.ids)}"
            return Resp(200, {"clientSecret": a["secret"]})
        if (method, path) == ("POST", "/management/v1/actions/_search"):
            n = self.names(body)
            return Resp(200, {"result": [{"id": i} for i, a in self.actions.items() if a["name"] == n]})
        if (method, path) == ("POST", "/management/v1/actions"):
            i = self.nid("act")
            self.actions[i] = body
            return Resp(200, {"id": i})
        if g := m(r"/management/v1/actions/(\w+)", path):
            if self.actions[g[1]] == body:
                return Resp(*NOCHANGE)
            self.actions[g[1]] = body
            return Resp(200)
        if g := m(r"/management/v1/flows/(\d+)/trigger/(\d+)", path):
            self.flows[(g[1], g[2])] = body["actionIds"]
            return Resp(200)
        if (method, path) == ("POST", "/v2/users"):
            if any("typeQuery" in q for q in body["queries"]):
                return Resp(200, {"result": [
                    {"userId": i, "username": u["username"], "human": {"email": {"email": u.get("email", "")}}}
                    for i, u in self.users.items() if u["kind"] == "human"]})
            n = self.names(body)
            org_q = [q["organizationIdQuery"]["organizationId"] for q in body["queries"] if "organizationIdQuery" in q]
            return Resp(200, {"result": [
                {"userId": i} for i, u in self.users.items()
                if u["username"] == n and (not org_q or u.get("org") == org_q[0])]})
        if (method, path) == ("POST", "/v2/users/human"):
            i = self.nid("usr")
            self.users[i] = {"username": body["username"], "org": (body.get("organization") or {}).get("orgId"),
                             "password": (body.get("password") or {}).get("password"), "kind": "human",
                             "email": (body.get("email") or {}).get("email", "")}
            return Resp(200, {"userId": i})
        if (method, path) == ("POST", "/management/v1/users/machine"):
            i = self.nid("usr")
            self.users[i] = {"username": body["userName"], "org": org, "kind": "machine"}
            return Resp(200, {"userId": i})
        if (method, path) == ("POST", "/management/v1/users/grants/_search"):
            uid = body["queries"][0]["userIdQuery"]["userId"]
            pid = body["queries"][1]["projectIdQuery"]["projectId"]
            return Resp(200, {"result": [{"id": i, "roleKeys": g["roleKeys"]}
                                         for i, g in self.grants.items() if g["user"] == uid and g["project"] == pid]})
        if g := m(r"/management/v1/users/(\w+)/grants", path):
            i = self.nid("grt")
            self.grants[i] = {"user": g[1], "project": body["projectId"], "roleKeys": body["roleKeys"]}
            return Resp(200, {"userGrantId": i})
        if g := m(r"/management/v1/users/(\w+)/grants/(\w+)", path):
            self.grants[g[2]]["roleKeys"] = body["roleKeys"]
            return Resp(200)
        if (method, path) == ("POST", "/admin/v1/idps/templates/_search"):
            n = self.names(body)
            return Resp(200, {"result": [{"id": i} for i, d in self.idps.items() if d["name"] == n]})
        if g := m(r"/admin/v1/idps/(\w+)", path):
            if method == "POST":
                i = self.nid("idp")
                self.idps[i] = {**body, "type": g[1]}
                return Resp(200, {"id": i})
        if g := m(r"/admin/v1/idps/(\w+)/(\w+)", path):
            new = {**self.idps[g[2]], **body}
            if new == self.idps[g[2]]:
                return Resp(*NOCHANGE)
            self.idps[g[2]] = new
            return Resp(200)
        if (method, path) == ("POST", "/admin/v1/policies/login/idps/_search"):
            return Resp(200, {"result": [{"idpId": i} for i in self.login_idps]})
        if (method, path) == ("POST", "/admin/v1/policies/login/idps"):
            self.login_idps.add(body["idpId"])
            return Resp(200)
        if g := m(r"/admin/v1/policies/login/idps/(\w+)", path):
            self.login_idps.discard(g[1])
            return Resp(200)
        raise AssertionError(f"the fake Zitadel has no route for {method} {path}")


class Kubernetes:
    """Secrets API of one namespace. `secrets` maps name -> {key: plain text}."""

    def __init__(self):
        self.secrets, self.calls, self.fail = {}, [], False

    def request(self, method, url, headers=None, json=None, data=None, verify=None, timeout=None):
        from_json = json
        path = re.sub(r"^https?://[^/]+", "", url)
        self.calls.append((method, path))
        if self.fail:
            return Resp(403, {"message": "forbidden"})
        g = re.fullmatch(r"/api/v1/namespaces/([\w-]+)/secrets(?:/([\w-]+))?", path)
        assert g, f"unexpected K8s path {path}"
        name = g[2]
        if method == "GET":
            if name not in self.secrets:
                return Resp(404, {"reason": "NotFound"})
            return Resp(200, {"data": {k: base64.b64encode(v.encode()).decode() for k, v in self.secrets[name].items()}})
        if method == "POST":
            n = from_json["metadata"]["name"]
            if n in self.secrets:
                return Resp(409)
            self.secrets[n] = dict(from_json["stringData"])
            return Resp(201)
        if method == "PATCH":
            self.secrets[name].update(__import__("json").loads(data)["stringData"])
            return Resp(200)
        raise AssertionError(f"verb {method} is not granted by the namespaced Role: {path}")
