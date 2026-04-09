# Internal AI Agents — Team Deployment Roadmap

Scaling the coding agent and PR review agent from a single local cluster to
serving multiple teams across on-premises and cloud environments.

---

## Current State (Phase 0) — Single-Cluster Local

```
You (local K8s) ─► Coding Agent CronJob ─► GitHub PR
                  ─► PR Review Agent     ─► Review + Approver Recommendation
                  ─► Langfuse            ─► Observability
```

- Single namespace `ai-agents` on your local cluster
- Agents run as CronJobs and webhook-triggered Jobs
- Config via ConfigMaps, secrets via K8s Secrets
- LLM calls to hosted APIs (Anthropic / OpenAI) or local Ollama

---

## Phase 1 — Multi-Team on a Shared Cluster

**Goal:** Onboard 2-5 teams onto the same cluster with tenant isolation.

### Architecture

```
┌─────────────────────────────────────────────────┐
│  Shared K8s Cluster                             │
│  ┌──────────────┐  ┌──────────────┐             │
│  │ ns: team-a   │  │ ns: team-b   │  ...        │
│  │  coding-agent│  │  coding-agent│             │
│  │  review-agent│  │  review-agent│             │
│  └──────────────┘  └──────────────┘             │
│  ┌──────────────────────────────────┐           │
│  │ ns: ai-platform (shared)        │           │
│  │  Langfuse · Ollama · Kagent CRD │           │
│  └──────────────────────────────────┘           │
└─────────────────────────────────────────────────┘
```

### What to build

| Item | Description |
|------|-------------|
| **Namespace-per-team** | Each team gets its own namespace with dedicated ConfigMap (TARGET_REPO, RULES, REVIEWERS) |
| **Kustomize overlays** | `k8s/overlays/team-a/`, `k8s/overlays/team-b/` with team-specific patches |
| **ResourceQuotas** | Prevent any team from monopolizing cluster resources |
| **NetworkPolicies** | Isolate teams; only allow egress to GitHub, LLM APIs, and shared Langfuse |
| **Shared LLM gateway** | Deploy LiteLLM or OpenAI-compatible proxy in `ai-platform` namespace for unified model routing, rate limiting, and key management |
| **Self-hosted model (optional)** | Ollama / vLLM in `ai-platform` for cost control and data sovereignty |
| **Centralized Langfuse** | Single Langfuse instance with project-per-team for cost attribution |
| **Helm chart** | Package agents as a Helm chart for repeatable team onboarding |

### Effort: ~2-3 weeks

---

## Phase 2 — On-Premises (Production-Grade)

**Goal:** Air-gapped or on-prem deployment with enterprise controls.

### Option A: Bare-Metal / VMware K8s

```
┌──────────────────────────────────────────────┐
│  On-Prem Data Centre                         │
│  ┌────────────────────────┐                  │
│  │  K8s (RKE2 / Tanzu /  │                  │
│  │  OpenShift / k3s)      │                  │
│  │  ┌─────────┐ ┌───────┐│                  │
│  │  │ Agents  │ │Ollama ││  ◄─ GPU nodes   │
│  │  └─────────┘ │vLLM   ││    for local LLM │
│  │              └───────┘││                  │
│  │  ┌─────────────────┐  │                  │
│  │  │ GitLab (self-   │  │                  │
│  │  │ hosted) + CI/CD │  │                  │
│  │  └─────────────────┘  │                  │
│  └────────────────────────┘                  │
│  ┌────────────────────────┐                  │
│  │ Harbor (container      │                  │
│  │ registry)              │                  │
│  └────────────────────────┘                  │
└──────────────────────────────────────────────┘
```

| Component | On-Prem Choice | Notes |
|-----------|---------------|-------|
| **K8s distribution** | RKE2, k3s, OpenShift, Tanzu | RKE2/k3s for simplicity; OpenShift for enterprise compliance |
| **LLM** | Ollama + Qwen 2.5 Coder (32B), or vLLM + Llama 3.3 | Requires GPU nodes (NVIDIA A100/H100 or RTX 4090 for dev) |
| **Git platform** | GitLab Self-Managed or Gitea | Swap `gh` CLI calls → `glab` or GitLab API |
| **Container registry** | Harbor | Vulnerability scanning built in |
| **Secret management** | HashiCorp Vault + External Secrets Operator | Auto-sync secrets to K8s |
| **Observability** | Langfuse (self-hosted) + Prometheus + Grafana | Langfuse Helm chart available |
| **CI/CD** | GitLab CI or Argo Workflows | Trigger agents from pipeline events |
| **HITL approval** | Kubiya or custom Slack/Teams bot | Human-in-the-loop for PR merge gates |

