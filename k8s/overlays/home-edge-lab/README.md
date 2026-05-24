# `home-edge-lab`

Single-Pi + NAS home lab — Home Assistant, IoT, cameras, OpenClaw-compatible agent. **Tier Advanced** ([convention](../../../docs/overlays/CONVENTION.md)).

Full design in [`docs/overlays/home-edge-lab.md`](../../../docs/overlays/home-edge-lab.md).

## Bootstrap

If running ON the Pi:

```bash
./01_init_cluster.sh                 # PI_HOST=local (default)
export KUBECONFIG=~/.kube/home-edge-lab.yaml
./02_deploy.sh
```

If running from another box, against the Pi over SSH:

```bash
PI_HOST=192.168.1.50 SSH_USER=pi ./01_init_cluster.sh
export KUBECONFIG=~/.kube/home-edge-lab.yaml
./02_deploy.sh
```

`02_deploy.sh` finishes by running the validation Job and tailing its logs. It exits non-zero if Home Assistant, Mosquitto, or MinIO failed the smoke check.

## Before you run

1. Edit `metallb-pool.yaml` to match your LAN.
2. Drop Google OAuth client + Cloudflare Tunnel secrets in their `.env` files (copy from `.env.example` templates).
3. Once the `agent-openclaw` component is published, uncomment its resource entry in `kustomization.yaml`.

## Tear down

```bash
./destroy.sh   # removes the overlay; k3s on the Pi is left intact
```

To wipe k3s from the Pi: `sh /usr/local/bin/k3s-uninstall.sh`.
