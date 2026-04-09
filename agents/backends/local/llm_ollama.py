"""Local LLM backend — Ollama / LiteLLM / vLLM / Anthropic / OpenAI."""

import logging
import os
import time

from agents.core.llm import LLMProvider, LLMResponse

log = logging.getLogger("backends.local.llm")


class OllamaProvider(LLMProvider):
    """OpenAI-compatible local provider dispatching to LiteLLM, Ollama,
    vLLM, or cloud SDKs based on ``AI_PROVIDER`` env var."""

    def __init__(self):
        self.provider = os.environ.get("AI_PROVIDER", "litellm")
        self.base_url = os.environ.get("AI_BASE_URL", "")
        self.api_key = os.environ.get("LITELLM_API_KEY", "sk-internal-agents-local")

    def call(self, system: str, prompt: str, model: str, max_tokens: int = 8192) -> LLMResponse:
        start = time.monotonic()
        text = self._dispatch(system, prompt, model, max_tokens)
        duration = time.monotonic() - start
        return LLMResponse(text=text, model=model, duration_s=duration)

    def list_models(self) -> list[str]:
        return [os.environ.get("AI_MODEL", "coding-model")]

    # ------------------------------------------------------------------

    def _dispatch(self, system: str, prompt: str, model: str, max_tokens: int) -> str:
        if self.provider in ("litellm", "ollama", "vllm"):
            return self._openai_compat(system, prompt, model, max_tokens)
        if self.provider == "anthropic":
            return self._anthropic(system, prompt, model, max_tokens)
        if self.provider == "openai":
            return self._openai(system, prompt, model, max_tokens)
        raise ValueError(f"Unknown AI_PROVIDER: {self.provider}")

    def _openai_compat(self, system: str, prompt: str, model: str, max_tokens: int) -> str:
        import openai

        base = self.base_url or {
            "litellm": "http://litellm.ai-models.svc.cluster.local:4000/v1",
            "ollama": "http://ollama.ai-models.svc.cluster.local:11434/v1",
            "vllm": "http://vllm.ai-models.svc.cluster.local:8000/v1",
        }.get(self.provider, "http://localhost:11434/v1")

        key = self.api_key if self.provider == "litellm" else (
            "ollama" if self.provider == "ollama" else "not-needed"
        )
        client = openai.OpenAI(base_url=base, api_key=key)
        resp = client.chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content

    def _anthropic(self, system: str, prompt: str, model: str, max_tokens: int) -> str:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=model or "claude-sonnet-4-20250514",
            max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def _openai(self, system: str, prompt: str, model: str, max_tokens: int) -> str:
        import openai
        if self.base_url:
            return self._openai_compat(system, prompt, model, max_tokens)
        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=model or "gpt-4o", max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content
