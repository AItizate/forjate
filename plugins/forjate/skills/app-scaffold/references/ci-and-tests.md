# Tests, Dockerfile and CI

## Tests

| Quality `test_pyramid` line | Files | Needs |
|-----------------------------|-------|-------|
| `unit:` | `tests/test_<topic>.py`: arithmetic, matching, routing, redaction, idempotency keys, tool argument schemas, the approval-token refusal, the escalation predicate, the allowed-field filter | nothing: pure functions, pydantic |
| `contract:` | `tests/test_contract.py`: every tool in the AI-engineering record has a module with the declared flags (reads `.builder/decisions/ai-engineering.yaml` when present); `scaffold.yaml` validates | pyyaml |
| `integration:` | not generated: it needs the environment; the README says how to run the tools against `ephemeral.sh up` | |
| `e2e:` | the verify Job | the cluster |
| evals | `tests/evals/test_golden_set.py` marked `@pytest.mark.eval`: the seed's items through the double, the thresholds from the quality record; `@pytest.mark.injection`: the injection items produce no tool call outside the allowed set; `@pytest.mark.redaction` when the record names redaction | the double |

`pyproject.toml` registers the markers and puts `pyyaml` in the `test` extra for the contract test; `python -m pytest -q` runs everything that needs no cluster and passes in a fresh virtualenv with `.[test]`. The gates runner's `app-tests`, `eval-regression`, `injection-suite` and `redaction-check` checks run these by marker.

## Dockerfile

```dockerfile
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY prompts ./prompts
RUN pip install --no-cache-dir .
USER app
# The Job or Deployment sets the command: ["python", "-m", "<pkg>.<module>"]
CMD ["python", "-c", "print('set a command: python -m <pkg>.<module>')"]
```

A tag on the base image, never `latest`; a non-root `USER`; nothing written outside `/tmp` at runtime (readOnlyRootFilesystem). `.dockerignore` excludes `tests/`, `.venv/`, `.github/`.

## Workflows

Three files, each a thin call to the shared templates (`plugins/forjate/skills/devops/references/ci-templates.md`). Inputs use the devops record's `image_registry` and the use case name as `repository_name`; the SHA is the tag.

```yaml
# .github/workflows/pr-validation.yml
name: PR validation
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]
jobs:
  conventional-commits:
    uses: AItizate/gh-actions-templates/.github/workflows/pr-validation-template.yml@v1
    with:
      require_conventional_commits: true
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e '.[test]' && python -m pytest -q
```

```yaml
# .github/workflows/build-push.yml
name: Build, scan, push and write back
on:
  push:
    branches: [main]
jobs:
  build-scan-push:
    uses: AItizate/gh-actions-templates/.github/workflows/build-push-generic-template.yml@v1
    with:
      branch: ${{ github.ref_name }}
      registry_url: ghcr.io                      # devops record: image_registry
      repository_name: <org>/<usecase>           # the image the overlay's images: block names
      image_tag: ${{ github.sha }}               # devops record: image_tag_policy sha
      docker_file: ./Dockerfile
    secrets:
      registry_username: ${{ github.actor }}
      registry_password: ${{ secrets.GITHUB_TOKEN }}
  write-back:
    needs: build-scan-push
    runs-on: ubuntu-latest
    steps:
      - name: Dispatch app-image-updated to the IaC repo
        uses: peter-evans/repository-dispatch@v3
        with:
          token: ${{ secrets.IAC_FACTORY_TOKEN }}
          repository: <org>/<iac-repo>
          event-type: app-image-updated
          client-payload: '{"app_name": "<usecase>", "new_tag": "${{ github.sha }}", "tenant": "<tenant>", "namespace": "uc-<usecase>"}'
  notify-on-failure:
    needs: [build-scan-push, write-back]
    if: always() && contains(needs.*.result, 'failure')
    uses: AItizate/gh-actions-templates/.github/workflows/webhook-notification-template.yml@v1
    with:
      repository: ${{ github.repository }}
      ref: ${{ github.ref }}
      run_id: ${{ github.run_id }}
      server_url: ${{ github.server_url }}
    secrets:
      NOTIFY_WEBHOOK_URL: ${{ secrets.NOTIFY_WEBHOOK_URL }}
```

```yaml
# .github/workflows/release.yml
name: Release tag
on:
  push:
    branches: [main]
    paths: [pyproject.toml]
jobs:
  version:
    runs-on: ubuntu-latest
    outputs: { version: "${{ steps.v.outputs.version }}" }
    steps:
      - uses: actions/checkout@v4
      - id: v
        run: echo "version=$(python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")" >> "$GITHUB_OUTPUT"
  tag:
    needs: version
    uses: AItizate/gh-actions-templates/.github/workflows/release-tag-template.yml@v1
    with:
      version: ${{ needs.version.outputs.version }}
```

What is never in a generated workflow: `docker/build-push-action`, `docker build`, `docker push`, `trivy` invoked by hand, `@main` on a template. The templates' Trivy scan is the image-scan gate; the write-back is `repository_dispatch` into the IaC repo's `sync-app-image.yml`, which edits `images:` with `yq`. `scaffold-check.py` enforces all of it.

## README

In the brief's language: what the app is (one paragraph from the brief's problem), the workloads and their commands, how to run the tests, how Crawl runs it (`ephemeral.sh up <usecase>` builds `<usecase>:dev` from `spec.build` and imports it; `MODEL_MODE=replay` in CI, the `live` command for the demo), how Walk builds it (the template, the SHA, the dispatch), what the scaffold refused or assumed (`scaffold.yaml` `notes`).
