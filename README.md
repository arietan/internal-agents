# Internal AI Agents

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Terraform](https://img.shields.io/badge/terraform-%3E%3D1.5-purple.svg)](https://www.terraform.io/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-ready-326ce5.svg)](https://kubernetes.io/)

Autonomous AI agents that generate code, review pull requests, and self-heal production systems. Deploy anywhere -- local Kubernetes, managed K8s (EKS/AKS/GKE), or fully serverless on AWS, Azure, or GCP.

Every action produces a **hash-chained audit trail** aligned with [MAS AIRG](https://www.mas.gov.sg/regulation/explainers/artificial-intelligence-and-machine-learning) compliance requirements. All PRs require human approval before merge.

## What It Does

- **Coding Agent** -- Reads GitHub issues, clones the target repo, generates implementation changes via an LLM, and opens pull requests.
- **PR Review Agent** -- Analyses diffs with an LLM, posts structured code reviews with severity levels, and recommends the best human approver.
- **Self-Healing Pipeline** -- Monitors Prometheus, Loki, and Tempo for anomalies, diagnoses root causes via LLM, and creates fix PRs automatically.

```
Alert fires  -->  Alertmanager  -->  Alert Receiver  -->  GitHub Issue (ai-agent)
                                                               |
Telemetry Watcher  -->  Prom/Loki/Tempo  -->  LLM diagnosis  -->  GitHub Issue
                                                               |
                                                        Coding Agent  -->  Fix PR
                                                               |
                                                        PR Review Agent  -->  Review
                                                               |
                                                        Human reviews all PRs
```

## Deployment Options

| Option | Compute | LLM | IaC | Best For |
|---|---|---|---|---|
| **Local K8s** | K8s Jobs/CronJobs | Self-hosted (Ollama/vLLM) | Kustomize | Development, on-prem |
| **Cloud-Agnostic K8s** | EKS / AKS / GKE | Self-hosted (same stack) | Terraform + Kustomize | Portable production |
| **AWS-Native** | Lambda + Step Functions | Bedrock | Terraform | AWS-committed orgs |
| **Azure-Native** | Azure Functions + Durable Functions | Azure OpenAI | Terraform | Azure-committed orgs |
| **GCP-Native** | Cloud Functions + Cloud Workflows | Vertex AI | Terraform | GCP-committed orgs |

All five options share the same agent business logic through an [abstract interface layer](docs/architecture.md#abstraction-layer-agentscore) and a runtime factory (`CLOUD_PROVIDER=local|aws|azure|gcp`).

## Quick Start

### Prerequisites

- Python 3.12+
- Docker (with Kubernetes enabled) or minikube
- [Ollama](https://ollama.com) installed locally
- GitHub PAT with `repo` scope
- `kubectl`, `gh` CLI, `make`

### 1. Clone and configure

```bash
git clone https://github.com/<YOUR_ORG>/internal-agents.git
cd internal-agents
cp .env.example .env
# Edit .env -- set GITHUB_TOKEN and TARGET_REPO at minimum
```

### 2. Install dependencies

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Pull a model

```bash
ollama pull deepseek-coder-v2:latest
```

### 4a. Run locally (no K8s)

```bash
make run-coding-agent      # generates code + opens PR
make run-review-agent      # reviews the latest PR
make run-telemetry-watcher # one-shot telemetry diagnosis
```

### 4b. Deploy to local Kubernetes

```bash
make deploy-full           # observability + models + agents + self-healing
make model-pull MODEL=deepseek-coder-v2:latest
make verify                # check all pods are running
make obs-port-forward      # Grafana :3000, Prometheus :9090, Langfuse :3001
```

### 4c. Deploy to cloud

```bash
# AWS-native serverless
make tf-init  CLOUD=aws-native
make tf-plan  CLOUD=aws-native
make tf-apply CLOUD=aws-native

# Cloud-agnostic (managed K8s)
make tf-init  CLOUD=cloud-agnostic TF_VARS='-var cloud=eks'
make tf-apply CLOUD=cloud-agnostic TF_VARS='-var cloud=eks'
make deploy-eks

# Azure or GCP
make tf-apply CLOUD=azure-native
make tf-apply CLOUD=gcp-native
```

See `make help` for all available targets.

## Architecture

```
agents/
  core/                     # Abstract interfaces (LLM, Audit, Config, Secrets, DLP, Observability)
  backends/
    local/                  # Ollama, filesystem audit, OTel, regex DLP
    aws/                    # Bedrock, DynamoDB, CloudWatch, Guardrails
    azure/                  # Azure OpenAI, Cosmos DB, App Insights, Content Safety
    gcp/                    # Vertex AI, Firestore, Cloud Monitoring, Cloud DLP
  tools/                    # Portable functions (git ops, PR fetch, codebase analysis)
  handlers/                 # Serverless entry points (Lambda, Azure Functions, Cloud Functions)
  coding-agent/             # Coding agent logic
  pr-review-agent/          # PR review agent logic
  self-healing/             # Telemetry watcher + alert receiver

infra/terraform/
  aws-native/               # Lambda, Step Functions, EventBridge, Bedrock, DynamoDB
  azure-native/             # Azure Functions, Durable Functions, Event Grid, Cosmos DB
  gcp-native/               # Cloud Functions, Cloud Workflows, Eventarc, Firestore
  cloud-agnostic/           # EKS / AKS / GKE cluster provisioning only

k8s/
  base/                     # Kustomize base (agents, models, observability)
  overlays/
    local/                  # Docker Desktop / minikube patches
    eks/ aks/ gke/          # Cloud-agnostic K8s overlays (StorageClass, identity)
```

See [docs/architecture.md](docs/architecture.md) for the full architecture documentation with Mermaid diagrams.

## Compliance (MAS AIRG)

| Feature | Description |
|---|---|
| **Hash-chained audit trail** | Every event (run, LLM call, PR, review) is a JSON record linked by SHA-256 hash chains |
| **Decision Validity Warrant** | Structured capture of facts, assumptions, reasoning, confidence, and limitations |
| **Data Loss Prevention** | PII/credential scanning before all LLM calls (regex local, Bedrock Guardrails, AI Content Safety, Cloud DLP) |
| **Kill switch** | `COMPLIANCE_KILL_SWITCH=true` halts all agent operations immediately |
| **Provider allowlist** | `APPROVED_PROVIDERS` restricts which LLM backends agents can use |
| **Human-in-the-loop** | All PRs require human approval before merge |

## Observability

Two observability models, unified by the `ObservabilityProvider` interface:

**Portable K8s stack** (local + cloud-agnostic) -- OTel Collector, Prometheus, Grafana, Loki, Tempo, Langfuse, Alertmanager

**Cloud-native** (serverless deployments):
- AWS: CloudWatch EMF + X-Ray + Bedrock Model Invocation Logging
- Azure: Application Insights + Log Analytics + Azure Monitor
- GCP: Cloud Monitoring + Cloud Trace + Cloud Logging

## Configuration

All configuration flows through environment variables, set via `.env` (local), K8s ConfigMaps (K8s), or cloud-native config services.

| Variable | Default | Description |
|---|---|---|
| `CLOUD_PROVIDER` | `local` | Backend selection: `local`, `aws`, `azure`, `gcp` |
| `GITHUB_TOKEN` | -- | PAT with `repo` scope (required) |
| `TARGET_REPO` | -- | `owner/repo` to operate on (required) |
| `AI_PROVIDER` | `litellm` | LLM provider: `litellm`, `ollama`, `anthropic`, `openai` |
| `AI_MODEL` | `coding-model` | Model name or alias |
| `HEALING_ENABLED` | `true` | Enable the self-healing pipeline |
| `HEALING_CONFIDENCE_THRESHOLD` | `0.7` | Min LLM confidence to create a healing issue |
| `APPROVED_PROVIDERS` | `litellm,ollama,vllm` | Comma-separated LLM allowlist |
| `DRY_RUN` | `false` | Skip GitHub writes (useful for testing) |

See `.env.example` for the full list with inline documentation.

## Roadmap

| Phase | Status | Milestone |
|---|---|---|
| **0** -- Local Cluster | Done | Single-dev K8s, self-hosted Ollama, full compliance |
| **1** -- Self-Healing Pipeline | Done | Telemetry watcher, alert receiver, closed-loop fixes |
| **2** -- Multi-Cloud Deployment | Done | AWS/Azure/GCP native + cloud-agnostic K8s via Terraform |
| **3** -- Shared Cluster | Next | Multi-team RBAC, shared model pool, webhook routing |
| **4** -- Self-Service Platform | Planned | Team self-onboarding portal, agent marketplace |

See [ROADMAP.md](ROADMAP.md) for details and [docs/cloud-deployment-plan.md](docs/cloud-deployment-plan.md) for the cloud deployment plan.

## Contributing

We welcome contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding conventions, and the PR process.

## Security

If you discover a security vulnerability, please follow the responsible disclosure process described in [SECURITY.md](SECURITY.md). Do **not** open a public issue.

## License

This project is licensed under the Apache License 2.0 -- see the [LICENSE](LICENSE) file for details.