### Key changes from Phase 0

1. **Replace GitHub-specific code** with an abstraction layer (`GitProvider` interface) supporting GitHub, GitLab, Bitbucket
2. **Deploy self-hosted LLM** — Ollama or vLLM with GPU scheduling (Karpenter or static GPU nodepool)
3. **LiteLLM proxy** — unified API gateway so agent code doesn't change per provider
4. **Sealed Secrets / Vault** — no plaintext secrets in manifests
5. **Ingress controller** — expose webhook endpoints via NGINX Ingress + cert-manager

### Effort: ~4-6 weeks

---

## Phase 3 — Cloud Deployment

**Goal:** Run on managed K8s in AWS, Azure, or GCP for teams that prefer cloud.

### Option B: AWS (EKS)

```
┌─────────────────────────────────────────────┐
│  AWS Account                                │
│  ┌──────────────┐  ┌───────────────────┐    │
│  │  EKS Cluster │  │ Amazon Bedrock    │    │
│  │  (Karpenter) │  │ (Claude / Llama)  │    │
│  │  ┌─────────┐ │  └───────────────────┘    │
│  │  │ Agents  │ │  ┌───────────────────┐    │
│  │  └─────────┘ │  │ CodeCommit / GH   │    │
│  └──────────────┘  └───────────────────┘    │
│  ┌──────────────┐  ┌───────────────────┐    │
│  │  ECR         │  │ Secrets Manager   │    │
│  └──────────────┘  └───────────────────┘    │
└─────────────────────────────────────────────┘
```

| Component | AWS Choice |
|-----------|-----------|
| K8s | EKS + Karpenter (auto GPU scaling) |
| LLM | Amazon Bedrock (Claude, Llama, Mistral) — no GPU management needed |
| Registry | ECR |
| Secrets | AWS Secrets Manager + External Secrets Operator |
| Ingress | AWS ALB Ingress Controller |
| IAM | IRSA (pod-level IAM roles) |
| Cost | Spot instances for agent Jobs, on-demand for webhooks |

### Option C: Azure (AKS)

| Component | Azure Choice |
|-----------|-------------|
| K8s | AKS + KEDA (event-driven scaling) |
| LLM | Azure OpenAI Service (GPT-4o, o1) |
| Registry | ACR |
| Secrets | Azure Key Vault + CSI driver |
| Ingress | Azure Application Gateway Ingress |
| IAM | Workload Identity |

### Option D: GCP (GKE)

| Component | GCP Choice |
|-----------|-----------|
| K8s | GKE Autopilot (fully managed node scaling) |
| LLM | Vertex AI (Gemini, Claude via Model Garden) |
| Registry | Artifact Registry |
| Secrets | Secret Manager + External Secrets |
| Ingress | GKE Gateway API |
| IAM | Workload Identity Federation |

### Cloud-agnostic approach (K8s-based)

Use the patterns from the existing `k8sacc-multicloud` framework:

1. **Kustomize overlays per cloud**: `k8s/overlays/aws/`, `k8s/overlays/azure/`, `k8s/overlays/gcp/`
2. **LiteLLM proxy** as the model gateway — agent code calls one endpoint, LiteLLM routes to the right provider
3. **External Secrets Operator** — one abstraction for AWS SM, Azure KV, GCP SM
4. **SkyPilot** — for workload portability and cost optimization across clouds

### Effort: ~3-4 weeks per cloud

---

## Phase 3 Alt — Cloud-Native Serverless (100% Managed)

**Goal:** Zero containers, zero K8s. Every component is a fully managed cloud service.

This replaces the K8s-based Phase 3 for teams that want to eliminate operational overhead entirely.

### Per-cloud service mapping

