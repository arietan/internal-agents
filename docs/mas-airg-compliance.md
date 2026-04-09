# MAS AIRG Compliance — Internal AI Agents

Reference: [MAS Guidelines on AI Risk Management (AIRG), Nov 2025](https://www.mas.gov.sg/-/media/mas-media-library/publications/consultations/bd/2025/final_consultation_paper_on_guidelines_on_ai_risk_management_forrelease.pdf)

---

## 1. Gap Analysis

### Current State vs MAS AIRG Requirements

| # | AIRG Domain | Current State | Gap | Priority |
|---|-------------|---------------|-----|----------|
| **G1** | **Board/Senior Management Oversight** | None — no governance structure defined | Need accountable executive, AI oversight committee, risk appetite statement | Critical |
| **G2** | **AI System Registry** | No inventory | Need registry of all AI systems with risk materiality assessment | Critical |
| **A1** | **Immutable Audit Trail** | Basic JSON logs to ephemeral `emptyDir` — lost on pod restart, no integrity checks | Need append-only persistent storage, cryptographic hashing, full I/O capture | Critical |
| **A2** | **Decision Validity Warrants** | `reasoning` field in audit but unstructured | Need structured DVW: facts, assumptions, data sources, logical chain | High |
| **H1** | **Human-in-the-Loop (HITL)** | PR body says "Human review required" — not enforced | Need mandatory approval gate, branch protection, escalation for high-risk | Critical |
| **H2** | **Kill Switch / Circuit Breaker** | None | Need ability to halt all agent operations immediately | Critical |
| **D1** | **Data Classification** | None — source code and LLM prompts flow without controls | Need data classification framework, PII/sensitive scanning before LLM calls | High |
| **D2** | **Data Retention** | Audit logs ephemeral, Langfuse traces indefinite | Need defined retention periods, secure deletion | Medium |
| **M1** | **Model Governance** | Uses alias `coding-model` — no version pinning or validation | Need model registry, version pinning, validation tests, change approval | High |
| **M2** | **Model Performance Monitoring** | LLM latency/error metrics exist | Need output quality monitoring, drift detection, periodic evaluation | Medium |
| **T1** | **Third-Party Risk** | Can fall back to Anthropic/OpenAI without controls | Need vendor risk assessment, data residency controls, external call gating | High |
| **S1** | **Security Hardening** | Webhook secret verification optional, no mTLS, no image signing | Need mandatory auth, mTLS, signed images, runtime security | High |
| **S2** | **Secret Management** | K8s Secrets (base64) — not encrypted at rest by default | Need external-secrets or sealed-secrets, rotation policy | Medium |
| **C1** | **Compliance Dashboard** | Grafana has operational metrics only | Need compliance-specific panels: audit completeness, HITL adherence, policy violations | Medium |
| **I1** | **Incident Response** | None | Need playbook, rollback procedure, communication plan | Medium |

---

## 2. Risk Materiality Assessment

Per MAS AIRG, risk materiality is assessed across three dimensions:

### 2.1 Impact
| Factor | Assessment | Rationale |
|--------|------------|-----------|
| Financial impact | Low | Agents modify internal code only; no direct customer/financial transactions |
| Operational impact | Medium | Faulty code could disrupt internal systems if merged without review |
| Reputational impact | Low–Medium | AI-generated code in production could raise questions if defects occur |

### 2.2 Complexity
| Factor | Assessment | Rationale |
|--------|------------|-----------|
| Model complexity | Medium | Uses pre-trained LLMs (opaque); agents have deterministic orchestration |
| Data complexity | Low–Medium | Input is source code + issue descriptions; output is code patches |
| Integration complexity | Medium | Interacts with GitHub API, K8s API, LLM endpoints |

### 2.3 Reliance
| Factor | Assessment | Rationale |
|--------|------------|-----------|
| Degree of automation | Medium | Creates PRs autonomously but requires human merge approval |
| Human override capability | High | PRs can be rejected, agent can be halted |
| Fallback availability | High | Manual coding replaces agent if disabled |

**Overall Risk Materiality: MEDIUM**

Controls should be applied proportionately — robust HITL, audit, and model governance are mandatory; advanced fairness/bias testing is lower priority for code generation.

---

## 3. Implementation Plan

### Phase 1 — Critical Controls (Weeks 1–3)

#### 1A. Immutable Audit Trail
- Persistent audit log storage (PVC or external log sink)
- Cryptographic hash chain (each record includes hash of previous)
- Full prompt/response capture (not truncated)
- Structured fields: run_id, timestamp, agent, model_version, input_hash, output_hash, decision, approver, human_action

#### 1B. Human-in-the-Loop Enforcement
- GitHub branch protection rules enforced via API
- Mandatory `ai-generated` label + `needs-human-review` status check
- Configurable risk thresholds: auto-flag high-risk changes for senior review
- PR merge blocked until human approves (enforced at GitHub level, not just advisory)

#### 1C. Kill Switch
- ConfigMap-based agent enable/disable flag
- K8s admission webhook or CronJob suspension
- `/circuit-breaker` endpoint on webhook listeners to halt processing
- Prometheus alert triggers automated suspension on error rate thresholds

#### 1D. AI System Registry
- `ai-registry.yaml` manifest documenting each agent, its purpose, risk assessment, accountable owner, model dependencies, data flows

### Phase 2 — High Priority Controls (Weeks 4–6)

#### 2A. Data Classification & DLP
- Pre-LLM prompt scanner for secrets, PII, credentials (regex + entropy checks)
- Data classification labels in audit records
- Configurable deny-list of file patterns excluded from LLM context

#### 2B. Model Governance
- Model version pinning in config (exact digest, not just tag)
- Model validation test suite (canary prompts with expected output patterns)
- Change approval workflow for model updates
- Model card documentation

#### 2C. Third-Party Risk Controls
- External LLM provider allow-list (block fallback to unapproved providers)
- Data residency enforcement — block external calls when data is classified
- Vendor risk assessment documentation per provider

#### 2D. Security Hardening
- Mandatory webhook secret verification (fail-closed)
- Pod security standards (restricted)
- Image signing with Cosign + admission controller
- Secret rotation via external-secrets-operator

### Phase 3 — Operational Maturity (Weeks 7–10)

#### 3A. Compliance Dashboard
- Grafana panels: audit trail completeness, HITL adherence rate, policy violations, model drift indicators
- Automated compliance reporting (weekly digest)

#### 3B. Incident Response
- Documented playbook for agent misbehaviour
- Automated rollback of recent agent PRs
- Alertmanager integration for compliance-critical alerts

#### 3C. Periodic Review
- Quarterly model evaluation and recalibration
- Annual risk materiality reassessment
- Penetration testing of agent infrastructure

---

## 4. Governance Structure

```
┌─────────────────────────────────────────────────────┐
│                   Board / ExCo                       │
│  Quarterly AI risk report   │   Risk appetite stmt   │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│         AI Oversight Committee                       │
│  Members: CTO, CISO, Head of Engineering, Head of   │
│           Risk, Compliance Officer                   │
│  Cadence: Monthly                                    │
│  Duties: Review AI registry, approve model changes,  │
│          review incidents, assess risk materiality    │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│     Accountable Executive: Head of Engineering       │
│  Duties: Day-to-day oversight, kill switch authority, │
│          incident escalation, audit review            │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│             Agent Operations Team                    │
│  Duties: Monitor dashboards, triage alerts,          │
│          execute model updates, maintain registry     │
└─────────────────────────────────────────────────────┘
```

---

## 5. Data Flow with Controls

```
  GitHub Issues/Roadmap
         │
         ▼
  ┌─── Coding Agent ──────────────────────────────────────┐
  │  1. Clone repo                                         │
  │  2. Gather context                                     │
  │  3. ⛔ DLP SCAN: check prompts for secrets/PII        │  ← Phase 2
  │  4. ⛔ KILL SWITCH CHECK                               │  ← Phase 1
  │  5. Call LLM (via LiteLLM → local Ollama)             │
  │  6. ✍️  FULL AUDIT: prompt hash, response hash,       │  ← Phase 1
  │        model version, timestamp, DVW                   │
  │  7. Parse plan, apply changes                          │
  │  8. Create PR with `ai-generated` + `needs-review`    │
  │  9. ⛔ BRANCH PROTECTION enforces human approval       │  ← Phase 1
  └────────────────────────────────────────────────────────┘
         │ PR opened
         ▼
  ┌─── PR Review Agent ───────────────────────────────────┐
  │  1. Fetch PR + diff                                    │
  │  2. ⛔ DLP SCAN: check diff for sensitive data        │  ← Phase 2
  │  3. Call LLM for review                                │
  │  4. ✍️  FULL AUDIT: review decision, risk level,      │  ← Phase 1
  │        recommended approver, model version             │
  │  5. Post structured review comment                     │
  │  6. Assign human reviewer                              │
  │  7. ⛔ Human must approve + merge (enforced)           │  ← Phase 1
  └────────────────────────────────────────────────────────┘
         │
         ▼
  ┌─── Immutable Audit Store ─────────────────────────────┐
  │  - Hash-chained JSON records                           │
  │  - Persistent volume (+ optional external sink)        │
  │  - Full prompt/response (encrypted at rest)            │
  │  - Retention: 7 years per MAS record-keeping           │
  └────────────────────────────────────────────────────────┘
```
