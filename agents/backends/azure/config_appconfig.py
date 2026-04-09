"""Azure config backend — App Configuration (scalar) + Blob Storage (YAML)."""

import logging
import os
from typing import Any

import yaml

from agents.core.config import ConfigLoader

log = logging.getLogger("backends.azure.config")


class AppConfigLoader(ConfigLoader):
    """Reads scalar config from Azure App Configuration and YAML from Blob Storage."""

    def __init__(self):
        self._appconfig_endpoint = os.environ.get("APPCONFIG_ENDPOINT", "")
        self._storage_account = os.environ.get("CONFIG_STORAGE_ACCOUNT", "")
        self._container_name = os.environ.get("CONFIG_CONTAINER", "agent-config")
        self._label = os.environ.get("APPCONFIG_LABEL", "production")
        self._appconfig_client = None
        self._blob_service = None

    def _get_appconfig(self):
        if not self._appconfig_client:
            from azure.appconfiguration import AzureAppConfigurationClient
            from azure.identity import DefaultAzureCredential
            self._appconfig_client = AzureAppConfigurationClient(
                base_url=self._appconfig_endpoint,
                credential=DefaultAzureCredential(),
            )
        return self._appconfig_client

    def _get_blob_service(self):
        if not self._blob_service:
            from azure.storage.blob import BlobServiceClient
            from azure.identity import DefaultAzureCredential
            account_url = f"https://{self._storage_account}.blob.core.windows.net"
            self._blob_service = BlobServiceClient(account_url, credential=DefaultAzureCredential())
        return self._blob_service

    def get_parameter(self, key: str) -> str:
        try:
            setting = self._get_appconfig().get_configuration_setting(key=key, label=self._label)
            return setting.value or ""
        except Exception:
            return os.environ.get(key, "")

    def load_yaml(self, name: str) -> dict:
        blob_name = f"config/{name}.yaml"
        try:
            blob_client = self._get_blob_service().get_blob_client(self._container_name, blob_name)
            data = yaml.safe_load(blob_client.download_blob().readall().decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            log.warning("Blob config not found: %s/%s", self._container_name, blob_name)
            return {}

    def get_all(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            for setting in self._get_appconfig().list_configuration_settings(label_filter=self._label):
                result[setting.key] = setting.value
        except Exception as e:
            log.warning("Failed to list App Configuration settings: %s", e)
        return result
