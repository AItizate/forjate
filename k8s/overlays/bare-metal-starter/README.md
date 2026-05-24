# `bare-metal-starter`

Reference overlay. See [`docs/overlays/bare-metal-starter.md`](../../../docs/overlays/bare-metal-starter.md) for the design.

## Before deploying

1. Edit `metallb-pool.yaml` — replace `192.168.1.240-192.168.1.250` with a free range on your LAN.
2. Provide a Cloudflare Tunnel token if you enable the secret generator block in `kustomization.yaml`.
3. Confirm your DNS provider is reachable from the cluster before pointing Traefik / cert-manager at Let's Encrypt prod.

## Build

```bash
kustomize build k8s/overlays/bare-metal-starter | less
```

## Deploy

```bash
kustomize build k8s/overlays/bare-metal-starter | kubectl apply -f -
```
