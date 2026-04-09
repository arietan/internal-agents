"""Azure secrets backend — Key Vault."""

import logging
import os

from agents.core.secrets import SecretsLoader

log = logging.getLogger("backends.azure.secrets")


class KeyVaultLoader(SecretsLoader):
    """Retrieves secrets from Azure Key Vault using managed identity."""

    def __init__(self):
        self._vault_url = os.environ.get("KEY_VAULT_URL", "")
        self._client = None

    def _get_client(self):
        if not self._client:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            self._client = SecretClient(vault_url=self._vault_url, credential=DefaultAzureCredential())
        return self._client

    def get_secret(self, name: str) -> str:
        kv_name = name.replace("_", "-").lower()
        try:
            secret = self._get_client().get_secret(kv_name)
            return secret.value or ""
        except Exception as e:
            raise KeyError(f"Secret '{kv_name}' not found in Key Vault: {e}")
