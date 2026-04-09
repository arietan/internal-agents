"""Azure LLM backend — Azure OpenAI Service."""

import logging
import os
import time

from agents.core.llm import LLMProvider, LLMResponse

log = logging.getLogger("backends.azure.llm")


class AzureOpenAIProvider(LLMProvider):
    """Calls Azure OpenAI Service via the openai Python SDK with Azure config."""

    def __init__(self):
        self._endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self._api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        self._api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        self._use_entra = os.environ.get("AZURE_OPENAI_USE_ENTRA", "false").lower() == "true"

    def _get_client(self):
        import openai

        if self._use_entra:
            from azure.identity import DefaultAzureCredential
            credential = DefaultAzureCredential()
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
            return openai.AzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=token.token,
                api_version=self._api_version,
            )
        return openai.AzureOpenAI(
            azure_endpoint=self._endpoint,
            api_key=self._api_key,
            api_version=self._api_version,
        )

    def call(self, system: str, prompt: str, model: str, max_tokens: int = 8192) -> LLMResponse:
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", model)
        client = self._get_client()
        start = time.monotonic()

        resp = client.chat.completions.create(
            model=deployment,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )

        duration = time.monotonic() - start
        usage = resp.usage
        return LLMResponse(
            text=resp.choices[0].message.content,
            model=deployment,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            duration_s=duration,
        )

    def list_models(self) -> list[str]:
        return [os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")]
