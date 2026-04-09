"""AWS config backend — SSM Parameter Store (scalar) + S3 (YAML files)."""

import logging
import os
from typing import Any

import boto3
import yaml

from agents.core.config import ConfigLoader

log = logging.getLogger("backends.aws.config")


class SsmS3ConfigLoader(ConfigLoader):
    """Reads scalar config from SSM Parameter Store and YAML from S3."""

    def __init__(self):
        region = os.environ.get("AWS_REGION", "us-east-1")
        self._ssm = boto3.client("ssm", region_name=region)
        self._s3 = boto3.client("s3", region_name=region)
        self._prefix = os.environ.get("SSM_PREFIX", "/internal-agents/")
        self._bucket = os.environ.get("CONFIG_BUCKET", "internal-agents-config")

    def get_parameter(self, key: str) -> str:
        try:
            resp = self._ssm.get_parameter(Name=f"{self._prefix}{key}", WithDecryption=True)
            return resp["Parameter"]["Value"]
        except self._ssm.exceptions.ParameterNotFound:
            return os.environ.get(key, "")

    def load_yaml(self, name: str) -> dict:
        s3_key = f"config/{name}.yaml"
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=s3_key)
            data = yaml.safe_load(resp["Body"].read().decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except self._s3.exceptions.NoSuchKey:
            log.warning("S3 config not found: s3://%s/%s", self._bucket, s3_key)
            return {}

    def get_all(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        paginator = self._ssm.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(Path=self._prefix, Recursive=True, WithDecryption=True):
            for param in page.get("Parameters", []):
                key = param["Name"].removeprefix(self._prefix)
                result[key] = param["Value"]
        return result
