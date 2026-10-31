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
from common import PSA_RANK, load_catalog, load_yaml, stage_components  # noqa: E402

STAGES = ("crawl", "walk", "run")
# Where a component runs and the PSA level its pods meet are catalog facts (`namespace`,
# `namespace_how`, `psa_level` in wiki/catalog.json, derived from k8s/** by wiki-compile.py):
# a component with a `namespace` is shared infrastructure and goes at a stage root, never under
# the use case's namespaced sub-overlay; the rest go in uc-<name> unless the security record's
# psa_exceptions move them. Kubernetes' own namespaces are never labelled by a use case.
SYSTEM_NAMESPACES = {"kube-system", "kube-public", "kube-node-lease", "default"}
CLUSTER_SCOPED = {"Namespace", "ClusterRole", "ClusterRoleBinding", "CustomResourceDefinition", "StorageClass",
                  "PersistentVolume", "PriorityClass", "MutatingWebhookConfiguration", "ValidatingWebhookConfiguration",
                  "IngressClass", "CSIDriver", "APIService", "ClusterIssuer", "ClusterSecretStore", "RuntimeClass"}
REMOTE = re.compile(r"^(https?://|ssh://|git@|github\.com/)")
# What the assembly knows about catalog components it wires: service, port, protocol, the Secret the
# component mounts (name, keys), the pod label for NetworkPolicies, laptop sizing, glue manifests.
# No component is named here. What an overlay needs to wire a component (its Service and port, the pod label,
# the Secret it mounts and its keys, placeholders to replace, a ConfigMap to generate, an Ingress to put behind
# auth, a GPU limit or a hostPath a laptop cannot satisfy, laptop sizing) is a catalog fact: wiki-compile.py derives
# `wiring` from the component's manifests and catalog-overrides.yaml curates the rest. See Assembly.meta().
CONTRACT_COMPONENT = re.compile(r"^apps/[a-z0-9-]+/[a-z0-9-]+$")
PLACEHOLDER_SHA = "0" * 40
PLACEHOLDER_DIGEST = "sha256:" + "0" * 64


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def dump(doc) -> str:
    return yaml.safe_dump(doc, sort_keys=False, width=120, allow_unicode=True)