| Component | AWS | Azure | GCP |
|-----------|-----|-------|-----|
| **Workflow orchestration** | Step Functions | Durable Functions / Logic Apps | Cloud Workflows |
| **LLM inference** | Bedrock InvokeModel | Azure OpenAI Service | Vertex AI Gemini API |
| **Agent platform** | Bedrock Agents / AgentCore | Foundry Agent Service | Vertex AI Agent Engine |
| **DLP / content filter** | Bedrock Guardrails | AI Content Safety | DLP API + Vertex Safety Filters |
| **Knowledge / RAG** | Bedrock Knowledge Bases | Azure AI Search + Foundry | Vertex AI RAG Engine |
| **Event routing** | EventBridge | Event Grid + Azure Functions | Eventarc |
| **Serverless functions** | Lambda | Azure Functions | Cloud Functions / Cloud Run |
| **NoSQL audit store** | DynamoDB | Cosmos DB | Firestore |
| **Object storage** | S3 | Blob Storage | Cloud Storage |
| **Secrets** | Secrets Manager | Key Vault | Secret Manager |
| **Config / feature flags** | SSM Parameter Store | App Configuration | Runtime Configurator / Firestore |
| **Observability** | CloudWatch + X-Ray | Azure Monitor + App Insights | Cloud Monitoring + Cloud Trace |
| **Identity** | IAM roles | Entra ID + Managed Identity | IAM + Workload Identity |
| **IaC** | CDK | Bicep | Pulumi / Terraform |

### Architecture pattern (AWS example, same shape on Azure/GCP)

```
GitHub webhook
    │
    ▼
EventBridge (event bus + routing rules)
    │
    ├── PR opened / synchronize ──► Step Functions: pr-review-agent
    │                                  ├─ Lambda: fetch PR + diff
    │                                  ├─ Bedrock Guardrails: DLP scan
    │                                  ├─ Bedrock InvokeModel: review
    │                                  ├─ Lambda: post comment + assign
    │                                  └─ DynamoDB: audit record
    │
    └── PR merged / push ──────────► Step Functions: coding-agent
                                       ├─ Lambda: clone + analyze repo
                                       ├─ Bedrock Knowledge Base: load rules/skills
                                       ├─ Bedrock Guardrails: DLP scan
                                       ├─ Bedrock InvokeModel: generate code
                                       ├─ Lambda: apply changes + create PR
                                       └─ DynamoDB: audit record
```

### What gets removed (vs Phase 3 K8s approach)

- Dockerfile, Makefile, entire `k8s/` directory
- Flask webhook listeners
- OTel Collector, Prometheus, Grafana, Langfuse, Loki, Tempo
- Ollama, LiteLLM, vLLM
- Kagent CRDs
- `telemetry.py` (Step Functions auto-logs every state transition)

### Effort: ~4-5 weeks for first cloud, ~2-3 weeks for each additional

---

## Phase 3C — Cloud-Agnostic Abstraction Layer

**Goal:** Run the same agent codebase on any cloud (or multiple clouds simultaneously) with swappable backends.

This is an architecture layer that sits between the agents and cloud services, making the codebase portable.

### Abstraction interfaces to build

```
agents/
  core/
    llm.py               # LLM provider interface
    audit.py              # Audit storage interface
    config.py             # Config/secrets loader interface
    events.py             # Webhook/event interface
    observability.py      # Metrics/tracing interface

  backends/
    aws/
      llm_bedrock.py      # Bedrock InvokeModel
      audit_dynamodb.py    # DynamoDB hash-chained audit
      config_ssm_s3.py     # SSM + S3 config loader
      secrets_sm.py        # Secrets Manager
    azure/
      llm_aoai.py          # Azure OpenAI
      audit_cosmos.py      # Cosmos DB audit
      config_appconfig.py  # App Configuration
      secrets_keyvault.py  # Key Vault
    gcp/
      llm_vertex.py        # Vertex AI Gemini
      audit_firestore.py   # Firestore audit
      config_sm.py         # Secret Manager (config)
      secrets_sm.py        # Secret Manager (secrets)
    local/
      llm_ollama.py        # Ollama / LiteLLM (existing)
      audit_filesystem.py  # JSON files (existing)
      config_file.py       # YAML files (existing)
      secrets_env.py       # Environment variables (existing)
```

### Interface design

Each interface follows the same pattern — a thin abstract class with cloud-specific implementations:

