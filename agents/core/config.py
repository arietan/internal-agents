"""Abstract configuration loader interface."""

from abc import ABC, abstractmethod
from typing import Any


class ConfigLoader(ABC):
    """Cloud-agnostic interface for reading configuration.

    Local: reads env vars + YAML files on disk / K8s ConfigMaps.
    AWS: SSM Parameter Store (scalar) + S3 (YAML files).
    Azure: App Configuration (scalar) + Blob Storage (YAML).
    GCP: Firestore (scalar) + Secret Manager (YAML).
    """

    @abstractmethod
    def get_parameter(self, key: str) -> str:
        """Read a single config value (kill switch, feature flag, etc.).

        Args:
            key: Parameter name (e.g. "COMPLIANCE_KILL_SWITCH").

        Returns:
            The parameter value as a string, or empty string if not found.
        """
        ...

    @abstractmethod
    def load_yaml(self, name: str) -> dict:
        """Load a YAML config file by logical name.

        Args:
            name: Logical config name ("skills", "rules", "reviewers").

        Returns:
            Parsed YAML as a dict.
        """
        ...

    @abstractmethod
    def get_all(self) -> dict[str, Any]:
        """Return all configuration as a flat dict."""
        ...
