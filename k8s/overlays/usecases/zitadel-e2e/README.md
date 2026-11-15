# Use case: `zitadel-e2e`

> Zitadel v4 with Login V2, PostgreSQL and the bootstrap Job on k3d, the three hooks
> run as plain Jobs in the documented order, and a verify Job that proves six
> behaviours against the live instance.

The end-to-end proof of `auth/zitadel` (through `bundles/zitadel-stack`). The
component has render, contract and mocked-bootstrap tests (`validate-zitadel.yml`), and it
has run on live clusters, but only a real Zitadel shows defects such as IdP linking being
off by default, an ambiguous admin email or self-registration being on. This use case
brings a real instance up and asserts those behaviours, so the next defect of that kind
fails CI instead of a migration.

CI runs it on every change to anything it composes (the component, the bundle, the
postgres component: found by following the overlay's references) and nightly
(`spec.nightly: true`, see `.github/workflows/usecase-e2e-nightly.yml`;
`workflow_dispatch` with `usecase: zitadel-e2e` runs only this one).

## Run it

```bash
./scripts/ephemeral/ephemeral.sh up zitadel-e2e         # its own k3d cluster
./scripts/ephemeral/ephemeral.sh validate zitadel-e2e   # re-run verify
./scripts/ephemeral/ephemeral.sh down zitadel-e2e       # delete the cluster
```

Needs `helm` besides the runner's usual tools (the component renders a chart) and egress
to `charts.zitadel.com`, `ghcr.io`, `docker.io` and PyPI (the bootstrap Job installs its
pinned dependencies at run time). Every secret is a placeholder under `secrets/`.

## What it runs

| Phase | Job | What it does |
|-------|-----|--------------|
| seed | `zitadel-e2e-seed` | The documented order for a delivery without Argo CD: waits for PostgreSQL, generates the Login V2 keypair, runs `zitadel-init`, then `zitadel-setup`, scales the Deployments up, then runs `zitadel-bootstrap` with the tenant's `bootstrap.yaml` |
| verify | `zitadel-e2e-verify` | The six assertions below. Every check runs; the summary decides |

There is no `run` phase: the second bootstrap run (assertion 2) needs the state before
and after, so the verify Job does it.

## What verify proves

Each assertion fails the Job when its behaviour regresses (the PR that added the use case
records the break-one-at-a-time evidence).

1. **Discovery and JWKS answer 200 through the issuer URL.** `/.well-known/openid-configuration`
   and the `jwks_uri` it advertises, both under the issuer URL, which names the Service on
   port 80 (the issuer is plain http: no TLS in k3d).
2. **The bootstrap is idempotent.** A second run exits 0, prints no `created` line and no
   `REGENERATED`, reads the login policy and the `loginV2` feature without writing them
   (`unchanged`); org, project, apps, users and IdP template keep their ids, the login
   policy's `changeDate` does not move and the `zitadel-oidc-<app>` Secrets keep their
   `resourceVersion` and data.
3. **The `groups` claim reaches the id_token.** The seeded user signs in with the password
   from `zitadel-bootstrap-env` through the session API, completes the auth request of the
   `portal` app, exchanges the code, and the id_token (signature checked against the JWKS)
   carries `groups == ["admin"]`, the role of its grant on the project, from the
   `groupsClaim` action of `bootstrap.yaml`.
4. **Linking settings.** An IdP with `auto_linking: email` ends with `isLinkingAllowed=true`,
   `isCreationAllowed=false` and `autoLinking=EMAIL` in the instance IdP templates; the same
   entry with `is_linking_allowed: false` exits 2 and leaves the template alone.
5. **The FirstInstance admin's email is unique.** A run where a bootstrap user has the
   admin's email, with an IdP that links by email, exits 1 and says `belongs to 2 users`;
   the run with distinct emails exits 0. The duplicate user is deleted afterwards.
6. **Self-registration is off by default.** `allowRegister=false` after the first run
   (Zitadel ships `true`); `true` after a run with `login_policy.allow_register: true`;
   `false` again on the next run of the tenant's file.

It also checks that the Login V2 service answers its health endpoint.

Out of scope: a real Google or GitHub login (the IdP is created from placeholder
credentials and read back), Argo CD SSO, Longhorn.

## How the admin API and the login are reached

- **Admin token.** The verify Job mounts Secret `zitadel-admin-sa` (the `IAM_OWNER` key the
  chart's setup Job writes, the one the bootstrap uses) and does the JWT-bearer grant. The
  image (`alpine/k8s`) has Python but neither PyJWT nor an openssl binary, so the RS256
  signature is computed with plain integer arithmetic.
- **A login without a browser.** `GET /oauth/v2/authorize` redirects to Login V2 with an
  auth request id; the Job creates a session (user id + password check) through the
  session API, completes the auth request with it and exchanges the code. It is what the
  Login V2 pages do, minus the pages, so the Actions v1 `groups` claim is proved on the
  Login V2 path.

## How it is put together

- **The hooks are templates.** `init`, `setup` and `bootstrap` ship suspended and the
  Deployments at 0 replicas (`replicas:` in the kustomization). `scripts/run-hook.sh` takes
  a hook Job as a template and runs a copy (one attempt, so the exit code is
  `bootstrap.py`'s), which is what Argo CD's `BeforeHookCreation` does. A second `up`
  replays the whole sequence on the live instance.
- **Variants without duplicated files.** The verify Job derives each variant of the
  bootstrap config (`is_linking_allowed: false`, a user with the admin's email,
  `allow_register: true`) from the live tenant ConfigMap, so the file in this directory is
  the only desired state.
- **No key in git.** The Login V2 keypair is generated by the seed Job (openssl from the
  PostgreSQL image) into Secret `zitadel-login-service-key`.
- **Plain http.** `ExternalSecure: false`, `ExternalPort: 80`, a second port 80 on Service
  `zitadel`, and the `AUDIENCE` line of the login service's `.env` changed from `https` to
  `http`. These are the only changes to the component's output besides the hostname.
- **The bootstrap Job's image stays the component's.** Nothing in this overlay rewrites it,
  so an `images:` override in the overlay (or the component's own pin) applies to the
  copies too.

## Isolation

`dedicated`, TTL `2h`. Nothing here is cluster-scoped, but Zitadel, its login service and
PostgreSQL are the heaviest stack of any use case, and the health signals (no restart after
verify) must not be disturbed by a neighbour.
