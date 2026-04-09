"""Local secrets backend — reads from environment variables / .env file."""

import os

from agents.core.secrets import SecretsLoader


class EnvSecretsLoader(SecretsLoader):
    """Retrieves secrets from environment variables."""

    def get_secret(self, name: str) -> str:
        value = os.environ.get(name, "")
        if not value:
            raise KeyError(f"Secret '{name}' not found in environment")
        return value