class Assembly:
    def __init__(self, uc_dir: Path, *, org: str, factory_ref: str, force: bool):
        self._meta: dict[str, dict] = {}
        self._noted_keys: set[str] = set()
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
        catalog = load_catalog()
        if catalog is None:
            raise SystemExit("error: wiki/catalog.json not reachable (run from the factory root or set FORJATE_ROOT)")
        self.catalog = {c["path"]: c for c in catalog.get("components") or []}
        self.k8s = next(p for p in self.uc.parents if p.name == "k8s")
        self.declared_ns = {o["metadata"]["name"] for o in self.local_objects(self.k8s / "base") if o["kind"] == "Namespace"}
        self.declared_ns |= {ns for c in self.choices("crawl") if (ns := self.fact(c, "namespace")) and self.fact(c, "namespace_how") == "declares"}
        self.labelled_ns: dict[str, str] = {}
        self.exception_secrets: dict[str, list[str]] = {}

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

    def fact(self, c: str, key: str, default=None):
        return (self.catalog.get(c) or {}).get(key, default)

    def infra(self, c: str) -> bool:
        """Shared infrastructure: the catalog gives it a namespace of its own."""
        return bool(self.fact(c, "namespace"))

    def meta(self, c: str) -> dict:
        """The wiring of a component, from the catalog's `wiring` facts (derived from its manifests by wiki-compile.py,
        curated in catalog-overrides.yaml where the tree cannot say: protocol, laptop sizing, a Secret the component
        takes but documents nowhere). Shape: service, port, protocol, label, secret (name, keys) or None, placeholders
        (shipped Secrets a pod references, replaced from Walk), config (name, literals) or None, ingress, sizing
        (kind, name, container, requests, limits) or None, bare_service (a workload with no Service of its own),
        secret_mounted, hostpath_volumes, gpu_drop (a GPU limit a laptop cannot satisfy on an optional-GPU component)."""
        if c in self._meta:
            return self._meta[c]
        w = self.fact(c, "wiring") or {}
        sec = w.get("secret") or {}
        if sec.get("name") and not sec.get("keys") and c not in self._noted_keys:
            self._noted_keys.add(c)
            self.notes.append(f"OPEN: {c} mounts {sec['name']} but documents no keys; add them to wiring.secret.keys in wiki/catalog-overrides.yaml or write the .env.example by hand")
        wl = w.get("workload") or {}
        sz = w.get("sizing") or {}
        shipped_services = {n for k, n in ((o["kind"], (o.get("metadata") or {}).get("name")) for o in self.local_objects(self.k8s / "components" / c)) if k == "Service"}
        out = {
            "service": w.get("service"), "port": w.get("port"), "protocol": w.get("protocol") or "tcp", "label": w.get("label"),
            "secret": (sec["name"], list(sec["keys"])) if sec.get("name") and sec.get("keys") else None,
            "placeholders": list(w.get("placeholder_secrets") or []),
            "config": (w["config"]["name"], list(w["config"]["literals"])) if (w.get("config") or {}).get("literals") else None,
            "ingress": w.get("ingress"),
            "sizing": (wl["kind"], wl["name"], wl.get("container") or wl["name"], sz["requests"]["cpu"], sz["requests"]["memory"], sz["limits"]["cpu"], sz["limits"]["memory"]) if sz and wl else None,
            "bare_service": bool(w.get("service")) and w.get("service") not in shipped_services,
            "extra_ports": dict(w.get("extra_ports") or {}),
            "secret_mounted": bool(w.get("secret_mounted")),
            "hostpath_volumes": list(w.get("hostpath_volumes") or []),
            "gpu_drop": bool(w.get("gpu_limit")) and self.fact(c, "gpu_required") != "required",
            "workload": wl,
        }
        self._meta[c] = out
        return out

    def runs(self, stage: str) -> list[str]:
        """Every component the stage's build contains: what the records choose at that stage, the same set
        validate.py reads (common.stage_components). A Crawl choice no Walk record repeats is superseded or
        dropped, and the stage overlay deletes its objects from the build it recomposes."""
        return stage_components(self.records, stage)

    def dropped_at(self, stage: str) -> list[str]:
        """Use-case-scoped components the previous stage ran and this stage does not."""
        if stage == "crawl":
            return []
        prev = STAGES[STAGES.index(stage) - 1]
        return [c for c in self.runs(prev) if c not in self.runs(stage) and not self.infra(c)]

    def psa_exceptions(self, stage: str) -> list[dict]:
        r = self.records.get("security")
        return list(((r or {}).get("spec", {}).get("stages", {}).get(stage) or {}).get("psa_exceptions") or [])

    def placement(self, stage: str) -> dict[str, str]:
        """Use-case-scoped components the security record moves out of uc-<name>, and where."""
        if stage == "crawl":
            return {}
        return {c: e["namespace"] for e in self.psa_exceptions(stage) for c in e["components"] if not self.infra(c)}

    def home(self, c: str, stage: str) -> str:
        """The namespace a component runs in at a stage."""
        return self.fact(c, "namespace") or self.placement(stage).get(c) or self.ns

    def local_objects(self, d: Path) -> list[dict]:
        """Objects a kustomization lists from local files, recursively, plus its generators; remote refs
        and Helm charts are not read. Used for names and kinds, never to rebuild the manifest."""
        k = d / "kustomization.yaml"
        if not k.is_file():
            return []
        doc = load_yaml(k)
        out: list[dict] = []
        for r in doc.get("resources") or []:
            if not isinstance(r, str) or REMOTE.match(r):
                continue
            t = (d / r).resolve()
            if t.is_dir():
                out += self.local_objects(t)
            elif t.is_file() and t.suffix in (".yaml", ".yml"):
                out += [x for x in yaml.safe_load_all(t.read_text()) if isinstance(x, dict) and x.get("kind")]
        for gen, kind in (("configMapGenerator", "ConfigMap"), ("secretGenerator", "Secret")):
            out += [{"kind": kind, "metadata": {"name": g["name"]}} for g in doc.get(gen) or [] if isinstance(g, dict) and g.get("name")]
        return out

    def objects_of(self, c: str) -> list[tuple[str, str]]:
        """(kind, name) of the namespaced objects a use-case-scoped component brings into uc-<name>,
        including the glue and the config the assembly adds for it."""
        objs = [(o["kind"], o["metadata"]["name"]) for o in self.local_objects(self.k8s / "components" / c)
                if o["kind"] not in CLUSTER_SCOPED and (o.get("metadata") or {}).get("name")]
        meta = self.meta(c)
        if meta.get("bare_service"):
            objs.append(("Service", meta["service"]))
        if meta.get("config"):
            objs.append(("ConfigMap", meta["config"][0]))
        if self.fact(c, "remote_refs") or not objs:
            self.notes.append(f"OPEN: {c} is moved out of {self.ns} but part of it is remote or Helm-rendered; move those objects by hand")
        return list(dict.fromkeys(objs))

    def services_of(self, c: str) -> list[str]:
        return [n for k, n in self.objects_of(c) if k == "Service"]

    def psa_labels(self, level: str) -> dict:
        return {"pod-security.kubernetes.io/enforce": level, "pod-security.kubernetes.io/warn": "restricted", "pod-security.kubernetes.io/audit": "restricted"}

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
            meta = self.meta(c)
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
            meta = self.meta(c)
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

    def secrets_at(self, stage: str) -> list[tuple[str, list[str], str]]:
        """(secret name, keys, origin) the stage's build needs: the Secrets of the components that run at the
        stage, the scaffold's, and the integration tokens of this and the earlier stages. A dropped
        component's Secret leaves with it."""
        out: list[tuple[str, list[str], str]] = []
        names: set[str] = set()
        for c in self.runs(stage):
            meta = self.meta(c)
            if meta.get("secret") and meta["secret"][0] not in names:
                out.append((meta["secret"][0], meta["secret"][1], c)); names.add(meta["secret"][0])
        for s in self.crawl_secrets():
            if s[2].startswith("scaffold:") and s[0] not in names:
                out.append(s); names.add(s[0])
        for st in STAGES[1:STAGES.index(stage) + 1]:
            for s in self.stage_secrets(st):
                if s[2].startswith("integration:") and s[0] not in names:
                    out.append(s); names.add(s[0])
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
        enc = "\n".join(f"    {k}: {'AgA' + 'x' * 40}  # placeholder: run the seal command from {name}.env.example" for k in keys) or "    {}"
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
            # A server that waits for its database before it listens refuses /healthz meanwhile: without a startup probe the
            # liveness probe restarts it, and a client that calls it (the replay Job) meets the outage as a failed lookup.
            container["startupProbe"] = {"httpGet": {"path": w["health_path"], "port": port}, "periodSeconds": 5, "failureThreshold": 36}
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
            meta = self.meta(c)
            wl = meta.get("workload") or {}
            pod_prefix = "/spec" if wl.get("kind") == "Pod" else "/spec/template/spec"
            if meta.get("sizing"):
                kind, name, cname, rc, rm, lc, lm = meta["sizing"]
                container = {"name": cname, "resources": {"requests": {"cpu": rc, "memory": rm}, "limits": {"cpu": lc, "memory": lm}}}
                doc = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name}, "spec": {"containers": [container]}} if kind == "Pod" else \
                      {"apiVersion": "apps/v1", "kind": kind, "metadata": {"name": name}, "spec": {"template": {"spec": {"containers": [container]}}}}
                self.write(nsdir / "patches" / f"{name}-resources-patch.yaml", f"# Laptop sizing for {c} (catalog defaults are sized for tenants; strategic merge on the container name).\n" + dump(doc))
                patches.append({"path": f"patches/{name}-resources-patch.yaml", "target": {"kind": kind, "name": name}})
            if meta.get("bare_service"):
                # the component ships a workload and no Service: the overlay adds the one the contract advertises
                ports = [{"name": "api", "port": meta["port"], "targetPort": meta["port"]}] + [{"name": n, "port": p, "targetPort": p} for n, p in meta["extra_ports"].items()]
                self.write(nsdir / f"{meta['service']}-service.yaml", f"# {c} ships no Service; the overlay adds the one the contract advertises (catalog wiring).\n" + dump(
                    {"apiVersion": "v1", "kind": "Service", "metadata": {"name": meta["service"]}, "spec": {"selector": {"app": meta["label"]}, "ports": ports}}))
                resources.append(f"{meta['service']}-service.yaml")
            if meta.get("secret") and not meta.get("secret_mounted") and wl:
                # the component takes credentials its manifests never reference: mount the overlay's Secret on the container
                container = {"name": wl.get("container") or wl["name"], "envFrom": [{"secretRef": {"name": meta["secret"][0]}}]}
                doc = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": wl["name"]}, "spec": {"containers": [container]}} if wl["kind"] == "Pod" else \
                      {"apiVersion": "apps/v1", "kind": wl["kind"], "metadata": {"name": wl["name"]}, "spec": {"template": {"spec": {"containers": [container]}}}}
                self.write(nsdir / "patches" / f"{wl['name']}-env-patch.yaml", f"# {c} has no credentials in its manifests; mount the overlay's {meta['secret'][0]} (strategic merge on the container name).\n" + dump(doc))
                patches.append({"path": f"patches/{wl['name']}-env-patch.yaml", "target": {"kind": wl["kind"], "name": wl["name"]}})
            for v in meta.get("hostpath_volumes") or []:
                # a hostPath is root-owned on k3d and the image rarely runs as root: an emptyDir is the laptop's disk at Crawl
                prefix = "/spec" if v.get("kind") == "Pod" else "/spec/template/spec"
                patches.append({"target": {"kind": v["kind"], "name": v["workload"]},
                                "patch": f"# assumes volumes[{v['index']}] is {v['name']} (upstream manifest); the hostPath is root-owned on k3d, an emptyDir is the laptop's disk at Crawl\n- op: replace\n  path: {prefix}/volumes/{v['index']}\n  value: {{name: {v['name']}, emptyDir: {{}}}}\n"})
            if meta.get("gpu_drop") and wl:
                patches.append({"target": {"kind": wl["kind"], "name": wl["name"]},
                                "patch": f"# assumes containers[0] is {wl.get('container') or wl['name']} (upstream manifest); drops the GPU limit a laptop cannot satisfy (catalog gpu_required: {self.fact(c, 'gpu_required')})\n- op: remove\n  path: {pod_prefix}/containers/0/resources/limits/nvidia.com~1gpu\n"})
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
            meta = self.meta(c)
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
            meta = self.meta(c)
            if meta.get("service"):
                endpoints.append({"name": c.split("/")[-1], "service": meta["service"], "port": meta["port"], "protocol": meta.get("protocol", "tcp")})
            if meta.get("secret"):
                secrets.append({"name": f"{c.split('/')[-1]}-credentials", "secretRef": meta["secret"][0], "keys": meta["secret"][1]})
        for w in workloads:
            if w["kind"] == "deployment":
                endpoints.append({"name": w["name"], "service": w["name"], "port": w.get("port", 8000), "protocol": "http"})
        # cluster-level controllers (shared infrastructure, or an operator-backed component) need their own cluster
        dedicated = any(self.infra(c) or self.fact(c, "ha") == "operator" for c in crawl)
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
        comps = [c for c in self.choices(stage) if not self.infra(c) and self.meta(c).get("label")]
        workloads = (self.scaffold or {}).get("spec", {}).get("workloads", [])
        # (pod label, port, namespace): a component a psa_exceptions entry moved is reached across namespaces
        targets = [(self.meta(c)["label"], self.meta(c)["port"], self.home(c, stage)) for c in comps] + [(w["name"], w.get("port", 8000), ns) for w in workloads if w["kind"] == "deployment"]

        def peer(lbl: str, home: str) -> dict:
            sel = {"podSelector": {"matchLabels": {"app": lbl}}}
            if home != ns:
                sel["namespaceSelector"] = {"matchLabels": {"kubernetes.io/metadata.name": home}}
            return sel

        for w in workloads:
            to = [{"to": [peer(lbl, home)], "ports": [{"protocol": "TCP", "port": port}]} for lbl, port, home in targets if lbl != w["name"]]
            docs.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": f"allow-{w['name']}-egress", "namespace": ns},
                         "spec": {"podSelector": {"matchLabels": {"app": w["name"]}}, "policyTypes": ["Egress"], "egress": to}})
        for lbl, port, home in targets:
            if home != ns:
                continue
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

    def exception_netpols(self, stage: str, n: str, comps: list[str]) -> str:
        """default-deny in an exception namespace: DNS, traffic inside it, the use case's namespace to the
        moved components' ports, and the ingress controller to the ones it serves (an Ingress or the IdP)."""
        ports = sorted({self.meta(c).get("port") for c in comps} - {None})
        served = [c for c in comps if self.meta(c).get("ingress") or "identity-provider" in (self.fact(c, "capabilities") or [])]
        from_uc = {"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": self.ns}}}]}
        if ports:
            from_uc["ports"] = [{"protocol": "TCP", "port": p} for p in ports]
        docs = [
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "default-deny", "namespace": n}, "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}},
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "allow-dns", "namespace": n},
             "spec": {"podSelector": {}, "policyTypes": ["Egress"], "egress": [{"to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}}], "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}},
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "allow-same-namespace", "namespace": n},
             "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"], "ingress": [{"from": [{"podSelector": {}}]}], "egress": [{"to": [{"podSelector": {}}]}]}},
            {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": f"allow-ingress-from-{self.ns}", "namespace": n},
             "spec": {"podSelector": {}, "policyTypes": ["Ingress"], "ingress": [from_uc]}},
        ]
        if served:
            docs.append({"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "allow-ingress-controller", "namespace": n},
                         "spec": {"podSelector": {}, "policyTypes": ["Ingress"], "ingress": [{"from": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "traefik"}}}]}]}})
        head = (f"# NetworkPolicies for {n} at {stage}: the PSA exception namespace of {self.name} (security: psa_exceptions), default-deny like {self.ns}.\n"
                f"# Components: {', '.join(comps)}. Egress to anything outside the cluster is not allowed here; add it by hand if one of them needs it.\n")
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
        new = self.new_at(stage)
        infra = [c for c in new if self.infra(c)]
        scoped = [c for c in new if not self.infra(c)]
        sc = (self.scaffold or {}).get("spec", {})
        image = sc.get("image")
        patches: list[dict] = []
        # PSA exceptions (security: psa_exceptions): use-case-scoped components that cannot run at the use
        # case's level leave uc-<name> for a namespace of their own. One already in the build is moved by a
        # relocation layer under the stage (a patch and an alias in one kustomization collide); one the stage
        # adds is composed straight into its namespace. A stage overlay never moves a component back.
        place = self.placement(stage)
        prev_place = self.placement("walk") if stage == "run" else {}
        before = self.runs(STAGES[STAGES.index(stage) - 1])
        dropped = self.dropped_at(stage)
        for c, n in prev_place.items():
            if c in dropped:
                continue
            if place.get(c) != n:
                self.notes.append(f"OPEN: {c} was moved to {n} at walk and the {stage} record says {place.get(c) or 'nothing'}; a stage overlay never moves a component back, edit the walk exception")
        relocate = {c: n for c, n in place.items() if c in before and c not in prev_place}
        placed = {c: place[c] for c in scoped if c in place}
        arriving: dict[str, list[str]] = {}
        for c, n in list(relocate.items()) + list(placed.items()):
            arriving.setdefault(n, []).append(c)
        wrapped = f"../../namespaces/{ns}" if stage == "walk" else "../walk"
        if relocate or dropped:
            moves = [{"target": {"kind": kind, "name": name, "namespace": ns}, "patch": f"- op: replace\n  path: /metadata/namespace\n  value: {n}\n"}
                     for c, n in relocate.items() for kind, name in self.objects_of(c)]
            # a component the previous stage ran and no record repeats at this stage leaves the build:
            # superseded by one that covers its capability (the records' choice), or dropped on purpose
            prev_stage = STAGES[STAGES.index(stage) - 1]
            for c in dropped:
                home = self.home(c, prev_stage)
                targets = [(kind, name, home) for kind, name in self.objects_of(c) if kind != "Secret"]  # the stage's secrets are written from what runs at the stage
                if home != ns:  # a relocated component left ExternalName aliases of its Services in uc-<name>
                    targets += [("Service", svc, ns) for svc in self.services_of(c)]
                for kind, name, where in targets:
                    moves.append({"target": {"kind": kind, "name": name, "namespace": where},
                                  "patch": f"# {c} ran at {prev_stage} and no record chooses it at {stage}\n$patch: delete\nkind: {kind}\nmetadata:\n  name: {name}\n"})
            self.write(sdir / "relocated" / "kustomization.yaml",
                       f"# {stage}: the build so far with the PSA exceptions moved out of {ns} (security: psa_exceptions)"
                       + (f" and the components {stage} no longer runs deleted ({', '.join(dropped)})" if dropped else "") + ".\n"
                       "# A layer of its own because the aliases left in the use case's namespace would collide with the originals here.\n"
                       + dump({"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "resources": ["../" + wrapped], "patches": moves}))
            wrapped = "./relocated"
        prev = (["../../../../../base"] + [self.rel_component(c, 5) for c in crawl_infra] + [wrapped]) if stage == "walk" else [wrapped]
        # shared infrastructure: at the stage root, or placed in its namespace when its manifests set none;
        # a component whose Namespace the build already has is wrapped so the duplicate is dropped
        root_infra: list[str] = []
        ns_dirs: dict[str, dict] = {}
        for c in infra:
            n, how = self.fact(c, "namespace"), self.fact(c, "namespace_how")
            if how == "none":
                ns_dirs.setdefault(n, {"resources": [], "declare": False})["resources"].append(self.rel_component(c, 7))
            elif how == "declares" and n in self.declared_ns:
                wdir = f"wrapped/{slug(c)}"
                self.write(sdir / wdir / "kustomization.yaml", f"# {c} ships the Namespace {n}, which the build already has: the duplicate is dropped here.\n" + dump(
                    {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "resources": [self.rel_component(c, 7)],
                     "patches": [{"target": {"kind": "Namespace", "name": n}, "patch": f"$patch: delete\napiVersion: v1\nkind: Namespace\nmetadata:\n  name: {n}\n"}]}))
                root_infra.append(f"./{wdir}")
            else:
                root_infra.append(self.rel_component(c, 5))
                if how == "declares":
                    self.declared_ns.add(n)
        resources = prev + root_infra + [f"./namespaces/{ns}"]
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
        sub_resources = (["netpols.yaml"] if stage == "walk" else []) + [self.rel_component(c, 7) for c in scoped if c not in placed]
        all_secrets = self.secrets_at(stage)
        # a component's Secret stays in uc-<name> while a workload there consumes it or the component runs there
        consumed = {x for w in sc.get("workloads", []) for x in w.get("secrets") or []}
        all_secrets = [t for t in all_secrets if t[2] not in self.catalog or self.home(t[2], stage) == ns or t[0] in consumed]
        if stage == "walk":
            for sname, keys, origin in self.crawl_secrets():
                patches.append({"target": {"kind": "Secret", "name": sname, "namespace": ns}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {sname}\n"})
            for c in scoped:
                for ph in self.meta(c)["placeholders"]:
                    patches.append({"target": {"kind": "Secret", "name": ph, "namespace": self.home(c, stage)}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {ph}\n"})
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
        idp = next((c for c in self.runs(stage) if "identity-provider" in (self.fact(c, "capabilities") or [])), None)
        mw = f"{self.home(idp, stage) if idp else ns}-gotrue-chain@kubernetescrd"
        if stage == "walk" and auth == "oauth2-proxy" and surface and surface != "none":
            port = next((w.get("port", 8000) for w in sc.get("workloads", []) if w["name"] == surface), 8000)
            ing = {"apiVersion": "networking.k8s.io/v1", "kind": "Ingress", "metadata": {"name": surface, "namespace": ns,
                   "annotations": {"traefik.ingress.kubernetes.io/router.middlewares": mw, "cert-manager.io/cluster-issuer": "letsencrypt-prod"}},
                   "spec": {"ingressClassName": "traefik", "rules": [{"host": f"{self.name}.example.com", "http": {"paths": [{"path": "/", "pathType": "Prefix", "backend": {"service": {"name": surface, "port": {"number": port}}}}]}}],
                            "tls": [{"hosts": [f"{self.name}.example.com"], "secretName": f"{surface}-tls"}]}}
            self.write(sdir / "namespaces" / ns / f"{surface}-ingress.yaml", f"# The human surface (ux: {surface}) behind oauth2-proxy and GoTrue (security/architecture: auth_in_front). Patch the host.\n" + dump(ing))
            sub_resources.append(f"{surface}-ingress.yaml")
            if surface not in [w["name"] for w in sc.get("workloads", [])]:
                self.notes.append(f"OPEN: the {stage} surface workload {surface} is not in scaffold.yaml yet; the Ingress is written for the shape, the workload arrives with the {stage} scaffold")
        # component Ingresses in the namespace sit behind the auth middleware (security: auth_in_front)
        if stage == "walk" and auth == "oauth2-proxy":
            for c in scoped:
                ing_name = self.meta(c).get("ingress")
                if ing_name and "identity-provider" not in (self.fact(c, "capabilities") or []):  # the IdP's own Ingress is never behind itself
                    patches.append({"target": {"kind": "Ingress", "name": ing_name, "namespace": self.home(c, stage)},
                                    "patch": f"- op: add\n  path: /metadata/annotations/traefik.ingress.kubernetes.io~1router.middlewares\n  value: {mw}\n"})
        # netpols (Walk; Run keeps them and the matrix is a Run recommendation the reviewer asks for)
        if stage == "walk":
            self.write(sdir / "namespaces" / ns / "netpols.yaml", self.netpols(stage, depth_note=""))
        elif self.setting("security", stage, "egress_matrix") == "required":
            self.notes.append("OPEN: security egress_matrix is required at Run; write the per-workload matrix next to stages/run (netpol-matrix-check reads it)")
        # aliases: a moved component keeps its short Service name in uc-<name>, so no consumer changes
        aliases = [{"apiVersion": "v1", "kind": "Service", "metadata": {"name": svc, "namespace": ns, "labels": {"forjate.io/psa-exception": n}},
                    "spec": {"type": "ExternalName", "externalName": f"{svc}.{n}.svc.cluster.local"}}
                   for n, comps in arriving.items() for c in comps for svc in self.services_of(c)]
        if aliases:
            self.write(sdir / "namespaces" / ns / "aliases.yaml", f"# {stage}: ExternalName aliases in {ns} for the Services the PSA exceptions moved out (security: psa_exceptions).\n" + "---\n".join(dump(a) for a in aliases))
            sub_resources.append("aliases.yaml")
        sub = {"namespace": ns, "resources": sub_resources}
        for c in scoped:
            meta = self.meta(c)
            if meta.get("config") and c not in placed:
                sub.setdefault("configMapGenerator", []).append({"name": meta["config"][0], "literals": meta["config"][1], "options": {"disableNameSuffixHash": True}})
        self.write(sdir / "namespaces" / ns / "kustomization.yaml", f"# {stage}: what the records add inside {ns} (components fit for {stage}, NetworkPolicies, the secrets mechanism, the surface).\n" + dump(sub))
        resources += self.write_exception_namespaces(stage, sdir, arriving, placed, mech, patches)
        resources += self.write_shared_namespaces(stage, sdir, ns_dirs, patches, psa)
        # argocd
        gitops = self.setting("devops", stage, "gitops")
        if gitops == "argocd":
            resources += self.argocd_files(stage, f"k8s/overlays/usecases/{self.name}/stages/{stage}", f"ssh://git@github.com/{self.org}/forjate.git", sdir, 5, wiring=(stage == "walk"))
            if stage == "walk" and any("gitops" in (self.fact(c, "capabilities") or []) for c in self.choices(stage)):
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

    def ns_patch(self, sdir: Path, n: str, level: str, why: str, patches: list[dict]) -> None:
        self.write(sdir / "patches" / f"{n}-psa-patch.yaml", f"# PSA of {n} at its own level: {why}\n" + dump(
            {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": n, "labels": self.psa_labels(level)}}))
        patches.append({"path": f"patches/{n}-psa-patch.yaml", "target": {"kind": "Namespace", "name": n}})

    def secret_files(self, ndir: Path, n: str, c: str, stage: str, mech: str) -> list[str]:
        """The Secret a component mounts, in the namespace it runs in: a sealed placeholder with its recipe,
        or an ExternalSecret at Run when the mechanism moved to a central store."""
        meta = self.meta(c)
        if not meta.get("secret"):
            return []
        sname, keys = meta["secret"]
        if mech in ("external-secrets", "vault") and stage == "run":
            es = {"apiVersion": "external-secrets.io/v1beta1", "kind": "ExternalSecret", "metadata": {"name": sname, "namespace": n},
                  "spec": {"refreshInterval": "1h", "secretStoreRef": {"name": "corporate-store", "kind": "ClusterSecretStore"},
                           "target": {"name": sname, "creationPolicy": "Owner"},
                           "data": [{"secretKey": k, "remoteRef": {"key": f"{self.name}/{sname}", "property": k}} for k in keys if k != "config.env"]}}
            self.write(ndir / "externalsecrets" / f"{sname}.yaml", f"# Run: {sname} for {c} in {n}, pulled from the central store (security: secrets_mechanism {mech}).\n" + dump(es))
            return [f"externalsecrets/{sname}.yaml"]
        self.write(ndir / "secrets" / f"sealed-{sname}.yaml", self.sealed_placeholder(sname, keys).replace(f"namespace: {self.ns}", f"namespace: {n}"))
        self.write(ndir / "secrets" / f"{sname}.env.example", self.env_example(sname, keys, f"{c}, which runs in {n}; sealed once per namespace", stage=stage).replace(f"namespace: {self.ns}", f"namespace: {n}"))
        return [f"secrets/sealed-{sname}.yaml"]

    def write_exception_namespaces(self, stage: str, sdir: Path, arriving: dict[str, list[str]], placed: dict[str, str],
                                   mech: str, patches: list[dict]) -> list[str]:
        """One sub-overlay per PSA exception namespace that receives use-case-scoped components at this stage:
        the Namespace at the record's level (or a label patch when the build already declares it), the
        components the stage adds there, their Secrets and NetworkPolicies. Moved components arrive by the
        relocation layer."""
        out: list[str] = []
        entries = {e["namespace"]: e for e in self.psa_exceptions(stage)}
        net = self.setting("security", stage, "network_policy") == "default-deny"
        central = stage == "run" and mech in ("external-secrets", "vault")
        # at Run a central store replaces the SealedSecrets Walk wrote in the exception namespaces too
        targets = list(arriving) + [n for n in self.exception_secrets if central and n not in arriving]
        for n in targets:
            comps = arriving.get(n, [])
            e = entries.get(n) or {"level": self.labelled_ns.get(n, "baseline"), "owner": "?", "reason": "moved at walk"}
            ndir = sdir / "namespaces" / n
            res: list[str] = []
            why = f"exception owned by {e['owner']}: {e['reason']}"
            first = n not in self.declared_ns
            if first:
                doc = {"apiVersion": "v1", "kind": "Namespace", "metadata": {
                    "name": n, "labels": {"forjate.io/usecase": self.name, "forjate.io/psa-exception": "true", **self.psa_labels(e["level"])},
                    "annotations": {"forjate.io/psa-exception-owner": e["owner"], "forjate.io/psa-exception-reason": e["reason"]}}}
                self.write(ndir / "namespace.yaml", f"# PSA exception namespace of {self.name} at {stage} (security: psa_exceptions). {self.ns} keeps its own level.\n" + dump(doc))
                res.append("namespace.yaml")
                self.declared_ns.add(n)
            elif comps and self.labelled_ns.get(n) != e["level"]:
                self.ns_patch(sdir, n, e["level"], why, patches)
            self.labelled_ns[n] = e["level"]
            for c in comps:
                lvl = self.fact(c, "psa_level", "unknown")
                if PSA_RANK.get(lvl, -1) < PSA_RANK[e["level"]]:
                    self.notes.append(f"OPEN: {c}'s shipped manifests meet {lvl} in the catalog and {n} enforces {e['level']}: confirm this overlay's patches bring it to {e['level']}, or its pods are rejected there")
            res += [self.rel_component(c, 7) for c in comps if placed.get(c) == n]
            config = []
            for c in comps:
                meta = self.meta(c)
                if meta.get("config") and placed.get(c) == n:
                    config.append({"name": meta["config"][0], "literals": meta["config"][1], "options": {"disableNameSuffixHash": True}})
                res += self.secret_files(ndir, n, c, stage, mech)
            if central:
                for c in dict.fromkeys(self.exception_secrets.get(n, [])):
                    sname = self.meta(c)["secret"][0]
                    patches.append({"target": {"kind": "SealedSecret", "name": sname, "namespace": n}, "patch": f"$patch: delete\napiVersion: bitnami.com/v1alpha1\nkind: SealedSecret\nmetadata:\n  name: {sname}\n"})
                    res += self.secret_files(ndir, n, c, stage, mech)
            self.exception_secrets.setdefault(n, []).extend(c for c in comps if self.meta(c).get("secret"))
            if net and first:
                every = [c for c, m in self.placement(stage).items() if m == n]
                self.write(ndir / "netpols.yaml", self.exception_netpols(stage, n, every))
                res.append("netpols.yaml")
            if not res:
                continue
            sub = {"namespace": n, "resources": res}
            if config:
                sub["configMapGenerator"] = config
            self.write(ndir / "kustomization.yaml", f"# {stage}: {n}, where the PSA exceptions of {self.name} run at {e['level']} ({why}).\n" + dump(sub))
            out.append(f"./namespaces/{n}")
        return out

    def write_shared_namespaces(self, stage: str, sdir: Path, ns_dirs: dict[str, dict], patches: list[dict], psa: str) -> list[str]:
        """Each namespace shared infrastructure runs in, labelled at the level its pods meet (catalog psa_level,
        the least strict of the components the build runs there). The assembly declares the ones nobody
        declares and places the components that set none; Kubernetes' own namespaces are never labelled."""
        out: list[str] = []
        groups: dict[str, list[str]] = {}
        for c in self.runs(stage):
            if self.infra(c):
                groups.setdefault(self.fact(c, "namespace"), []).append(c)
        entries = {e["namespace"]: e for e in self.psa_exceptions(stage)}
        for n, comps in groups.items():
            levels = [self.fact(c, "psa_level", "unknown") for c in comps]
            levels = [l for l in levels if l != "n/a"]
            level = None if not levels or "unknown" in levels else min(levels, key=lambda l: PSA_RANK[l])
            if n in SYSTEM_NAMESPACES:
                continue
            if levels and level is None:
                if self.labelled_ns.get(n) != "unknown":
                    self.notes.append(f"OPEN: the catalog does not know the PSA level of {n} ({', '.join(comps)}); it is left unlabelled for its owner")
                self.labelled_ns[n] = "unknown"
                continue
            if level and PSA_RANK[level] < PSA_RANK.get(psa, 0) and n not in entries:
                self.notes.append(f"OPEN: at {stage}, {n} runs at {level}, below {self.ns}'s {psa}, and the security record has no psa_exceptions entry for it")
            if level and n in entries and entries[n]["level"] != level:
                self.notes.append(f"OPEN: at {stage}, the security record puts {n} at {entries[n]['level']}, the catalog says its pods meet {level}; the label follows the catalog")
            d = ns_dirs.get(n) or {"resources": []}
            mech = self.setting("security", stage, "secrets_mechanism", "sealed-secrets")
            for c in comps:
                if c in self.new_at(stage):
                    d["resources"] += self.secret_files(sdir / "namespaces" / n, n, c, stage, mech)
            why = f"shared infrastructure, catalog psa_level of {', '.join(comps)}."
            if n in self.declared_ns or any(self.fact(c, "namespace_how") in ("declares", "remote") for c in comps):
                if level and self.labelled_ns.get(n) != level:
                    self.ns_patch(sdir, n, level, why, patches)
            elif level or d["resources"]:
                doc = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": n, "labels": self.psa_labels(level) if level else {}}}
                self.write(sdir / "namespaces" / n / "namespace.yaml", f"# {n}: declared by the assembly, no component in it ships the Namespace ({why})\n" + dump(doc))
                d["resources"].insert(0, "namespace.yaml")
                self.declared_ns.add(n)
            if level:
                self.labelled_ns[n] = level
            if d["resources"]:
                self.write(sdir / "namespaces" / n / "kustomization.yaml", f"# {stage}: shared infrastructure in {n}; components whose manifests set no namespace are placed here.\n" + dump(
                    {"namespace": n, "resources": d["resources"]}))
                out.append(f"./namespaces/{n}")
        return out

    # ------------------------------------------------------------ tenant target
    def write_tenant(self, repo: Path, tenant: str) -> None:
        k8s = repo / "k8s"
        ns = self.ns
        nsdir = k8s / "namespaces" / ns
        stage = "walk" if "walk" in self.in_scope else "crawl"
        everything = [c for c in self.runs(stage) if not self.infra(c)]
        place = self.placement(stage)
        comps = [c for c in everything if c not in place]
        infra = [c for c in self.choices(stage) if self.infra(c)]
        sc = (self.scaffold or {}).get("spec", {})
        image = sc.get("image")
        root_path = k8s / "kustomization.yaml"
        exc_dirs = self.write_tenant_exceptions(k8s, stage, place, everything)
        # shared namespaces at their own level: patches on a root the assembly writes, notes on the tenant's own root
        shared_labels: list[tuple[str, str]] = []
        groups: dict[str, list[str]] = {}
        for c in infra:
            groups.setdefault(self.fact(c, "namespace"), []).append(c)
        for n, cs in groups.items():
            levels = [l for l in (self.fact(c, "psa_level", "unknown") for c in cs) if l != "n/a"]
            if n in SYSTEM_NAMESPACES or not levels:
                continue
            if "unknown" in levels:
                self.notes.append(f"OPEN: the catalog does not know the PSA level of {n} ({', '.join(cs)}); the tenant's owner labels it")
                continue
            shared_labels.append((n, min(levels, key=lambda l: PSA_RANK[l])))
        undeclared = [(n, l) for n, l in shared_labels
                      if n not in self.declared_ns and not any(self.fact(c, "namespace_how") in ("declares", "remote") for c in groups[n])]
        for c in infra:
            if self.fact(c, "namespace_how") == "none":
                self.notes.append(f"OPEN: {c} sets no namespace in its manifests; place it in {self.fact(c, 'namespace')} with a namespace child of the tenant root")
        if not root_path.exists():
            root = {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
                    "resources": [f"ssh://git@github.com/{self.org}/forjate.git//k8s/base?ref={self.factory_ref}"] + [self.ssh_component(c) for c in infra] + [f"./namespaces/{ns}"] + exc_dirs,
                    "labels": [{"pairs": {"app.kubernetes.io/managed-by": "kustomize", "app.kubernetes.io/overlay": tenant}}]}
            if undeclared:
                self.write(k8s / "shared-namespaces.yaml", "# Namespaces shared components use but do not ship, at the PSA level their pods meet (catalog psa_level).\n"
                           + "---\n".join(dump({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": n, "labels": self.psa_labels(l)}}) for n, l in undeclared))
                root["resources"].insert(1 + len(infra), "shared-namespaces.yaml")
            labelled = [(n, l) for n, l in shared_labels if (n, l) not in undeclared]
            if labelled:
                root["patches"] = [{"target": {"kind": "Namespace", "name": n}, "patch": dump({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": n, "labels": self.psa_labels(l)}})}
                                   for n, l in labelled]
            self.write(root_path, f"# Tenant root of {tenant}: the factory base and the cluster-level components by SSH ref pinned to one tag ({self.factory_ref}),\n# then one namespace child per use case (and per PSA exception namespace). No base/ + overlays/ split (tenant-patterns.md).\n# Shared namespaces carry the PSA level their pods meet (catalog psa_level), never the use case's.\n" + dump(root))
        else:
            self.notes.append(f"add to {root_path}: ./namespaces/{ns}" + "".join(f", {d}" for d in exc_dirs) + " and the infra components " + ", ".join(self.ssh_component(c) for c in infra))
            for n, l in shared_labels:
                self.notes.append(f"label Namespace {n} in {root_path} at pod-security.kubernetes.io/enforce={l} (catalog psa_level of what runs there)")
        psa = self.setting("security", stage, "psa_level", "baseline")
        self.write(nsdir / "namespace.yaml", dump({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns, "labels": {"forjate.io/usecase": self.name, "pod-security.kubernetes.io/enforce": psa, "pod-security.kubernetes.io/warn": "restricted", "pod-security.kubernetes.io/audit": "restricted"}}}))
        resources = ["namespace.yaml"] + [self.ssh_component(c) for c in comps] + ["netpols.yaml"]
        for w in sc.get("workloads", []):
            self.write(nsdir / f"{w['name']}.yaml", self.workload_manifest(w, image=image))
            resources.append(f"{w['name']}.yaml")
        patches: list[dict] = []
        for c in comps:
            meta = self.meta(c)
            if meta.get("bare_service"):
                ports = [{"name": "api", "port": meta["port"], "targetPort": meta["port"]}] + [{"name": n, "port": p, "targetPort": p} for n, p in meta["extra_ports"].items()]
                self.write(nsdir / f"{meta['service']}-service.yaml", dump({"apiVersion": "v1", "kind": "Service", "metadata": {"name": meta["service"]}, "spec": {"selector": {"app": meta["label"]}, "ports": ports}}))
                resources.append(f"{meta['service']}-service.yaml")
        secrets = self.secrets_at(stage)
        consumed = {x for w in sc.get("workloads", []) for x in w.get("secrets") or []}
        secrets = [t for t in secrets if t[2] not in self.catalog or self.home(t[2], stage) == ns or t[0] in consumed]
        aliases = [{"apiVersion": "v1", "kind": "Service", "metadata": {"name": svc, "labels": {"forjate.io/psa-exception": n}},
                    "spec": {"type": "ExternalName", "externalName": f"{svc}.{n}.svc.cluster.local"}}
                   for c, n in place.items() if c in everything for svc in self.services_of(c)]
        if aliases:
            self.write(nsdir / "aliases.yaml", f"# ExternalName aliases in {ns} for the Services the PSA exceptions run elsewhere (security: psa_exceptions).\n" + "---\n".join(dump(a) for a in aliases))
            resources.append("aliases.yaml")
        for sname, keys, origin in secrets:
            patches.append({"target": {"kind": "Secret", "name": sname}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {sname}\n"})
            self.write(nsdir / "secrets" / f"sealed-{sname}.yaml", self.sealed_placeholder(sname, keys))
            self.write(nsdir / "secrets" / f"{sname}.env.example", self.env_example(sname, keys, origin, stage="walk"))
            resources.append(f"secrets/sealed-{sname}.yaml")
        for c in comps:
            for ph in self.meta(c)["placeholders"]:
                if ph not in [s[0] for s in secrets]:
                    patches.append({"target": {"kind": "Secret", "name": ph}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {ph}\n"})
        self.write(nsdir / "netpols.yaml", self.netpols(stage, depth_note=""))
        doc = {"namespace": ns, "resources": resources, "patches": patches}
        for c in comps:
            meta = self.meta(c)
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

    def write_tenant_exceptions(self, k8s: Path, stage: str, place: dict[str, str], everything: list[str]) -> list[str]:
        """Tenant target: one namespace child per PSA exception namespace, with its components by SSH ref,
        their sealed Secrets and default-deny. The root composes it next to ./namespaces/uc-<name>."""
        out: list[str] = []
        entries = {e["namespace"]: e for e in self.psa_exceptions(stage)}
        by_ns: dict[str, list[str]] = {}
        for c in everything:
            if c in place:
                by_ns.setdefault(place[c], []).append(c)
        for n, cs in by_ns.items():
            e = entries[n]
            ndir = k8s / "namespaces" / n
            doc = {"apiVersion": "v1", "kind": "Namespace", "metadata": {
                "name": n, "labels": {"forjate.io/usecase": self.name, "forjate.io/psa-exception": "true", **self.psa_labels(e["level"])},
                "annotations": {"forjate.io/psa-exception-owner": e["owner"], "forjate.io/psa-exception-reason": e["reason"]}}}
            self.write(ndir / "namespace.yaml", dump(doc))
            res = ["namespace.yaml"] + [self.ssh_component(c) for c in cs]
            patches = []
            for c in cs:
                res += self.secret_files(ndir, n, c, "walk", "sealed-secrets")
                meta = self.meta(c)
                if meta.get("secret"):
                    patches.append({"target": {"kind": "Secret", "name": meta["secret"][0]}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {meta['secret'][0]}\n"})
                for ph in meta["placeholders"]:
                    if ph != (meta.get("secret") or ("",))[0]:
                        patches.append({"target": {"kind": "Secret", "name": ph}, "patch": f"$patch: delete\napiVersion: v1\nkind: Secret\nmetadata:\n  name: {ph}\n"})
            if self.setting("security", stage, "network_policy") == "default-deny":
                self.write(ndir / "netpols.yaml", self.exception_netpols(stage, n, cs))
                res.append("netpols.yaml")
            sub = {"namespace": n, "resources": res}
            if patches:
                sub["patches"] = patches
            config = [{"name": self.meta(c)["config"][0], "literals": self.meta(c)["config"][1], "options": {"disableNameSuffixHash": True}}
                      for c in cs if self.meta(c).get("config")]
            if config:
                sub["configMapGenerator"] = config
            self.write(ndir / "kustomization.yaml", f"# {n}: the PSA exceptions of {self.name} at {e['level']} (owner {e['owner']}: {e['reason']}).\n" + dump(sub))
            out.append(f"./namespaces/{n}")
        return out

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
        psa_rows = [(st, e) for st in self.in_scope for e in self.psa_exceptions(st)]
        if psa_rows:
            lines += ["", "## PSA exceptions", "",
                      f"`{self.ns}` enforces the security record's `psa_level` per stage and is never lowered; these namespaces run below it.", "",
                      "| Stage | Namespace | Level | Components | Owner | Reason |", "|---|---|---|---|---|---|"]
            lines += [f"| {st} | `{e['namespace']}` | {e['level']} | " + ", ".join(f"`{c}`" for c in e["components"]) + f" | {e['owner']} | {' '.join(str(e['reason']).split())} |" for st, e in psa_rows]
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
                  "- [x] from Walk: PSA labels (the use case's namespace at the stage's level, every other namespace at its own, the PSA exceptions in theirs), default-deny NetworkPolicies, the egress allow-list, sealed secrets replacing every generated Secret, the ArgoCD Application on a tag",
                  "- [ ] seal the real secrets with the recipe in each `.env.example` before the first Walk sync",
                  "- [ ] patch the hostnames (`*.example.com`) and the ArgoCD `targetRevision` to the release tag"]
        if self.notes:
            lines += ["", "## Assembly notes", ""] + [f"- {n}" for n in dict.fromkeys(self.notes)]
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
    for n in dict.fromkeys(asm.notes):
        print(f"note: {n}")
    print(f"assembled {asm.name} ({a.target}): {len(asm.written)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
