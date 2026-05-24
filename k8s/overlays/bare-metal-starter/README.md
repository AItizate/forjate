# `bare-metal-starter`

First serious on-prem cluster — k3s HA + Longhorn + MetalLB + Cloudflare Tunnel + GitOps via ArgoCD. **Tier Advanced** ([convention](../../../docs/overlays/CONVENTION.md)).

Full design in [`docs/overlays/bare-metal-starter.md`](../../../docs/overlays/bare-metal-starter.md).

## Bootstrap

```bash
# Edit NODES at the top of 01_init_cluster.sh, then:
./01_init_cluster.sh   # k3sup install on each node (embedded etcd HA)
export KUBECONFIG=~/.kube/bare-metal-starter.yaml
./02_deploy.sh         # apply overlay + run validation Job
```

`02_deploy.sh` exits non-zero if the post-deploy health check fails. Read its tail for the line-by-line result.

## Before you run

1. Edit `metallb-pool.yaml` — replace `192.168.1.240-192.168.1.250` with a free contiguous range on your LAN (outside the DHCP scope).
2. If using Cloudflare Tunnel, drop your tunnel token in `secrets/cloudflare.env` (copy from `cloudflare.env.example` once you create one).
3. Confirm DNS reaches Let's Encrypt from the cluster before pointing cert-manager at it.

## Tear down

```bash
./destroy.sh   # removes the overlay's resources; leaves k3s installed on the nodes
```

To wipe k3s itself from each node: `ssh root@<NODE> 'sh /usr/local/bin/k3s-uninstall.sh'`.
