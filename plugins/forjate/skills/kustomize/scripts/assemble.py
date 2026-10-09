#!/usr/bin/env python3
"""Assemble a use case's overlay from its decision records, gates.yaml and scaffold.yaml.

    assemble.py <usecase-dir> [--target overlay|tenant] [--tenant-repo DIR] [--tenant NAME]
                              [--factory-ref TAG] [--org ORG] [--force]

overlay (default): writes under <usecase-dir>/ the Crawl root (kustomization.yaml, namespaces/uc-<name>/
  with the components the records chose, the scaffold's Jobs and Deployments, secretGenerators with their
  .env.example recipes, laptop sizing patches), usecase.yaml (contract + spec.build), stages/walk/ and
  stages/run/ (overlays on the overlay: the stage's components, PSA labels, default-deny NetworkPolicies
  and the egress allow-list from the security record, sealed-secret placeholders replacing every generated
  Secret, the ArgoCD Application and repo-server wiring, images: as the write-back surface), .gitignore
  and a README with the decision summary and the checklist.

tenant: writes the tenant-root shape (docs/use-case-builder/tenant-patterns.md) under <tenant-repo>/k8s/:
  a root kustomization pulling the factory base and components by SSH ref pinned to --factory-ref,
  ./namespaces/uc-<name> with the Walk shape, $patch: delete for every placeholder Secret replaced by a
  SealedSecret, the ArgoCD Application and repo-server SSH wiring, images: as the write-back surface.

The generator is deterministic and writes only what the records state; the kustomize skill reviews the
output, fills what a record left open, and runs build + kubeconform. Existing files are kept unless
--force (the Jobs a human edited survive a re-run).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BUILDER = HERE.parents[2] / "scripts" / "builder"
sys.path.insert(0, str(BUILDER))
from common import load_yaml  # noqa: E402

STAGES = ("crawl", "walk", "run")
# Components that live in their own namespace (cluster-level infrastructure). They go at a stage root,
# never under the use case's namespaced sub-overlay, which would force them into uc-<name>.
INFRA_PREFIXES = ("apps/sealed-secrets", "apps/continuous-delivery/", "apps/storage/", "apps/networking/", "apps/monitoring/",
                  "apps/security/", "apps/docker-registry", "apps/iac/", "apps/cloudflare-tunnel")
# What the assembly knows about catalog components it wires: service, port, protocol, the Secret the
# component mounts (name, keys), the pod label for NetworkPolicies, laptop sizing, glue manifests.
COMPONENTS: dict[str, dict] = {
    "apps/databases/postgres": {"service": "postgres", "port": 5432, "protocol": "postgresql", "label": "postgres",
                                "secret": ("postgres-secret", ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]),
                                "sizing": ("StatefulSet", "postgres", "postgres", "100m", "256Mi", "1", "1Gi")},
    "apps/databases/redis": {"service": "redis", "port": 6379, "protocol": "redis", "label": "redis",
                             "sizing": ("Deployment", "redis", "redis", "50m", "64Mi", "500m", "256Mi")},
    "apps/databases/mongodb": {"service": "mongodb", "port": 27017, "protocol": "mongodb", "label": "mongodb",
                               "secret": ("mongodb-secret", ["MONGO_INITDB_ROOT_USERNAME", "MONGO_INITDB_ROOT_PASSWORD"]),
                               "sizing": ("StatefulSet", "mongodb", "mongodb", "100m", "128Mi", "500m", "512Mi")},
    "apps/minio/dev": {"service": "minio", "port": 9000, "protocol": "s3", "label": "minio",
                       "secret": ("minio-secret", ["MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD"]), "glue": "minio-dev"},
    "apps/minio/single-server": {"service": "minio", "port": 9000, "protocol": "s3", "label": "minio",
                                 "secret": ("minio-storage-configuration", ["config.env"])},
    "apps/document-processing/docling": {"service": "docling", "port": 5001, "protocol": "http", "label": "docling",
                                         "sizing": ("Deployment", "docling", "docling", "250m", "1Gi", "2", "3Gi")},
    "apps/ai-models/ollama": {"service": "ollama-service", "port": 11434, "protocol": "http", "label": "ollama",
                              "sizing": ("StatefulSet", "ollama", "ollama", "250m", "1Gi", "2", "4Gi"), "glue": "ollama"},
    "apps/ai-models/vllm": {"service": "vllm", "port": 8000, "protocol": "http", "label": "vllm"},
    "apps/ai-models/litellm": {"service": "litellm", "port": 4000, "protocol": "http", "label": "litellm",
                               "secret": ("litellm-secret", ["LITELLM_MASTER_KEY"]), "placeholder_secret": "litellm-secret"},
    "apps/ai-models/open-webui": {"service": "open-webui", "port": 8080, "protocol": "http", "label": "open-webui"},
    "apps/brokers/nats": {"service": "nats", "port": 4222, "protocol": "nats", "label": "nats"},
    "apps/brokers/rabbitmq": {"service": "rabbitmq", "port": 5672, "protocol": "amqp", "label": "rabbitmq"},
    "apps/databases/lancedb": {"service": "lancedb", "port": 8000, "protocol": "http", "label": "lancedb"},
    "apps/databases/milvus": {"service": "milvus", "port": 19530, "protocol": "grpc", "label": "milvus"},
    "apps/surveys/formbricks": {"service": "formbricks", "port": 3000, "protocol": "http", "label": "formbricks",
                                "secret": ("formbricks-secret", ["NEXTAUTH_SECRET", "ENCRYPTION_KEY", "CRON_SECRET", "DATABASE_URL"]),
                                "config": ("formbricks-config", ["WEBAPP_URL=http://formbricks:3000", "NEXTAUTH_URL=http://formbricks:3000"]), "ingress": "formbricks-ingress"},
    "apps/auth/gotrue-auth": {"service": "gotrue-auth", "port": 9999, "protocol": "http", "label": "gotrue",
                              "secret": ("gotrue-secret", ["GOTRUE_JWT_SECRET", "GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID", "GOTRUE_EXTERNAL_GOOGLE_SECRET", "DATABASE_URL"]),
                              "placeholder_secret": "gotrue-secret"},
    "apps/cloudflare-tunnel": {"secret": ("cloudflare-tunnel-secret", ["TUNNEL_TOKEN"]), "namespace": "cloudflare-tunnel"},
    "bundles/temporal-stack": {"service": "temporal-frontend", "port": 7233, "protocol": "grpc", "label": "temporal"},
}
CONTRACT_COMPONENT = re.compile(r"^apps/[a-z0-9-]+/[a-z0-9-]+$")
PLACEHOLDER_SHA = "0" * 40
PLACEHOLDER_DIGEST = "sha256:" + "0" * 64


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def dump(doc) -> str:
    return yaml.safe_dump(doc, sort_keys=False, width=120, allow_unicode=True)


class Assembly:
    def __init__(self, uc_dir: Path, *, org: str, factory_ref: str, force: bool):
        self.uc = uc_dir.resolve()
        self.name = self.uc.name
        self.ns = f"uc-{self.name}"
        self.org, self.factory_ref, self.force = org, factory_ref, force
        b = self.uc / ".builder"
        self.brief = load_yaml(b / "brief.yaml")
        self.plan = load_yaml(b / "stage-plan.yaml")
        self.records = {p.stem: load_yaml(p) for p in sorted((b / "decisions").glob("*.yaml"))}
        self.gates = load_yaml(b / "gates.yaml") if (b / "gates.yaml").is_file() else None
        self.scaffold = load_yaml(b / "scaffold.yaml") if (b / "scaffold.yaml").is_file() else None
        self.written: list[Path] = []
        self.notes: list[str] = []
        self.in_scope = [s for s in STAGES if (self.plan["spec"]["stages"].get(s) or {}).get("in_scope")]

    # ------------------------------------------------------------ record access
    def setting(self, area: str, stage: str, key: str, default=None):
        r = self.records.get(area)
        if not r:
            return default
        return ((r["spec"]["stages"].get(stage) or {}).get("settings") or {}).get(key, default)

    def choices(self, stage: str) -> list[str]:
        out: list[str] = []
        for r in self.records.values():
            for c in (r["spec"]["stages"].get(stage) or {}).get("choice") or []:
                if c not in out:
                    out.append(c)
        return out

    def new_at(self, stage: str) -> list[str]:
        """Components a stage adds over the previous stages."""
        before = {c for s in STAGES[:STAGES.index(stage)] for c in self.choices(s)}
        return [c for c in self.choices(stage) if c not in before]

    def infra(self, c: str) -> bool:
        return c.startswith(INFRA_PREFIXES)

    def rel_component(self, c: str, depth: int) -> str:
        return "../" * depth + f"components/{c}"

    def ssh_component(self, c: str) -> str:
        return f"ssh://git@github.com/{self.org}/forjate.git//k8s/components/{c}?ref={self.factory_ref}"

    # ------------------------------------------------------------ writing
    def write(self, path: Path, text: str, *, keep: bool = True) -> None:
        if path.exists() and keep and not self.force:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text.endswith("\n") else text + "\n")
        self.written.append(path)

    # ------------------------------------------------------------ secrets
    def crawl_secrets(self) -> list[tuple[str, list[str], str]]:
        """(secret name, keys, origin) the Crawl overlay generates: component Secrets and scaffold secrets."""
        out: list[tuple[str, list[str], str]] = []
        for c in self.choices("crawl"):
            meta = COMPONENTS.get(c) or {}
            if meta.get("secret"):
                name, keys = meta["secret"]
                out.append((name, keys, c))
        for w in (self.scaffold or {}).get("spec", {}).get("workloads", []):
            for s in w.get("secrets") or []:
                if s not in [o[0] for o in out]:
                    out.append((s, [s.upper().replace("-", "_")], f"scaffold:{w['name']}"))
        return out

    def stage_secrets(self, stage: str) -> list[tuple[str, list[str], str]]:
        """Secrets that first appear at a later stage: the stage's components and the external integrations."""
        out: list[tuple[str, list[str], str]] = []
        known = {s[0] for s in self.crawl_secrets()}
        for c in self.new_at(stage):
            meta = COMPONENTS.get(c) or {}
            if meta.get("secret") and meta["secret"][0] not in known:
                out.append((meta["secret"][0], meta["secret"][1], c)); known.add(meta["secret"][0])
        for line in self.setting("architecture", stage, "integrations", []) or []:
            system, _, pattern = str(line).partition(":")
            if pattern.strip() in ("stub", "replay", "seed-replay", "batch") or not pattern.strip():
                continue
            sname = f"{slug(system)}-secret"
            if sname not in known:
                out.append((sname, [f"{slug(system).upper().replace('-', '_')}_TOKEN"], f"integration: {line}")); known.add(sname)
        return out

    def env_example(self, name: str, keys: list[str], origin: str, *, stage: str) -> str:
        seal = f"./scripts/convert-to-sealed-secret.sh   (select the overlay; writes secrets/sealed-{name}.yaml)" if stage != "crawl" else "not sealed at Crawl (secretGenerator from this file's gitignored copy); from Walk: ./scripts/convert-to-sealed-secret.sh"
        lines = [f"# {name} -- replace values before sealing ({origin})",
                 "# To generate: openssl rand -hex 32   (one value per key; database credentials as the component documents)",
                 f"# To seal:     {seal}",
                 f"# Secret name: {name}   namespace: {self.ns}   keys: {', '.join(keys)}"]
        for k in keys:
            default = "CHANGE_ME"
            if k == "POSTGRES_DB": default = "appdb"
            if k in ("POSTGRES_USER", "MINIO_ROOT_USER"): default = "app"
            if k in ("POSTGRES_PASSWORD", "MINIO_ROOT_PASSWORD", "APPROVAL_SECRET"): default = "ephemeral-local-only" if stage == "crawl" else "CHANGE_ME"
            if k == "DATABASE_URL": default = f"postgresql://app:CHANGE_ME@postgres:5432/{name.split('-')[0]}"
            if k == "config.env": default = '"export MINIO_ROOT_USER=app\\nexport MINIO_ROOT_PASSWORD=CHANGE_ME"'
            lines.append(f"{k}={default}")
        return "\n".join(lines)

    def sealed_placeholder(self, name: str, keys: list[str]) -> str:
        enc = "\n".join(f"    {k}: {'AgA' + 'x' * 40}  # placeholder: run the seal command from {name}.env.example" for k in keys if k != "config.env")
        return (f"# Placeholder SealedSecret for {name}: encryptedData is not valid until the recipe in {name}.env.example has been run\n"
                f"# against the target cluster's sealed-secrets controller (the env-example-check and secrets-check gates read this file).\n"
                "apiVersion: bitnami.com/v1alpha1\nkind: SealedSecret\nmetadata:\n"
                f"  name: {name}\n  namespace: {self.ns}\nspec:\n  encryptedData:\n{enc}\n  template:\n    metadata:\n      name: {name}\n      namespace: {self.ns}\n    type: Opaque\n")

    # ------------------------------------------------------------ workloads
    def workload_manifest(self, w: dict, *, image: str) -> str:
        env = [{"name": e.split("=", 1)[0], "value": e.split("=", 1)[1]} if "=" in e else {"name": e, "value": ""} for e in w.get("env") or []]
        env_from = [{"secretRef": {"name": s}} for s in w.get("secrets") or []]
        mounts = [{"name": f"writable-{i}", "mountPath": p} for i, p in enumerate(w.get("writable_paths") or [])]
        volumes = [{"name": f"writable-{i}", "emptyDir": {}} for i, _ in enumerate(w.get("writable_paths") or [])]
        container = {
            "name": w["name"], "image": image, "imagePullPolicy": "IfNotPresent", "command": w["command"],
            "env": env, "envFrom": env_from,
            "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "1", "memory": "1Gi"}},
            "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
            "volumeMounts": mounts,
        }
        pod_sc = {"runAsNonRoot": True, "runAsUser": 1000, "seccompProfile": {"type": "RuntimeDefault"}}
        labels = {"app": w["name"], "forjate.io/usecase": self.name}
        if w["kind"] == "job":
            phase = w.get("phase", "run")
            labels["forjate.io/phase"] = phase
            backoff = {"seed": 5, "run": 2, "verify": 0}[phase]
            doc = {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": w["name"], "namespace": self.ns, "labels": labels},
                   "spec": {"suspend": True, "backoffLimit": backoff, "ttlSecondsAfterFinished": 600,
                            "template": {"metadata": {"labels": labels}, "spec": {"restartPolicy": "Never", "securityContext": pod_sc, "containers": [container], "volumes": volumes}}}}
            head = f"# {phase} phase ({w['name']}): suspended, the runner un-suspends it in order (seed -> run -> verify).\n# Command and environment from .builder/scaffold.yaml; the image is built by ephemeral.sh from usecase.yaml spec.build.\n"
            return head + dump(doc)
        port = w.get("port", 8000)
        if w.get("health_path"):
            container["livenessProbe"] = {"httpGet": {"path": w["health_path"], "port": port}, "initialDelaySeconds": 10, "periodSeconds": 15}
            container["readinessProbe"] = {"httpGet": {"path": "/readyz" if w["health_path"] == "/healthz" else w["health_path"], "port": port}, "initialDelaySeconds": 5, "periodSeconds": 5}
        container["ports"] = [{"containerPort": port}]
        dep = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": w["name"], "namespace": self.ns, "labels": labels},
               "spec": {"replicas": 1, "selector": {"matchLabels": {"app": w["name"]}},
                        "template": {"metadata": {"labels": labels}, "spec": {"securityContext": pod_sc, "containers": [container], "volumes": volumes}}}}
        svc = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": w["name"], "namespace": self.ns, "labels": labels},
               "spec": {"selector": {"app": w["name"]}, "ports": [{"port": port, "targetPort": port, "protocol": "TCP"}]}}
        return f"# {w['name']}: a workload the architecture record names, served from the scaffold's image.\n" + dump(dep) + "---\n" + dump(svc)

    # ------------------------------------------------------------ overlay target
    def write_overlay(self) -> None:
        uc, ns = self.uc, self.ns
        nsdir = uc / "namespaces" / ns
        crawl = self.choices("crawl")
        uc_components = [c for c in crawl if not self.infra(c)]
        infra = [c for c in crawl if self.infra(c)]
        sc = (self.scaffold or {}).get("spec", {})
        image = sc.get("image")
        workloads = sc.get("workloads", [])
        # root
        root = {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
                "resources": ["../../../base"] + [self.rel_component(c, 3) for c in infra] + [f"./namespaces/{ns}"],
                "labels": [{"pairs": {"app.kubernetes.io/managed-by": "kustomize", "app.kubernetes.io/overlay": self.name}}]}
        self.write(uc / "kustomization.yaml", f"# Crawl root of {self.name}, assembled from .builder/ by forjate:kustomize. Stages extend it: stages/walk, stages/run.\n" + dump(root))
        # namespace
        psa = self.setting("security", "crawl", "psa_level", "privileged")
        labels = {"forjate.io/usecase": self.name, "pod-security.kubernetes.io/warn": "restricted", "pod-security.kubernetes.io/audit": "restricted"}
        if psa != "privileged":
            labels["pod-security.kubernetes.io/enforce"] = psa
        self.write(nsdir / "namespace.yaml", "# PSA: the security record's Crawl level; warn and audit at restricted so violations are visible before Walk enforces.\n"
                   + dump({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns, "labels": labels}}))
        resources = ["namespace.yaml"] + [self.rel_component(c, 5) for c in uc_components]
        patches: list[dict] = []
        # glue and sizing per component
        for c in uc_components:
            meta = COMPONENTS.get(c) or {}
            if meta.get("sizing"):
                kind, name, cname, rc, rm, lc, lm = meta["sizing"]
                self.write(nsdir / "patches" / f"{name}-resources-patch.yaml", f"# Laptop sizing for {c} (catalog defaults are sized for tenants).\n" + dump(
                    {"apiVersion": "apps/v1", "kind": kind, "metadata": {"name": name}, "spec": {"template": {"spec": {"containers": [
                        {"name": cname, "resources": {"requests": {"cpu": rc, "memory": rm}, "limits": {"cpu": lc, "memory": lm}}}]}}}}))
                patches.append({"path": f"patches/{name}-resources-patch.yaml", "target": {"kind": kind, "name": name}})
            if meta.get("glue") == "minio-dev":
                self.write(nsdir / "minio-service.yaml", "# apps/minio/dev ships a Pod only; the overlay adds the Service the contract advertises.\n" + dump(
                    {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "minio"}, "spec": {"selector": {"app": "minio"}, "ports": [{"name": "api", "port": 9000, "targetPort": 9000}, {"name": "console", "port": 9090, "targetPort": 9090}]}}))
                resources.append("minio-service.yaml")
                self.write(nsdir / "patches" / "minio-env-patch.yaml", "# apps/minio/dev has no credentials; mount the overlay's minio-secret (strategic merge on the container name).\n# The component's hostPath is root-owned on k3d and the image runs as 1001: an emptyDir is the laptop's disk at Crawl.\n" + dump(
                    {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "minio"}, "spec": {"containers": [{"name": "minio", "envFrom": [{"secretRef": {"name": "minio-secret"}}],
                        "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "1", "memory": "1Gi"}}}]}}))
                patches.append({"path": "patches/minio-env-patch.yaml", "target": {"kind": "Pod", "name": "minio"}})
                patches.append({"target": {"kind": "Pod", "name": "minio"},
                                "patch": "# assumes volumes[0] is localvolume (upstream pod.yaml); the hostPath is root-owned on k3d and the image runs as 1001\n- op: replace\n  path: /spec/volumes/0\n  value: {name: localvolume, emptyDir: {}}\n"})
            if meta.get("glue") == "ollama":
                patches.append({"target": {"kind": "StatefulSet", "name": "ollama"},
                                "patch": "# assumes containers[0] is ollama (upstream statefulset.yaml); drops the GPU limit a laptop cannot satisfy\n- op: remove\n  path: /spec/template/spec/containers/0/resources/limits/nvidia.com~1gpu\n"})
        # workloads
        for w in workloads:
            self.write(nsdir / f"{w['name']}.yaml", self.workload_manifest(w, image=image))
            resources.append(f"{w['name']}.yaml")
        # secrets
        secret_gen = []
        for sname, keys, origin in self.crawl_secrets():
            self.write(nsdir / "secrets" / f"{sname}.env.example", self.env_example(sname, keys, origin, stage="crawl"))
            secret_gen.append({"name": sname, "envs": [f"secrets/{sname}.env"], "options": {"disableNameSuffixHash": True}})
        config_gen = []
        for c in uc_components:
            meta = COMPONENTS.get(c) or {}
            if meta.get("config"):
                cname, literals = meta["config"]
                config_gen.append({"name": cname, "literals": literals, "options": {"disableNameSuffixHash": True}})
        sub = {"namespace": ns, "resources": resources}
        if secret_gen:
            sub["secretGenerator"] = secret_gen
        if config_gen:
            sub["configMapGenerator"] = config_gen
        if patches:
            sub["patches"] = patches
        if image:
            sub["images"] = [{"name": image, "newTag": "dev"}]
        head = (f"# {ns}: the use case's namespace at Crawl. Components from the records' choices, the scaffold's workloads,\n"
                "# secretGenerators from gitignored .env files seeded from the committed .env.example (the runner and CI copy them),\n"
                "# the image built by ephemeral.sh from usecase.yaml spec.build and pinned to :dev here (Walk replaces the tag by write-back).\n")
        self.write(nsdir / "kustomization.yaml", head + dump(sub))
        self.write(uc / ".gitignore", "# Real credentials never land in git; the committed examples do.\n**/secrets/*.env\n!**/secrets/*.env.example\napp/.venv*/\n")
        self.write_contract(crawl, workloads, image)
        for stage in ("walk", "run"):
            if stage in self.in_scope:
                self.write_stage(stage)
        self.write_readme()

    def write_contract(self, crawl: list[str], workloads: list[dict], image: str | None) -> None:
        jobs = {}
        for w in workloads:
            if w["kind"] == "job" and w.get("phase"):
                jobs[w["phase"]] = {"name": w["name"], "timeout": {"seed": 600, "run": 900, "verify": 600}[w["phase"]]}
        if "seed" not in jobs or "verify" not in jobs:
            self.notes.append("OPEN: the scaffold declares no seed or verify Job; usecase.yaml needs both before ephemeral.sh can run")
        endpoints, secrets = [], []
        for c in crawl:
            meta = COMPONENTS.get(c) or {}
            if meta.get("service"):
                endpoints.append({"name": c.split("/")[-1], "service": meta["service"], "port": meta["port"], "protocol": meta.get("protocol", "tcp")})
            if meta.get("secret"):
                secrets.append({"name": f"{c.split('/')[-1]}-credentials", "secretRef": meta["secret"][0], "keys": meta["secret"][1]})
        for w in workloads:
            if w["kind"] == "deployment":
                endpoints.append({"name": w["name"], "service": w["name"], "port": w.get("port", 8000), "protocol": "http"})
        dedicated = any(c.startswith(("apps/storage/", "apps/continuous-delivery/", "apps/sealed-secrets", "apps/minio/single-server")) for c in crawl)
        contract = {"apiVersion": "forjate.io/v0", "kind": "UseCase",
                    "metadata": {"name": self.name, "description": str(self.brief["spec"]["problem"]).split(". ")[0][:160]},
                    "spec": {"isolation": "dedicated" if dedicated else "shared", "ttl": "4h",
                             "components": [c for c in crawl if CONTRACT_COMPONENT.match(c)], "jobs": jobs,
                             "outputs": {"endpoints": endpoints, "secrets": secrets}}}
        if image:
            contract["spec"]["build"] = [{"image": image, "context": "app"}]
        head = (f"# Contract for the {self.name} ephemeral use-case environment, assembled from .builder/.\n"
                "# Schema: scripts/ephemeral/usecase.schema.json. Design: docs/ephemeral-use-cases.md\n"
                "# spec.build: Crawl has no registry; ephemeral.sh builds app/ and imports <image>:dev into k3d before applying.\n")
        self.write(self.uc / "usecase.yaml", head + dump(contract))

    # ------------------------------------------------------------ stages
    def netpols(self, stage: str, *, depth_note: str) -> str:
        """default-deny, allow-dns, in-cluster allows derived from the scaffold's workloads and the components, one policy per external host."""
        ns = self.ns
        docs = [
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "default-deny", "namespace": ns}, "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}},
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "allow-dns", "namespace": ns},
             "spec": {"podSelector": {}, "policyTypes": ["Egress"], "egress": [{"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}}], "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}},
        ]
        comps = [c for c in self.choices(stage) if not self.infra(c) and (COMPONENTS.get(c) or {}).get("label")]
        workloads = (self.scaffold or {}).get("spec", {}).get("workloads", [])
        targets = [(COMPONENTS[c]["label"], COMPONENTS[c]["port"]) for c in comps] + [(w["name"], w.get("port", 8000)) for w in workloads if w["kind"] == "deployment"]
        for w in workloads:
            to = [{"to": [{"podSelector": {"matchLabels": {"app": lbl}}}], "ports": [{"protocol": "TCP", "port": port}]} for lbl, port in targets if lbl != w["name"]]
            docs.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": f"allow-{w['name']}-egress", "namespace": ns},
                         "spec": {"podSelector": {"matchLabels": {"app": w["name"]}}, "policyTypes": ["Egress"], "egress": to}})
        for lbl, port in targets:
            docs.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": f"allow-ingress-to-{lbl}", "namespace": ns},
                         "spec": {"podSelector": {"matchLabels": {"app": lbl}}, "policyTypes": ["Ingress"],
                                  "ingress": [{"from": [{"podSelector": {}}], "ports": [{"protocol": "TCP", "port": port}]}]}})
        surface = self.setting("ux", stage, "surface_workload") or None
        if surface and surface != "none":
            docs.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": f"allow-ingress-controller-to-{surface}", "namespace": ns},
                         "spec": {"podSelector": {"matchLabels": {"app": surface}}, "policyTypes": ["Ingress"],
                                  "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "traefik"}}}]}]}})
        external = []
        for line in self.setting("security", stage, "egress_allowlist", []) or []:
            dest = str(line).split("#")[0].strip()
            if not dest:
                continue
            host, _, port = dest.partition(":")
            port = int(port) if port.strip().isdigit() else 443
            external.append((host.strip(), port))
            docs.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
                         "metadata": {"name": f"allow-egress-{slug(host)[:40]}", "namespace": ns,
                                      "annotations": {"forjate.io/egress-host": f"{host}:{port}", "forjate.io/note": "NetworkPolicy has no FQDN selector: replace the cidr with the resolved address range of this host, or use the CNI's FQDN policy (CiliumNetworkPolicy toFQDNs)"}},
                         "spec": {"podSelector": {}, "policyTypes": ["Egress"], "egress": [{"to": [{"ipBlock": {"cidr": "203.0.113.0/32"}}], "ports": [{"protocol": "TCP", "port": port}]}]}})
        head = (f"# NetworkPolicies for {ns} at {stage}, generated from decisions/security.yaml (network_policy: default-deny,\n"
                f"# egress_allowlist: {len(external)} external host(s)) and the in-cluster allows derived from the scaffold's workloads and the components.{depth_note}\n")
        return head + "---\n".join(dump(d) for d in docs)

    def argocd_files(self, stage: str, path: str, repo_url: str, dirn: Path, depth: int, *, wiring: bool = True) -> list[str]:
        """Application + repo-server SSH wiring when the devops record lists private-ref prerequisites."""
        out = []
        sync = self.setting("devops", stage, "argocd_sync", "auto-selfheal")
        prune = sync == "auto-prune-selfheal"
        app = {"apiVersion": "argoproj.io/v1alpha1", "kind": "Application", "metadata": {"name": f"{self.ns}-{stage}", "namespace": "argocd"},
               "spec": {"project": "default", "source": {"repoURL": repo_url, "targetRevision": self.factory_ref, "path": path},
                        "destination": {"server": "https://kubernetes.default.svc", "namespace": self.ns},
                        "syncPolicy": {"automated": {"selfHeal": True, "prune": prune}, "syncOptions": ["ServerSideApply=true", "CreateNamespace=false"]}}}
        self.write(dirn / "argocd" / "application.yaml", f"# ArgoCD Application for {stage}: tracks a tag (devops: target_revision tag, {sync}); CreateNamespace=false keeps the PSA labels of namespace.yaml.\n# targetRevision is the tag that carries this overlay; bump it on release (the write-back never edits it).\n" + dump(app))
        out.append("argocd/application.yaml")
        if wiring and self.setting("devops", stage, "argocd_private_refs"):
            self.write(dirn / "argocd" / "repo-server-ssh-patch.yaml", "# devops argocd_private_refs: the repo-server clones ssh:// refs with the deploy key in argocd-ssh-keys (strategic merge on the container name).\n" + dump(
                {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "argocd-repo-server", "namespace": "argocd"},
                 "spec": {"template": {"spec": {"containers": [{"name": "argocd-repo-server", "env": [{"name": "GIT_SSH_COMMAND", "value": "ssh -F /app/ssh-keys/ssh_config"}, {"name": "ARGOCD_EXEC_TIMEOUT", "value": "600s"}],
                                                                  "volumeMounts": [{"name": "argocd-ssh-keys", "mountPath": "/app/ssh-keys", "readOnly": True}]}],
                                                  "volumes": [{"name": "argocd-ssh-keys", "secret": {"secretName": "argocd-ssh-keys", "defaultMode": 256}}]}}}}))
            self.write(dirn / "argocd" / "cmd-params-cm-patch.yaml", "# Helm-rendered components and seven SSH clones per refresh need these (devops record, tenant-patterns.md).\n" + dump(
                {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "argocd-cmd-params-cm", "namespace": "argocd"},
                 "data": {"reposerver.enable.kustomize.helm": "true", "timeout.reconciliation": "600s"}}))
            for sname, keys in (("argocd-ssh-keys", ["ssh_config", "id_ed25519"]), ("argocd-repo-creds", ["type", "url", "sshPrivateKey"])):
                self.write(dirn / "argocd" / "secrets" / f"sealed-{sname}.yaml", self.sealed_placeholder(sname, keys).replace(f"namespace: {self.ns}", "namespace: argocd"))
                self.write(dirn / "argocd" / "secrets" / f"{sname}.env.example", self.env_example(sname, keys, "ArgoCD repo-server SSH wiring (namespace argocd)", stage=stage).replace(f"namespace: {self.ns}", "namespace: argocd"))
                out.append(f"argocd/secrets/sealed-{sname}.yaml")
        return out

    def write_stage(self, stage: str) -> None:
        uc, ns = self.uc, self.ns
        sdir = uc / "stages" / stage
        # kustomize refuses a resource that is an ancestor of the current root ("cycle detected"), so a stage
        # overlay recomposes the Crawl root from its parts (base, the Crawl infra, the Crawl namespace child)
        # instead of referencing ../.. ; Run extends ../walk, a sibling.
        crawl_infra = [c for c in self.choices("crawl") if self.infra(c)]
        prev = ["../../../../../base"] + [self.rel_component(c, 5) for c in crawl_infra] + [f"../../namespaces/{ns}"] if stage == "walk" else ["../walk"]
        new = self.new_at(stage)
        infra = [c for c in new if self.infra(c)]
        scoped = [c for c in new if not self.infra(c)]
        sc = (self.scaffold or {}).get("spec", {})
        image = sc.get("image")
        resources = prev + [self.rel_component(c, 5) for c in infra] + [f"./namespaces/{ns}"]
        patches: list[dict] = []
        # PSA on the namespace
        psa = self.setting("security", stage, "psa_level", "baseline")
        self.write(sdir / "patches" / "namespace-psa-patch.yaml", f"# PSA at {stage} from decisions/security.yaml (psa_level: {psa}); restricted stays on warn and audit.\n" + dump(
            {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns, "labels": {"pod-security.kubernetes.io/enforce": psa, "pod-security.kubernetes.io/warn": "restricted", "pod-security.kubernetes.io/audit": "restricted"}}}))
        patches.append({"path": "patches/namespace-psa-patch.yaml", "target": {"kind": "Namespace", "name": ns}})
        # the model runs live from Walk; the external systems are the real ones
        if stage == "walk" and sc.get("workloads"):
            env = [{"name": "MODEL_MODE", "value": "live"}]
            for line in self.setting("security", stage, "egress_allowlist", []) or []:
                host = str(line).split("#")[0].strip().partition(":")[0]
                if "odoo" in host or "erp" in host:
                    env.append({"name": "ERP_URL", "value": f"https://{host}"})
                if "orders" in host:
                    env.append({"name": "ORDERS_URL", "value": f"https://{host}"})
            for w in sc["workloads"]:
                kind = "Job" if w["kind"] == "job" else "Deployment"
                self.write(sdir / "patches" / f"{w['name']}-env-patch.yaml", f"# {stage}: the real model and the real systems (strategic merge on the container name, order-independent).\n" + dump(
                    {"apiVersion": "batch/v1" if kind == "Job" else "apps/v1", "kind": kind, "metadata": {"name": w["name"]}, "spec": {"template": {"spec": {"containers": [{"name": w["name"], "env": env}]}}}}))
                patches.append({"path": f"patches/{w['name']}-env-patch.yaml", "target": {"kind": kind, "name": w["name"], "namespace": ns}})
        # secrets: the mechanism per stage
        mech = self.setting("security", stage, "secrets_mechanism", "sealed-secrets")
        # Walk writes the NetworkPolicies and the surface; Run inherits them from ../walk and adds only what changes.
        sub_resources = (["netpols.yaml"] if stage == "walk" else []) + [self.rel_component(c, 7) for c in scoped]
        all_secrets = self.crawl_secrets() + self.stage_secrets("walk") + (self.stage_secrets("run") if stage == "run" else [])
        if stage == "walk":
            for sname, keys, origin in self.crawl_secrets():
                patches.append({"target": {"kind": "Secret", "name": sname, "namespace": ns}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {sname}\n"})
            for c in scoped:
                ph = (COMPONENTS.get(c) or {}).get("placeholder_secret")
                if ph:
                    patches.append({"target": {"kind": "Secret", "name": ph, "namespace": ns}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {ph}\n"})
            for sname, keys, origin in all_secrets:
                self.write(sdir / "namespaces" / ns / "secrets" / f"sealed-{sname}.yaml", self.sealed_placeholder(sname, keys))
                self.write(sdir / "namespaces" / ns / "secrets" / f"{sname}.env.example", self.env_example(sname, keys, origin, stage=stage))
                sub_resources.append(f"secrets/sealed-{sname}.yaml")
        if stage == "run" and mech in ("external-secrets", "vault"):
            for sname, keys, origin in all_secrets:
                patches.append({"target": {"kind": "SealedSecret", "name": sname, "namespace": ns}, "patch": f"$patch: delete\napiVersion: bitnami.com/v1alpha1\nkind: SealedSecret\nmetadata:\n  name: {sname}\n"})
                es = {"apiVersion": "external-secrets.io/v1beta1", "kind": "ExternalSecret", "metadata": {"name": sname, "namespace": ns},
                      "spec": {"refreshInterval": "1h", "secretStoreRef": {"name": "corporate-store", "kind": "ClusterSecretStore"},
                               "target": {"name": sname, "creationPolicy": "Owner"},
                               "data": [{"secretKey": k, "remoteRef": {"key": f"{self.name}/{sname}", "property": k}} for k in keys if k != "config.env"]}}
                self.write(sdir / "namespaces" / ns / "externalsecrets" / f"{sname}.yaml", f"# Run: {sname} pulled from the central store (security: secrets_mechanism {mech}); the SealedSecret of the same name is deleted above.\n# ClusterSecretStore corporate-store is the organisation's (devops Q: which store, inside the residency).\n" + dump(es))
                sub_resources.append(f"externalsecrets/{sname}.yaml")
        # ingress for the human surface
        auth = self.setting("security", stage, "auth_in_front") or self.setting("architecture", stage, "auth_in_front")
        surface = self.setting("ux", stage, "surface_workload")
        if stage == "walk" and auth == "oauth2-proxy" and surface and surface != "none":
            port = next((w.get("port", 8000) for w in sc.get("workloads", []) if w["name"] == surface), 8000)
            ing = {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": surface, "namespace": ns,
                   "annotations": {"traefik.ingress.kubernetes.io/router.middlewares": f"{ns}-gotrue-chain@kubernetescrd", "cert-manager.io/cluster-issuer": "letsencrypt-prod"}},
                   "spec": {"ingressClassName": "traefik", "rules": [{"host": f"{self.name}.example.com", "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {"service": {"name": surface, "port": {"number": port}}}}]}}],
                            "tls": [{"hosts": [f"{self.name}.example.com"], "secretName": f"{surface}-tls"}]}}
            self.write(sdir / "namespaces" / ns / f"{surface}-ingress.yaml", f"# The human surface (ux: {surface}) behind oauth2-proxy and GoTrue (security/architecture: auth_in_front). Patch the host.\n" + dump(ing))
            sub_resources.append(f"{surface}-ingress.yaml")
            if surface not in [w["name"] for w in sc.get("workloads", [])]:
                self.notes.append(f"OPEN: the {stage} surface workload {surface} is not in scaffold.yaml yet; the Ingress is written for the shape, the workload arrives with the {stage} scaffold")
        # component Ingresses in the namespace sit behind the auth middleware (security: auth_in_front)
        if stage == "walk" and auth == "oauth2-proxy":
            for c in scoped:
                ing_name = (COMPONENTS.get(c) or {}).get("ingress")
                if ing_name:
                    patches.append({"target": {"kind": "Ingress", "name": ing_name, "namespace": ns},
                                    "patch": f"- op: add\n  path: /metadata/annotations/traefik.ingress.kubernetes.io~1router.middlewares\n  value: {ns}-gotrue-chain@kubernetescrd\n"})
        # netpols (Walk; Run keeps them and the matrix is a Run recommendation the reviewer asks for)
        if stage == "walk":
            self.write(sdir / "namespaces" / ns / "netpols.yaml", self.netpols(stage, depth_note=""))
        elif self.setting("security", stage, "egress_matrix") == "required":
            self.notes.append("OPEN: security egress_matrix is required at Run; write the per-workload matrix next to stages/run (netpol-matrix-check reads it)")
        sub = {"namespace": ns, "resources": sub_resources}
        for c in scoped:
            meta = COMPONENTS.get(c) or {}
            if meta.get("config"):
                sub.setdefault("configMapGenerator", []).append({"name": meta["config"][0], "literals": meta["config"][1], "options": {"disableNameSuffixHash": True}})
        self.write(sdir / "namespaces" / ns / "kustomization.yaml", f"# {stage}: what the records add inside {ns} (components fit for {stage}, NetworkPolicies, the secrets mechanism, the surface).\n" + dump(sub))
        # argocd
        gitops = self.setting("devops", stage, "gitops")
        if gitops == "argocd":
            resources += self.argocd_files(stage, f"k8s/overlays/usecases/{self.name}/stages/{stage}", f"ssh://git@github.com/{self.org}/forjate.git", sdir, 5, wiring=(stage == "walk"))
            if stage == "walk" and "apps/continuous-delivery/argocd" in self.choices(stage):
                patches.append({"path": "argocd/repo-server-ssh-patch.yaml", "target": {"kind": "Deployment", "name": "argocd-repo-server", "namespace": "argocd"}})
                patches.append({"path": "argocd/cmd-params-cm-patch.yaml", "target": {"kind": "ConfigMap", "name": "argocd-cmd-params-cm", "namespace": "argocd"}})
        doc = {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "resources": resources, "patches": patches}
        if stage == "walk":
            doc["labels"] = [{"pairs": {"app.kubernetes.io/managed-by": "kustomize", "app.kubernetes.io/overlay": self.name}}]
        if image:
            registry = self.setting("devops", stage, "image_registry", "ghcr.io")
            img = {"name": image, "newName": f"{registry}/{self.org.lower()}/{image}"}
            if stage == "run" or self.setting("security", stage, "image_policy") in ("pinned-digest", "signed"):
                img["digest"] = PLACEHOLDER_DIGEST
            else:
                img["newTag"] = PLACEHOLDER_SHA
            doc["images"] = [img]
        head = (f"# {stage} stage of {self.name}: {'recomposes the Crawl root (base, Crawl components, the namespace child)' if stage == 'walk' else 'extends ../walk'} and adds what the records require for {stage}, nothing the plan put out of scope.\n"
                f"# images: is the write-back surface: sync-app-image.yml (repository_dispatch app-image-updated) sets the SHA with yq, never sed.\n"
                "# Every remote ref is a tag (ref-pinning-check); the Application tracks a tag with selfHeal (argocd-revision-check).\n")
        self.write(sdir / "kustomization.yaml", head + dump(doc))

    # ------------------------------------------------------------ tenant target
    def write_tenant(self, repo: Path, tenant: str) -> None:
        k8s = repo / "k8s"
        ns = self.ns
        nsdir = k8s / "namespaces" / ns
        stage = "walk" if "walk" in self.in_scope else "crawl"
        comps = [c for c in self.choices("crawl") + self.new_at("walk") if not self.infra(c)] if stage == "walk" else [c for c in self.choices("crawl") if not self.infra(c)]
        infra = [c for c in self.choices(stage) if self.infra(c)]
        sc = (self.scaffold or {}).get("spec", {})
        image = sc.get("image")
        root_path = k8s / "kustomization.yaml"
        if not root_path.exists():
            root = {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
                    "resources": [f"ssh://git@github.com/{self.org}/forjate.git//k8s/base?ref={self.factory_ref}"] + [self.ssh_component(c) for c in infra] + [f"./namespaces/{ns}"],
                    "labels": [{"pairs": {"app.kubernetes.io/managed-by": "kustomize", "app.kubernetes.io/overlay": tenant}}]}
            self.write(root_path, f"# Tenant root of {tenant}: the factory base and the cluster-level components by SSH ref pinned to one tag ({self.factory_ref}),\n# then one namespace child per use case. No base/ + overlays/ split (tenant-patterns.md).\n" + dump(root))
        else:
            self.notes.append(f"add to {root_path}: ./namespaces/{ns} and the infra components " + ", ".join(self.ssh_component(c) for c in infra))
        psa = self.setting("security", stage, "psa_level", "baseline")
        self.write(nsdir / "namespace.yaml", dump({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns, "labels": {"forjate.io/usecase": self.name, "pod-security.kubernetes.io/enforce": psa, "pod-security.kubernetes.io/warn": "restricted", "pod-security.kubernetes.io/audit": "restricted"}}}))
        resources = ["namespace.yaml"] + [self.ssh_component(c) for c in comps] + ["netpols.yaml"]
        for w in sc.get("workloads", []):
            self.write(nsdir / f"{w['name']}.yaml", self.workload_manifest(w, image=image))
            resources.append(f"{w['name']}.yaml")
        patches: list[dict] = []
        for c in comps:
            meta = COMPONENTS.get(c) or {}
            if meta.get("glue") == "minio-dev":
                self.write(nsdir / "minio-service.yaml", dump({"apiVersion": "v1", "kind": "Service", "metadata": {"name": "minio"}, "spec": {"selector": {"app": "minio"}, "ports": [{"port": 9000, "targetPort": 9000}]}}))
                resources.append("minio-service.yaml")
            if meta.get("config"):
                pass
        secrets = self.crawl_secrets() + (self.stage_secrets("walk") if stage == "walk" else [])
        for sname, keys, origin in secrets:
            patches.append({"target": {"kind": "Secret", "name": sname}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {sname}\n"})
            self.write(nsdir / "secrets" / f"sealed-{sname}.yaml", self.sealed_placeholder(sname, keys))
            self.write(nsdir / "secrets" / f"{sname}.env.example", self.env_example(sname, keys, origin, stage="walk"))
            resources.append(f"secrets/sealed-{sname}.yaml")
        for c in comps:
            ph = (COMPONENTS.get(c) or {}).get("placeholder_secret")
            if ph and ph not in [s[0] for s in secrets]:
                patches.append({"target": {"kind": "Secret", "name": ph}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {ph}\n"})
        self.write(nsdir / "netpols.yaml", self.netpols(stage, depth_note=""))
        doc = {"namespace": ns, "resources": resources, "patches": patches}
        for c in comps:
            meta = COMPONENTS.get(c) or {}
            if meta.get("config"):
                doc.setdefault("configMapGenerator", []).append({"name": meta["config"][0], "literals": meta["config"][1], "options": {"disableNameSuffixHash": True}})
        if image:
            registry = self.setting("devops", stage, "image_registry", "ghcr.io")
            doc["images"] = [{"name": image, "newName": f"{registry}/{self.org.lower()}/{image}", "newTag": PLACEHOLDER_SHA}]
        head = (f"# {ns} as a namespace child of the {tenant} tenant root: components by SSH ref pinned to {self.factory_ref}, the scaffold's workloads,\n"
                "# every factory placeholder Secret deleted and replaced by a SealedSecret of the same name (its .env.example carries the recipe),\n"
                "# images: is the write-back surface (sync-app-image.yml edits newTag with yq).\n")
        self.write(nsdir / "kustomization.yaml", head + dump(doc))
        if self.setting("devops", stage, "gitops") == "argocd":
            self.argocd_files(stage, f"k8s", f"ssh://git@github.com/{self.org}/{tenant}-iac.git", k8s, 1)
            self.notes.append(f"apply k8s/argocd/application.yaml to the argocd namespace; the Application tracks {self.factory_ref} of the tenant repo, adjust repoURL")
        self.write(k8s / ".gitignore", "# Real credentials never land in git; the committed examples do.\n**/secrets/*.env\n!**/secrets/*.env.example\n")
        self.write(repo / "k8s" / "README.md" if not (repo / "k8s" / "README.md").exists() else repo / "k8s" / f"README-{self.name}.md", self.readme_text(tenant=tenant), keep=False)

    # ------------------------------------------------------------ README
    def readme_text(self, *, tenant: str | None = None) -> str:
        b = self.brief["spec"]
        lines = [f"# Use case: `{self.name}`" + (f" (tenant {tenant})" if tenant else ""), "",
                 f"> {b['problem']}", "",
                 f"Assembled by `forjate:kustomize` from `.builder/` (brief, stage plan, {len(self.records)} decision records, gates). Success metric: {b['success']['metric']} (baseline {b['success'].get('baseline', '?')}, target {b['success'].get('target', '?')}).", ""]
        if not tenant:
            lines += ["## Run it", "", "```bash",
                      f"./scripts/ephemeral/ephemeral.sh up {self.name}        # builds app/ into {self.name}:dev, imports it, seed -> run -> verify",
                      f"./scripts/ephemeral/ephemeral.sh validate {self.name}  # re-run only the verify Job",
                      f"python3 scripts/gates/gates.py run {self.name} --transition 'crawl->walk'",
                      f"kubectl kustomize --enable-helm k8s/overlays/usecases/{self.name}/stages/walk | kubeconform -strict -ignore-missing-schemas -",
                      "```", ""]
        lines += ["## Decisions", "", "| Area | Crawl | Walk | Run |", "|---|---|---|---|"]
        for area, r in self.records.items():
            cells = []
            for s in STAGES:
                sd = r["spec"]["stages"].get(s)
                if not sd:
                    cells.append("out of scope"); continue
                choice = ", ".join(f"`{c}`" for c in sd.get("choice") or []) or "no component"
                first = str(sd.get("rationale", "")).strip().split(". ")[0][:140]
                cells.append(f"{choice}. {first}")
            lines.append(f"| {area} | " + " | ".join(cells) + " |")
        oq = [(a, q) for a, r in self.records.items() for q in r["spec"].get("open_questions") or []]
        lines += ["", "## Open questions", ""] + ([f"- **{a} {q['id']}** (blocks {q.get('blocks_stage', 'nothing')}" + (f", {q['caused_by_rule']}" if q.get("caused_by_rule") else "") + f"): {str(q['question']).strip()}" for a, q in oq] or ["none"])
        if self.gates:
            lines += ["", "## Gates", "", "| Transition | Approver | Gates | ci | verify-job | metric | manual |", "|---|---|---|---|---|---|---|"]
            for tr, body in self.gates["spec"]["transitions"].items():
                counts = {t: 0 for t in ("ci", "verify-job", "metric", "manual")}
                for g in body.get("gates") or []:
                    counts[((g.get("check") or {}).get("type") or "manual")] += 1
                lines.append(f"| {tr} | {body.get('approver', '')} | {sum(counts.values())} | {counts['ci']} | {counts['verify-job']} | {counts['metric']} | {counts['manual']} |")
            lines += ["", f"`scripts/gates/gates.py run {self.name} --transition <t>` executes them; `manual` gates list their signer and never block."]
        lines += ["", "## Checklist (kustomize skill, CONVENTION.md tiers)", "",
                  "- [x] builds with `kustomize build --enable-helm` and passes kubeconform (CI: validate-kustomize)",
                  "- [x] `usecase.yaml` validates; seed and verify Jobs exist suspended (CI: validate-usecases)",
                  "- [x] `.env.example` with the generate and seal header for every secret; real `.env` gitignored",
                  "- [x] plaintext-credential scan clean over the whole use case (`secret-scan.py`, CI: validate-kustomize)",
                  "- [x] from Walk: PSA labels, default-deny NetworkPolicies, the egress allow-list, sealed secrets replacing every generated Secret, the ArgoCD Application on a tag",
                  "- [ ] seal the real secrets with the recipe in each `.env.example` before the first Walk sync",
                  "- [ ] patch the hostnames (`*.example.com`) and the ArgoCD `targetRevision` to the release tag"]
        if self.notes:
            lines += ["", "## Assembly notes", ""] + [f"- {n}" for n in self.notes]
        return "\n".join(lines) + "\n"

    def write_readme(self) -> None:
        self.write(self.uc / "README.md", self.readme_text(), keep=False)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("usecase_dir")
    ap.add_argument("--target", choices=["overlay", "tenant"], default="overlay")
    ap.add_argument("--tenant-repo", help="tenant repository root (target tenant)")
    ap.add_argument("--tenant", help="tenant name for app.kubernetes.io/overlay (default: the repo directory name)")
    ap.add_argument("--factory-ref", default="v1.2.0", help="factory tag the tenant pins and the Application tracks")
    ap.add_argument("--org", default="AItizate")
    ap.add_argument("--force", action="store_true", help="overwrite files that already exist")
    a = ap.parse_args(argv)
    asm = Assembly(Path(a.usecase_dir), org=a.org, factory_ref=a.factory_ref, force=a.force)
    if a.target == "overlay":
        asm.write_overlay()
    else:
        if not a.tenant_repo:
            ap.error("--tenant-repo is required for --target tenant")
        repo = Path(a.tenant_repo).resolve()
        asm.write_tenant(repo, a.tenant or repo.name)
    for p in asm.written:
        print(f"wrote {p}")
    for n in asm.notes:
        print(f"note: {n}")
    print(f"assembled {asm.name} ({a.target}): {len(asm.written)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
