"""AWS secrets backend — Secrets Manager."""

import json
import logging
import os

import boto3

from agents.core.secrets import SecretsLoader

log = logging.getLogger("backends.aws.secrets")


class SecretsManagerLoader(SecretsLoader):
    """Retrieves secrets from AWS Secrets Manager."""

    def __init__(self):
        region = os.environ.get("AWS_REGION", "us-east-1")
        self._client = boto3.client("secretsmanager", region_name=region)
        self._prefix = os.environ.get("SECRETS_PREFIX", "internal-agents/")

    def get_secret(self, name: str) -> str:
        secret_id = f"{self._prefix}{name}"
        try:
            resp = self._client.get_secret_value(SecretId=secret_id)
            secret_string = resp.get("SecretString", "")
            try:
                data = json.loads(secret_string)
                return data.get(name, secret_string)
            except (json.JSONDecodeError, TypeError):
                return secret_string
        except self._client.exceptions.ResourceNotFoundException:
            raise KeyError(f"Secret '{secret_id}' not found in Secrets Manager")
