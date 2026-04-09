"""Abstract secrets loader interface."""

from abc import ABC, abstractmethod


class SecretsLoader(ABC):
    """Cloud-agnostic interface for secret retrieval.

    Local: os.environ / .env file.
    AWS: Secrets Manager.
    Azure: Key Vault.
    GCP: Secret Manager.
    """

    @abstractmethod
    def get_secret(self, name: str) -> str:
        """Retrieve a secret value by name.

        Args:
            name: Secret identifier (e.g. "GITHUB_TOKEN").

        Returns:
            The secret value.

        Raises:
            KeyError: If the secret does not exist.
        """
        ...
