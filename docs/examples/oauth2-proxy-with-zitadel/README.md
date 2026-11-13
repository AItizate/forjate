# oauth2-proxy with Zitadel (tenant integration example)

An example of wiring oauth2-proxy to a Zitadel instance. It is **not** part of the zitadel component: it belongs to the tenant overlay that runs both.

- `oauth2-values-zitadel.yaml`: oauth2-proxy Helm values (provider `oidc`, `oidc-groups-claim: groups`, client credentials from the Secret `zitadel-oidc-oauth2-proxy`). Copy it into your overlay and change the issuer, redirect, cookie and whitelist domains.
- `bootstrap-application.yaml`: the `applications:` entry for the tenant's `bootstrap.yaml`; the bootstrap writes `zitadel-oidc-oauth2-proxy` (keys `client-id`, `client-secret`, `issuer-url`) in the Zitadel namespace for it. Copy that Secret into oauth2-proxy's namespace.
- The `groups` claim needs the `groupsClaim` action shown (commented) in the bootstrap config.

The Traefik middleware chain does not change; only the OIDC provider does (`provider: google` becomes `provider: oidc` plus `oidc-issuer-url`). More: `docs/tenant-onboarding/zitadel-integrations.md`.
