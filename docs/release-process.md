# Release Process

How to safely develop, test, and release changes in the forjate.

## The Problem

Tagging a release before validating it in a real cluster leads to a painful loop: tag → deploy → find bugs → fix → force-push tag. This document defines a process that avoids force-pushing tags entirely.

## Key Principle

This factory is abstract — each consumer picks their own combination of components. There is no single staging environment that can validate everything. Therefore, **consumers validate changes in their own clusters using pre-release tags** before the factory cuts a stable release.

---

## Two Deployment Flows

Consumers have two ways to deploy changes to their clusters. Both are valid and serve different purposes.

### Flow 1: Dev / Direct Apply (fast iteration)

For local development and testing — apply directly from your machine without waiting for git or ArgoCD. Ideal when iterating on factory rc tags or debugging.

```bash
# Build and apply directly to the cluster
kubectl kustomize k8s/ | kubectl --context <context> apply -f -
```

- Changes are **immediate** — no commit, no push, no ArgoCD wait
- ArgoCD will show the app as **OutOfSync** (that's fine, it's temporary)
- Once validated, commit to the repo and ArgoCD reconciles to match
- Use this when you're testing rc tags, debugging, or moving fast

### Flow 2: Release / GitOps (production path)

For stable releases — commit to the consumer repo, push, and let ArgoCD handle deployment.

```bash
# Update kustomization.yaml with the new tag
# Commit and push
git add -A && git commit -m "chore: bump factory to v1.8.0" && git push
```

- ArgoCD detects the change and applies it automatically
- Requires ArgoCD configured with **auto-sync**, **self-heal**, and **prune**
- This is the only path for production — never leave a cluster running on direct-apply state

### ArgoCD Configuration (consumer side)

Consumer ArgoCD apps should be configured with:

```yaml
syncPolicy:
  automated:
    selfHeal: true    # reverts manual changes to match git
    prune: true       # deletes resources removed from git
```

This means:
- **Auto-sync**: ArgoCD applies changes when it detects a new commit
- **Self-heal**: if someone `kubectl apply`s directly (Flow 1), ArgoCD will revert it to match git on the next sync cycle
- **Prune**: resources removed from kustomization are deleted from the cluster

**Important**: After testing with Flow 1, always commit the changes to git. Otherwise ArgoCD will revert your direct-apply changes on the next sync.

---

## Factory Release Process

### 1. Work on a feature branch

```bash
git checkout -b feat/monitoring/prometheus-grafana
# make changes, push branch
git push -u origin feat/monitoring/prometheus-grafana
```

### 2. Merge to main

Once the branch is ready and PR is approved:

```bash
git checkout main && git pull
git merge feat/monitoring/prometheus-grafana
git push
```

### 3. Tag a release candidate

```bash
git tag v1.8.0-rc.1
git push origin v1.8.0-rc.1
```

### 4. Consumer tests the rc

Update the consumer's `kustomization.yaml` to the rc tag:

```yaml
resources:
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/monitoring/prometheus?ref=v1.8.0-rc.1
```

Then test using **Flow 1** (direct apply) for fast iteration:

```bash
rm -rf ~/.cache/kustomize/    # clear cached remote refs
kubectl kustomize k8s/ | kubectl --context <context> apply -f -
```

### 5. Fix and iterate (if needed)

If the rc has bugs, fix on main in the factory and tag a new rc:

```bash
# fix the issue on main
git commit -m "fix(prometheus): correct scrape config path"
git push

# new release candidate
git tag v1.8.0-rc.2
git push origin v1.8.0-rc.2
```

Consumer updates `?ref=v1.8.0-rc.2`, clears cache, re-applies. Repeat until stable.

### 6. Tag the stable release

Once validated in a real cluster:

```bash
git tag v1.8.0
git push origin v1.8.0
```

The stable tag points to the **same commit** as the last validated rc.

### 7. Consumer pins to stable and commits (Flow 2)

```yaml
resources:
  - ssh://git@github.com/AItizate/forjate.git//k8s/components/apps/monitoring/prometheus?ref=v1.8.0
```

Commit and push. ArgoCD picks it up and deploys via the production path.

---

## Versioning

[Semantic Versioning](https://semver.org/):

- **PATCH** (v1.7.0 → v1.7.1): Bug fixes, no new features
- **MINOR** (v1.7.0 → v1.8.0): New components, non-breaking changes
- **MAJOR** (v1.7.0 → v2.0.0): Breaking changes requiring consumer updates
- **RC** (v1.8.0-rc.1, rc.2, ...): Pre-release candidates for validation

## Rules

1. **Never force-push a tag.** Tags are immutable. Fix forward with a new rc or patch.
2. **Never tag a stable release from untested code.** Always validate via at least one rc in a real cluster.
3. **Consumer repos pin to stable tags in production**, never to branches, `main`, or rc tags.
4. **RC tags are ephemeral.** Once a stable tag is cut, rc tags can be ignored.
5. **One rc series per minor/major.** Don't start `v1.9.0-rc.1` before `v1.8.0` is finalized.
6. **Always clear kustomize cache** (`rm -rf ~/.cache/kustomize/`) when switching between tags — kustomize aggressively caches remote git refs.
7. **Direct-apply (Flow 1) is temporary.** Always commit to git after validating, so ArgoCD stays in sync.

## Quick Reference

```bash
# --- Factory side ---
git tag v1.X.0-rc.1 && git push origin v1.X.0-rc.1    # tag rc
git tag v1.X.0 && git push origin v1.X.0                # tag stable
git tag --sort=-v:refname | head -10                     # list tags

# --- Consumer side (dev) ---
rm -rf ~/.cache/kustomize/                               # clear cache
kubectl kustomize k8s/ | kubectl --context im-u apply -f -  # direct apply

# --- Consumer side (release) ---
git add -A && git commit -m "chore: bump factory to v1.X.0" && git push  # ArgoCD deploys
```
