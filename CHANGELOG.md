# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **Multi-cloud deployment** -- AWS-native (Lambda + Step Functions + Bedrock), Azure-native (Functions + Durable Functions + Azure OpenAI), and GCP-native (Cloud Functions + Workflows + Vertex AI) via Terraform.
- **Cloud-agnostic K8s** -- Terraform modules and Kustomize overlays for EKS, AKS, and GKE.
- **Abstract interface layer** (`agents/core/`) with factory-pattern backend selection via `CLOUD_PROVIDER` env var.
- **Cloud backend implementations** (`agents/backends/{aws,azure,gcp}/`) for LLM, audit, config, secrets, content filter, and observability.
- **Serverless handlers** (`agents/handlers/{aws,azure,gcp}/`) for Lambda, Azure Functions, and Cloud Functions entry points.
- **Self-healing pipeline** -- telemetry watcher (CronJob) + alert receiver (Deployment) that diagnose production anomalies via LLM and create fix PRs autonomously.
- **Coding agent** -- reads GitHub issues, clones repos, generates code via LLM, and opens pull requests.
- **PR review agent** -- analyses diffs with LLM, posts structured reviews with severity levels, and recommends the best human approver.
- **MAS AIRG compliance** -- hash-chained audit trail, Decision Validity Warrants, DLP scanning, kill switch, provider allowlist, human-in-the-loop enforcement.
- **Observability** -- portable K8s stack (OTel Collector, Prometheus, Grafana, Loki, Tempo, Langfuse, Alertmanager) and cloud-native equivalents per provider.
- **Open source preparation** -- LICENSE (Apache 2.0), CONTRIBUTING.md, SECURITY.md, ROADMAP.md, GitHub issue/PR templates, CI workflow.
