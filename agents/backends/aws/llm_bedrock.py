"""AWS LLM backend — Amazon Bedrock Converse API."""

import json
import logging
import os
import time

import boto3

from agents.core.llm import LLMProvider, LLMResponse

log = logging.getLogger("backends.aws.llm")


class BedrockProvider(LLMProvider):
    """Calls Bedrock Converse API for Claude, Llama, Nova, Mistral, etc."""

    def __init__(self):
        region = os.environ.get("AWS_REGION", "us-east-1")
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._bedrock = boto3.client("bedrock", region_name=region)

    def call(self, system: str, prompt: str, model: str, max_tokens: int = 8192) -> LLMResponse:
        model_id = os.environ.get("BEDROCK_MODEL_ID", model)
        start = time.monotonic()

        resp = self._client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            system=[{"text": system}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
        )

        duration = time.monotonic() - start
        output = resp["output"]["message"]["content"][0]["text"]
        usage = resp.get("usage", {})

        return LLMResponse(
            text=output,
            model=model_id,
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            duration_s=duration,
            raw=resp,
        )

    def list_models(self) -> list[str]:
        resp = self._bedrock.list_foundation_models()
        return [m["modelId"] for m in resp.get("modelSummaries", [])]