```python
# agents/core/llm.py
class LLMProvider(ABC):
    @abstractmethod
    def call(self, system: str, prompt: str, model: str, max_tokens: int) -> str: ...

# agents/backends/aws/llm_bedrock.py
class BedrockProvider(LLMProvider):
    def call(self, system, prompt, model, max_tokens):
        resp = self.client.converse(modelId=model, ...)
        return resp["output"]["message"]["content"][0]["text"]

# agents/backends/azure/llm_aoai.py
class AzureOpenAIProvider(LLMProvider):
    def call(self, system, prompt, model, max_tokens):
        resp = self.client.chat.completions.create(model=model, ...)
        return resp.choices[0].message.content

# agents/backends/gcp/llm_vertex.py
class VertexProvider(LLMProvider):
    def call(self, system, prompt, model, max_tokens):
        resp = self.model.generate_content(...)
        return resp.text
```

### Factory pattern for backend selection

```python
# agents/core/factory.py
CLOUD = os.environ.get("CLOUD_PROVIDER", "local")  # aws | azure | gcp | local

def get_llm() -> LLMProvider:
    if CLOUD == "aws":    return BedrockProvider()
    if CLOUD == "azure":  return AzureOpenAIProvider()
    if CLOUD == "gcp":    return VertexProvider()
    return OllamaProvider()  # local fallback

def get_audit() -> AuditStore:
    if CLOUD == "aws":    return DynamoDBAudit()
    if CLOUD == "azure":  return CosmosAudit()
    if CLOUD == "gcp":    return FirestoreAudit()
    return FilesystemAudit()

# ... same for config, secrets, observability
```

### Workflow orchestration portability

Workflow orchestration is the hardest layer to abstract because each cloud uses a fundamentally different model:

| Cloud | Orchestration | Definition format |
|-------|---------------|-------------------|
| AWS | Step Functions | Amazon States Language (JSON) |
| Azure | Durable Functions | Python/C# code |
| GCP | Cloud Workflows | YAML |
| Local | Python `run()` / CronJob | Python code |

**Recommended approach:** Keep a single canonical workflow definition in the existing `agent.yaml` format and generate cloud-specific orchestration from it:

```
agents/coding-agent/agent.yaml  (canonical workflow spec)
    │
    ├── generate ──► infra/aws/coding-agent-sfn.asl.json     (Step Functions)
    ├── generate ──► infra/azure/coding-agent-durable.py      (Durable Functions)
    ├── generate ──► infra/gcp/coding-agent-workflow.yaml      (Cloud Workflows)
    └── existing ──► agents/coding-agent/coding_agent.py       (local Python)
```

### IaC for multi-cloud

Use **Pulumi** (Python) or **Terraform** instead of cloud-specific tools:

```
infra/
  pulumi/
    __main__.py           # Entry point
    config.py             # Cloud selection + shared config
    stacks/
      aws.py              # AWS resources (Step Functions, Lambda, DynamoDB, ...)
      azure.py            # Azure resources (Durable Functions, Cosmos DB, ...)
      gcp.py              # GCP resources (Cloud Workflows, Firestore, ...)
    shared/
      audit_table.py      # Abstract audit table (DynamoDB / Cosmos / Firestore)
      event_routing.py    # Abstract event bus (EventBridge / Event Grid / Eventarc)
```

Deploy with: `pulumi up --stack aws` or `pulumi up --stack azure` or `pulumi up --stack gcp`

### Effort: ~6-8 weeks (abstraction layer + first two cloud backends)

---

## Phase 4 — Platform Product (Serving All Teams)

