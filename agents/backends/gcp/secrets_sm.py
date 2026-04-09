"""GCP secrets backend — Secret Manager."""

import logging
import os

from agents.core.secrets import SecretsLoader

log = logging.getLogger("backends.gcp.secrets")


class SecretManagerLoader(SecretsLoader):
    """Retrieves secrets from GCP Secret Manager."""

    def __init__(self):
        self._project = os.environ.get("GCP_PROJECT", "")
        self._client = None

    def _get_client(self):
        if not self._client:
            from google.cloud import secretmanager
            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    def get_secret(self, name: str) -> str:
        secret_name = f"projects/{self._project}/secrets/{name}/versions/latest"
        try:
            response = self._get_client().access_secret_version(name=secret_name)
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            raise KeyError(f"Secret '{name}' not found in Secret Manager: {e}")
