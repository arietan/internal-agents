"""GCP config backend — Secret Manager (YAML) + Firestore (scalar config)."""

import logging
import os
from typing import Any

import yaml

from agents.core.config import ConfigLoader

log = logging.getLogger("backends.gcp.config")


class GcpConfigLoader(ConfigLoader):
    """Reads scalar config from Firestore and YAML from Secret Manager."""

    def __init__(self):
        self._project = os.environ.get("GCP_PROJECT", "")
        self._config_collection = os.environ.get("CONFIG_COLLECTION", "agent-config")
        self._db = None
        self._sm_client = None

    def _get_firestore(self):
        if not self._db:
            from google.cloud import firestore
            self._db = firestore.Client(project=self._project)
        return self._db

    def _get_secret_manager(self):
        if not self._sm_client:
            from google.cloud import secretmanager
            self._sm_client = secretmanager.SecretManagerServiceClient()
        return self._sm_client

    def get_parameter(self, key: str) -> str:
        try:
            doc = self._get_firestore().collection(self._config_collection).document(key).get()
            if doc.exists:
                return doc.to_dict().get("value", "")
        except Exception:
            pass
        return os.environ.get(key, "")

    def load_yaml(self, name: str) -> dict:
        secret_name = f"projects/{self._project}/secrets/agent-config-{name}/versions/latest"
        try:
            resp = self._get_secret_manager().access_secret_version(name=secret_name)
            data = yaml.safe_load(resp.payload.data.decode("UTF-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            log.warning("Config YAML not found in Secret Manager: %s", name)
            return {}

    def get_all(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            for doc in self._get_firestore().collection(self._config_collection).stream():
                data = doc.to_dict()
                result[doc.id] = data.get("value", data)
        except Exception as e:
            log.warning("Failed to read config collection: %s", e)
        return result
