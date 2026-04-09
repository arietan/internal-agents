---
name: Bug Report
about: Report a bug to help us improve
title: "[bug] "
labels: bug
assignees: ""
---

## Describe the Bug

A clear description of what the bug is.

## Steps to Reproduce

1. Set `CLOUD_PROVIDER=...`
2. Run `make ...`
3. See error

## Expected Behaviour

What you expected to happen.

## Actual Behaviour

What actually happened. Include logs, error messages, or screenshots if applicable.

## Environment

- **Deployment**: local K8s / EKS / AKS / GKE / AWS-native / Azure-native / GCP-native
- **Python version**: 3.12.x
- **LLM provider**: Ollama / LiteLLM / Bedrock / Azure OpenAI / Vertex AI
- **Model**: e.g. `deepseek-coder-v2:latest`
- **OS**: e.g. macOS 15, Ubuntu 24.04

## Additional Context

Any other context about the problem (config snippets, audit logs, etc.).
Do **not** include secrets, tokens, or credentials.
