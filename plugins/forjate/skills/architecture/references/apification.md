# Apification: when the use case must expose an API

`settings.api_surface` is `none`, `internal` or `external`. Default is `none` at Crawl for everything, because the verify Job can exec a CLI or call a ClusterIP without any surface the planner has to secure.

| Surface | Means | Needs | Stage |
|---------|-------|-------|-------|
| `none` | no Service outside the namespace; Jobs and the verify Job talk to pods directly | nothing | Crawl default |
| `internal` | a ClusterIP consumed by other namespaces or scheduled Jobs | a NetworkPolicy allowing the caller from Walk; API key between namespaces | Walk when another team's workload calls it |
| `external` | an Ingress or a tunnel route reachable from the internet | `apps/auth/gotrue-auth` + oauth2-proxy for humans, signature or API key for machines, `apps/cloudflare-tunnel` so no port is opened, rate limiting at Traefik | Walk when a SaaS webhook or users outside the cluster call it |

## When to expose an API at all

- **A chat channel pushes.** Telegram / WhatsApp webhooks need `external` from Walk. At Crawl, poll.
- **Another system needs the result on demand.** The ERP wants to ask "what did you extract from invoice 123": `internal` if the ERP runs in the cluster, `external` with an API key otherwise.
- **A human reviews.** The review queue is a UI, which is the UX expert's call; the API behind it is yours and is `internal` until the UI is exposed.
- **Nobody calls it.** Batch and CDC use cases stay at `none` through Run; they are observed through metrics, not called.

## What goes in front

Humans: `apps/auth/gotrue-auth` and the oauth2-proxy middleware from base, as in `docs/service-integration.md`. Machines: a signature check for webhooks (Telegram secret token, Stripe signature), an API key in a header for pull callers, scoped per caller and rotated through the secrets mechanism of the stage. Never the agent's own credentials, and never an unauthenticated route "because it is only a pilot": a pilot with real customer data is the thing the security expert has to sign.

## Record it

`settings.api_surface`, `settings.auth_in_front`, and the component (`apps/auth/gotrue-auth`, `apps/cloudflare-tunnel`) in `choice` for the stage where it appears. The route itself (hostname, path) is the kustomize skill's to write.
