# `agentic-simple-workflow`

Reference overlay. See [`docs/overlays/agentic-simple-workflow.md`](../../../docs/overlays/agentic-simple-workflow.md) for the design.

## Before deploying

- Replace `ghcr.io/example/agent:latest` in `agent-deployment.yaml` with your own image.
- Create `secrets/agent.env` with your real values and uncomment the `secretGenerator` block in `kustomization.yaml`.
- Adjust the LLM backend (Ollama by default — swap for a remote LiteLLM gateway when you outgrow local inference).

## Build & deploy

```bash
kustomize build k8s/overlays/agentic-simple-workflow | kubectl apply -f -
```
