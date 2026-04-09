"""
Runtime backend selection based on CLOUD_PROVIDER environment variable.

    CLOUD_PROVIDER=local  (default) — K8s-native: Ollama, filesystem audit, OTel
    CLOUD_PROVIDER=aws              — Bedrock, DynamoDB, CloudWatch
    CLOUD_PROVIDER=azure            — Azure OpenAI, Cosmos DB, Azure Monitor
    CLOUD_PROVIDER=gcp              — Vertex AI, Firestore, Cloud Monitoring

Cloud-agnostic K8s deployments (EKS/AKS/GKE) use the "local" backend because
the same open-source stack (Prometheus, Grafana, Loki, Tempo, Langfuse) runs as
K8s workloads regardless of which cloud hosts the cluster.
"""

import os
from functools import lru_cache

from agents.core.llm import LLMProvider
from agents.core.audit import AuditStore
from agents.core.config import ConfigLoader
from agents.core.secrets import SecretsLoader
from agents.core.content_filter import ContentFilter
from agents.core.observability import ObservabilityProvider

CLOUD = os.environ.get("CLOUD_PROVIDER", "local").lower()


@lru_cache(maxsize=1)
def get_llm() -> LLMProvider:
    if CLOUD == "aws":
        from agents.backends.aws.llm_bedrock import BedrockProvider
        return BedrockProvider()
    if CLOUD == "azure":
        from agents.backends.azure.llm_aoai import AzureOpenAIProvider
        return AzureOpenAIProvider()
    if CLOUD == "gcp":
        from agents.backends.gcp.llm_vertex import VertexProvider
        return VertexProvider()
    from agents.backends.local.llm_ollama import OllamaProvider
    return OllamaProvider()


@lru_cache(maxsize=1)
def get_audit() -> AuditStore:
    if CLOUD == "aws":
        from agents.backends.aws.audit_dynamodb import DynamoDBAudit
        return DynamoDBAudit()
    if CLOUD == "azure":
        from agents.backends.azure.audit_cosmos import CosmosAudit
        return CosmosAudit()
    if CLOUD == "gcp":
        from agents.backends.gcp.audit_firestore import FirestoreAudit
        return FirestoreAudit()
    from agents.backends.local.audit_filesystem import FilesystemAudit
    return FilesystemAudit()


@lru_cache(maxsize=1)
def get_config() -> ConfigLoader:
    if CLOUD == "aws":
        from agents.backends.aws.config_ssm_s3 import SsmS3ConfigLoader
        return SsmS3ConfigLoader()
    if CLOUD == "azure":
        from agents.backends.azure.config_appconfig import AppConfigLoader
        return AppConfigLoader()
    if CLOUD == "gcp":
        from agents.backends.gcp.config_sm import GcpConfigLoader
        return GcpConfigLoader()
    from agents.backends.local.config_file import FileConfigLoader
    return FileConfigLoader()


@lru_cache(maxsize=1)
def get_secrets() -> SecretsLoader:
    if CLOUD == "aws":
        from agents.backends.aws.secrets_sm import SecretsManagerLoader
        return SecretsManagerLoader()
    if CLOUD == "azure":
        from agents.backends.azure.secrets_keyvault import KeyVaultLoader
        return KeyVaultLoader()
    if CLOUD == "gcp":
        from agents.backends.gcp.secrets_sm import SecretManagerLoader
        return SecretManagerLoader()
    from agents.backends.local.secrets_env import EnvSecretsLoader
    return EnvSecretsLoader()


@lru_cache(maxsize=1)
def get_content_filter() -> ContentFilter:
    if CLOUD == "aws":
        from agents.backends.aws.filter_guardrails import GuardrailsFilter
        return GuardrailsFilter()
    if CLOUD == "azure":
        from agents.backends.azure.filter_content_safety import ContentSafetyFilter
        return ContentSafetyFilter()
    if CLOUD == "gcp":
        from agents.backends.gcp.filter_dlp import DlpFilter
        return DlpFilter()
    from agents.backends.local.filter_regex import RegexContentFilter
    return RegexContentFilter()


@lru_cache(maxsize=1)
def get_observability() -> ObservabilityProvider:
    if CLOUD == "aws":
        from agents.backends.aws.observability_cw import CloudWatchObservability
        return CloudWatchObservability()
    if CLOUD == "azure":
        from agents.backends.azure.observability_monitor import AzureMonitorObservability
        return AzureMonitorObservability()
    if CLOUD == "gcp":
        from agents.backends.gcp.observability_cm import CloudMonitoringObservability
        return CloudMonitoringObservability()
    from agents.backends.local.observability_otel import OtelObservability
    return OtelObservability()
