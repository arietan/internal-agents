# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| Latest on `main` | Yes |
| Older releases | Best effort |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly. **Do not open a public GitHub issue.**

### How to Report

1. **Email**: Send a detailed report to **security@`<YOUR_ORG_DOMAIN>`**.
2. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgement** within 48 hours of your report.
- **Assessment** within 7 business days. We will confirm whether the issue is accepted or rejected and provide an estimated timeline for a fix.
- **Fix and Disclosure** -- we aim to release a fix within 30 days for critical issues. We will coordinate with you on public disclosure timing.

### Scope

The following are in scope for security reports:

- **Agent code** (`agents/`) -- authentication bypass, privilege escalation, injection vulnerabilities
- **Audit trail integrity** -- hash chain tampering, record forgery
- **DLP bypass** -- PII/credential leakage past content filters
- **Secret exposure** -- credentials leaked in logs, audit records, or PR content
- **Infrastructure as Code** (`infra/terraform/`) -- insecure defaults, overly permissive IAM policies
- **Kubernetes manifests** (`k8s/`) -- RBAC escalation, insecure pod configurations
- **Supply chain** -- dependency vulnerabilities in `requirements*.txt`

### Out of Scope

- Vulnerabilities in upstream dependencies (report to the upstream project directly)
- Issues requiring physical access to the deployment environment
- Social engineering attacks

## Security Best Practices for Deployers

- Never commit `.env` files or cloud credentials to the repository.
- Use the provider allowlist (`APPROVED_PROVIDERS`) to restrict LLM backends.
- Enable the kill switch (`COMPLIANCE_KILL_SWITCH`) as an emergency stop.
- Rotate `GITHUB_TOKEN` and cloud credentials regularly.
- Use cloud-native secret management (Secrets Manager, Key Vault, Secret Manager) in production.
- Enable encryption at rest for audit storage (DynamoDB, Cosmos DB, Firestore, or K8s PV with encryption).
- Review all AI-generated PRs before merging -- never enable auto-merge.
- Restrict network access to LLM endpoints and observability services.
