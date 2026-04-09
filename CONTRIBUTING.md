# Contributing to Internal AI Agents

Thank you for your interest in contributing. This guide covers development setup, codebase conventions, and how to land changes.

## Table of Contents

- [Development Setup](#development-setup)
- [Codebase Overview](#codebase-overview)
- [Architecture Patterns](#architecture-patterns)
- [Conventions](#conventions)
- [Testing](#testing)
- [Making Changes](#making-changes)
- [Areas Open for Contribution](#areas-open-for-contribution)

## Development Setup

### System dependencies

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Agent runtime |
| Docker Desktop | latest | Container builds, local K8s |
| kubectl | latest | Cluster management |
| gh | latest | GitHub CLI (used by agents at runtime) |
| Ollama | latest | Self-hosted LLM inference |
| make | any | Task runner |
| Terraform | >= 1.5 | Cloud infrastructure provisioning (optional) |

Enable Kubernetes in Docker Desktop (Settings > Kubernetes > Enable).

### Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate

# Core dependencies
pip install -r requirements.txt

# Cloud-specific (pick one, or install all for development)
pip install -r requirements-aws.txt
pip install -r requirements-azure.txt
pip install -r requirements-gcp.txt
```

### Environment variables

```bash
cp .env.example .env
```

Set at minimum:

- `GITHUB_TOKEN` -- a PAT with `repo` scope
- `TARGET_REPO` -- an `owner/repo` you own (use a throwaway repo for testing)

For local-only runs (no K8s), also set:

```bash
AI_PROVIDER=ollama
AI_MODEL=deepseek-coder-v2:latest
AI_BASE_URL=http://localhost:11434/v1
OTEL_ENABLED=false
```

### Pull a model

```bash
ollama pull deepseek-coder-v2:latest
# or for lighter testing:
ollama pull qwen2.5-coder:1.5b
```

### Run locally

```bash
make run-coding-agent       # picks up issues, generates code, opens PRs
make run-review-agent       # reviews the latest open PR
make run-telemetry-watcher  # one-shot: queries telemetry, creates issues
make run-alert-receiver     # starts alert webhook server on :8082
```

Add `DRY_RUN=true` to your `.env` to skip GitHub writes during development.

### Run on local K8s

```bash
make deploy-full          # builds images + deploys entire stack
make verify               # check all pods are running
make obs-port-forward     # access Grafana, Prometheus, Langfuse
```

## Codebase Overview

### Where things live

| Path | Purpose |
|---|---|
| `agents/core/` | Abstract interfaces (`LLMProvider`, `AuditStore`, `ConfigLoader`, `SecretsLoader`, `ContentFilter`, `ObservabilityProvider`) and `factory.py` for runtime backend selection |
| `agents/backends/{local,aws,azure,gcp}/` | Concrete implementations of each interface per cloud provider |
| `agents/tools/` | Portable, cloud-agnostic tool functions (git ops, PR fetch, codebase analysis, audit writing) |
| `agents/handlers/{aws,azure,gcp}/` | Serverless function entry points (Lambda handler, Azure function_app, Cloud Function) |
| `agents/coding-agent/` | Coding agent logic + webhook listener |
| `agents/pr-review-agent/` | PR review agent logic + webhook listener |
| `agents/self-healing/` | Telemetry watcher (CronJob) + alert receiver (Deployment) |
| `agents/compliance.py` | Audit trail, DLP, kill switch, DVW -- delegates to `agents/core/` |
| `agents/telemetry.py` | OTel tracing + metrics facade -- delegates to `agents/core/` |
| `k8s/base/` | Kustomize base manifests (agents, models, observability) |
| `k8s/overlays/{local,eks,aks,gke}/` | Environment-specific Kustomize overlays |
| `infra/terraform/{aws,azure,gcp}-native/` | Terraform for cloud-native serverless infrastructure |
| `infra/terraform/cloud-agnostic/` | Terraform for managed K8s clusters (EKS/AKS/GKE) |
| `docs/` | Architecture docs, deployment plans, compliance mapping |

### How the code flows

```
coding_agent.py
  |-- Config (from env vars / ConfigLoader)
  |-- Clone repo (gh CLI / github_clone tool)
  |-- Gather context (GitHub issues / roadmap / manual)
  |-- Analyze codebase (codebase_analyzer tool)
  |-- get_content_filter().scan()               <-- DLP via factory
  |-- get_config().get_parameter("kill_switch") <-- kill switch via factory
  |-- get_llm().call(system, prompt, model)     <-- LLM via factory
  |-- get_audit().write_record(record)          <-- audit via factory
  |-- parse_plan() -> JSON with branch, files, commit msg
  |-- apply_changes() -> write files to disk
  |-- create_pr() -> git commit, push, gh pr create
  '-- get_audit().write_record(record)          <-- audit via factory
```

The `factory.py` module reads `CLOUD_PROVIDER` env var and returns the appropriate backend:
- `local` -- Ollama, filesystem audit, regex DLP, OTel
- `aws` -- Bedrock, DynamoDB, Guardrails, CloudWatch
- `azure` -- Azure OpenAI, Cosmos DB, Content Safety, App Insights
- `gcp` -- Vertex AI, Firestore, Cloud DLP, Cloud Monitoring

## Architecture Patterns

### Adding a new cloud backend

1. Create `agents/backends/yourcloud/` with implementations for each interface:
   - `llm_*.py` implementing `LLMProvider`
   - `audit_*.py` implementing `AuditStore`
   - `config_*.py` implementing `ConfigLoader`
   - `secrets_*.py` implementing `SecretsLoader`
   - `filter_*.py` implementing `ContentFilter`
   - `observability_*.py` implementing `ObservabilityProvider`
2. Add the cloud key to `factory.py` dispatch (follow the existing `if CLOUD == "aws":` pattern).
3. Create `requirements-yourcloud.txt` for the SDK dependencies.
4. If the cloud has a serverless model, add a handler in `agents/handlers/yourcloud/`.
5. Add Terraform modules in `infra/terraform/yourcloud-native/`.
6. Update `docs/architecture.md` with the new option.

### Adding a new agent

1. Create `agents/your-agent/your_agent.py` with a `Config` dataclass and a `run()` function.
2. Import and use `compliance.py` for audit + DLP and `telemetry.py` for tracing (these delegate to the correct backend automatically).
3. Add a Dockerfile stage in `Dockerfile`.
4. Create K8s manifests (Deployment or CronJob) under `agents/your-agent/`.
5. Register the manifests in `k8s/base/kustomization.yaml`.
6. Add Make targets for running locally and building.

### Adding a new tool function

1. Create `agents/tools/your_tool.py` with pure Python functions.
2. Keep functions cloud-agnostic -- use `agents.core.factory` if you need backend services.
3. Export from `agents/tools/__init__.py`.

### Adding a new LLM provider (within a backend)

1. Implement the `LLMProvider` ABC (see `agents/core/llm.py`).
2. Add a dispatch entry in `factory.py` for the appropriate `CLOUD_PROVIDER` value.
3. Add the provider to `APPROVED_PROVIDERS` in the configmap.
4. Update `.env.example` with any new env vars the provider needs.

## Conventions

### Python

- **Type hints** on all public function signatures.
- **Dataclasses** for configuration (`Config`) -- no global mutable state.
- **Logging** via `logging.getLogger("agent-name")` -- never `print()`.
- Functions should be < 50 lines. Break large functions into well-named helpers.
- Errors must be handled explicitly -- never bare `except:`.
- All backend classes must inherit from the appropriate ABC in `agents/core/`.

### Git

- **Conventional commits**: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
- **Branch names**: `feature/short-description`, `fix/short-description`, `chore/short-description`.
- One logical change per commit. Squash messy WIP before opening a PR.
- **Sign your commits** if possible (`git commit -s`).

### Kubernetes manifests

- All resources must carry `app.kubernetes.io/part-of: internal-agents`.
- Use `kustomize` for environment-specific changes (overlays), not inline conditionals.
- Secrets go in `agent-secrets` -- never hardcode values in manifests.
- Resource requests/limits are required for all containers.

### Terraform

- Use modules for logical groupings (e.g., `foundation`, `lambdas`, `observability`).
- All resources must be tagged with `project = "internal-agents"` and `managed_by = "terraform"`.
- Use `variables.tf` for all configurable values; avoid hardcoding.
- Lock provider versions in the root module.

### Configuration

- All agent config flows through environment variables.
- K8s: set values in `k8s/base/configmap.yaml` (non-sensitive) or `agent-secrets` (sensitive).
- Local: set values in `.env`. Never commit `.env`.
- New config values must also be added to `.env.example` with a comment.

## Testing

```bash
make test    # runs pytest
make lint    # validates YAML + compiles Python
```

Priorities for test contributions:

1. **Unit tests for `agents/core/`** -- verify factory dispatch, audit hash chaining, content filter patterns.
2. **Unit tests for `compliance.py`** -- audit chain integrity, DLP pattern matching, kill switch logic.
3. **Unit tests for plan parsing** -- `parse_plan()` in both agents with various LLM output formats.
4. **Backend tests** -- mock cloud SDKs (boto3, azure-*, google-cloud-*) and verify backend implementations.
5. **Integration tests** -- mock the GitHub API and LLM endpoints, verify end-to-end flow.
6. **Terraform validation** -- `terraform validate` and `terraform plan` for each infrastructure module.

Use `DRY_RUN=true` when testing against real repos to avoid creating PRs.

## Making Changes

### Small changes (bug fixes, config tweaks)

1. Fork the repository and create a branch: `git checkout -b fix/description`.
2. Make changes. Run `make lint`.
3. Commit with a conventional message: `git commit -m "fix: description"`.
4. Open a PR against `main`.

### Larger changes (new features, new agents, new backends)

1. **Open an issue first** describing what you want to build and why.
2. Fork the repository and create a branch: `git checkout -b feature/description`.
3. Develop incrementally. Keep commits focused.
4. Add or update relevant configs if your feature introduces new env vars.
5. Test locally with `make run-coding-agent` or the appropriate target.
6. If you added K8s resources, test with `make deploy-full && make verify`.
7. If you added Terraform, validate with `make tf-init CLOUD=yourcloud && make tf-plan CLOUD=yourcloud`.
8. Open a PR. Include in the description:
   - What changed and why.
   - How you tested it.
   - Any new env vars or config changes.
   - Which deployment options are affected.

### What makes a good PR

- Focused scope -- one logical change per PR.
- Tests for new logic (especially in `agents/core/` and `compliance.py`).
- Updated `.env.example` if new env vars were added.
- No secrets, tokens, or credentials in the diff.
- YAML manifests validated (`make lint`).
- Terraform validated (`terraform validate`) if infrastructure was changed.
- Documentation updated if behaviour changed.

## Debugging

### Agent fails with LLM errors

- Check the model is loaded: `ollama list` or `make model-list`.
- Check LiteLLM is running: `make litellm-test`.
- Small models (1.5B) often produce invalid JSON. Use 7B+ for reliable structured output.
- Set `DRY_RUN=true` to test everything except the GitHub write.

### Pods stuck in CrashLoopBackOff

```bash
kubectl -n ai-agents logs deploy/coding-agent-webhook --previous
kubectl -n ai-agents describe pod <pod-name>
```

Common causes: missing secrets, wrong image tag, OOM (bump resource limits in the overlay).

### Audit trail issues

Audit records are written via the `AuditStore` backend. For local runs, records go to `/var/log/agent-audit/` (override with `AUDIT_LOG_DIR`). Verify chain integrity:

```python
from agents.core.factory import get_audit
get_audit().verify_chain()
```

### Terraform issues

```bash
cd infra/terraform/<cloud>
terraform init
terraform validate
terraform plan -var-file=terraform.tfvars
```

### Self-healing pipeline not creating issues

- Check `HEALING_ENABLED=true` is set.
- Verify alerts are firing in Prometheus.
- If confidence is below the threshold (default 0.7), lower `HEALING_CONFIDENCE_THRESHOLD` for testing.
- Check `HEALING_COOLDOWN_MINUTES` -- the watcher deduplicates issues within this window.

```bash
make healing-status    # check CronJob and alert receiver
make healing-logs      # tail latest watcher job + receiver logs
make healing-test      # manually trigger a watcher run
```

## Areas Open for Contribution

Ordered by impact:

1. **Test suite** -- unit tests for `agents/core/`, `compliance.py`, `parse_plan()`, backend mocks.
2. **Retry logic** -- small models produce invalid JSON; add retry + fallback parsing in `parse_plan()`.
3. **Helm chart** -- package the Kustomize manifests as a Helm chart for broader adoption.
4. **Additional cloud backends** -- Oracle Cloud, IBM Cloud, or other providers.
5. **Multi-repo support** -- allow agents to operate across multiple target repositories.
6. **Self-healing accuracy** -- improve telemetry watcher diagnosis prompts, add per-alert-type templates.
7. **Runbook integration** -- let the telemetry watcher cross-reference runbooks for better diagnosis.
8. **Webhook signature verification** -- harden HMAC validation in `webhook_listener.py` files.
9. **Cost dashboards** -- Grafana dashboards for FinOps tracking across deployment options.
10. **CI/CD pipeline** -- GitHub Actions for lint, test, Terraform validate, Docker build.
