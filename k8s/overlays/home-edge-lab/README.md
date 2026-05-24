# `home-edge-lab`

Reference overlay. See [`docs/overlays/home-edge-lab.md`](../../../docs/overlays/home-edge-lab.md) for the design.

## Hardware assumed

- 1 × Raspberry Pi 5 (4 GB+) running k3s as control plane
- 1 × NAS exposed via NFS or as a Longhorn-capable worker node
- A LAN with a free contiguous IP block for MetalLB

## Before deploying

1. Edit `metallb-pool.yaml` to match your LAN.
2. Provide Google OAuth client credentials and a Cloudflare Tunnel token via `secrets/` (templates in `secrets/*.env.example`).
3. Once the `agent-openclaw` component lands in `components/apps/agents/`, uncomment its resource line in `kustomization.yaml`.

## Build & deploy

```bash
kustomize build k8s/overlays/home-edge-lab | kubectl apply -f -
```