**Goal:** Self-service platform where any team can onboard their repos.

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Agent Platform                                          │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────────┐  │
│  │ Control Plane        │  │ Data Plane (per-team)    │  │
│  │  - Admin UI / API    │  │  - Agent Jobs            │  │
│  │  - Team onboarding   │  │  - Webhook listeners     │  │
│  │  - Config management │  │  - Scoped secrets        │  │
│  │  - Audit dashboard   │  │  - Namespaced resources  │  │
│  │  - LLM gateway       │  │                          │  │
│  │  - Langfuse          │  │                          │  │
│  └──────────────────────┘  └──────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │ Self-Service API                                     ││
│  │  POST /teams/{id}/onboard  — register repo + config  ││
│  │  POST /teams/{id}/trigger  — manual agent run        ││
│  │  GET  /teams/{id}/runs     — audit trail             ││
│  │  GET  /teams/{id}/metrics  — usage + cost            ││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────┘
```

### New components to build

| Component | Purpose |
|-----------|---------|
| **Admin API** | REST/gRPC service for team onboarding, config CRUD, trigger management |
| **Admin UI** | Dashboard for monitoring agent runs, reviewing audit logs, managing teams |
| **Tenant controller** | K8s operator that provisions namespace + RBAC + config when a team is registered |
| **LLM gateway (LiteLLM)** | Centralized model routing, rate limiting, cost tracking per team |
| **Audit service** | Persist all agent decisions, LLM inputs/outputs, PR links for compliance |
| **Webhook router** | Single ingress endpoint that routes events to the correct team's agent |
| **Usage metering** | Track tokens consumed, PRs created, reviews completed per team per month |

### Effort: ~8-12 weeks

---

## Decision Matrix

| Criteria | On-Prem (Ph 2) | Cloud K8s (Ph 3) | Serverless (Ph 3 Alt) | Cloud-Agnostic (Ph 3C) | Platform (Ph 4) |
|----------|----------------|-------------------|----------------------|----------------------|-----------------|
| **Data sovereignty** | Full control | Depends on region | Depends on region | Best of all — choose per deployment | Depends on target |
| **GPU / self-hosted LLM** | You manage | Cloud handles | Cloud handles (no containers) | Cloud handles | Either |
| **Vendor lock-in** | None | Low (K8s portable) | High (cloud-specific services) | None (abstraction layer) | Depends on infra |
| **Time to deploy** | 4-6 weeks | 3-4 weeks | 4-5 weeks first cloud | 6-8 weeks (abstraction + 2 clouds) | 8-12 weeks |
| **Operational overhead** | High | Medium | Lowest (zero infra) | Low (per-cloud managed) | Medium |
| **Cost (5 teams)** | $$$ (hardware) | $$ (pay per use) | $ (true pay-per-invocation) | $$ (per cloud) | $$$$ (engineering) |
| **Cost (50 teams)** | $$$ (amortized) | $$$$ (linear) | $$ (serverless scales well) | $$ (per cloud) | $$ (amortized) |
| **Portability** | Low (hardware-bound) | Medium (K8s portable) | Low (per-cloud locked) | Highest | Medium |
| **Compliance** | Easiest (air-gapped) | Cloud security review | Cloud security review | Per-cloud review | Depends |
| **Best for** | Regulated / air-gapped | Cloud-native teams | Single-cloud-first, zero-ops | Multi-cloud orgs, avoid lock-in | Large eng orgs |

---

## Recommended Path

```
Phase 0 (now)       → Local cluster, prove the agents work
     │
Phase 1 (~3 wks)    → Multi-team on shared cluster, Helm chart
     │
     ├── Phase 2 (if regulated / on-prem required)
     │      → Self-hosted LLM, GitLab, Harbor, Vault
     │
     ├── Phase 3 (if cloud + K8s preferred)
     │      → EKS/AKS/GKE + Bedrock/Azure OpenAI/Vertex
     │
     ├── Phase 3 Alt (if cloud + zero-ops preferred)
     │      → 100% managed serverless (Step Functions / Durable Functions / Cloud Workflows)
     │      → No containers, no K8s, no self-hosted anything
     │
     └── Phase 3C (if multi-cloud / avoid lock-in)
            → Build abstraction layer (LLM, audit, config, secrets)
            → Deploy to any cloud with swappable backends
            → Use Pulumi/Terraform for multi-cloud IaC
            │
            Phase 4 (when > 10 teams)
               → Self-service platform with admin UI
```

### How to choose

- **Single cloud, want simplicity?** → Phase 3 Alt (serverless, lowest ops)
- **Single cloud, want K8s control?** → Phase 3 (K8s-based)
- **Multiple clouds or avoiding vendor lock-in?** → Phase 3C (abstraction layer)
- **Regulated / air-gapped?** → Phase 2 (on-prem)
- **Scaling to many teams?** → Any Phase 3 path → Phase 4

Phase 3C is compatible with both Phase 3 (K8s) and Phase 3 Alt (serverless) — the
abstraction layer works regardless of whether the cloud backend uses containers or
managed services.
