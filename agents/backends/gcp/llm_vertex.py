"""GCP LLM backend — Vertex AI Generative AI API."""

import logging
import os
import time

from agents.core.llm import LLMProvider, LLMResponse

log = logging.getLogger("backends.gcp.llm")


class VertexProvider(LLMProvider):
    """Calls Vertex AI GenerativeModel for Gemini, Claude, etc."""

    def __init__(self):
        self._project = os.environ.get("GCP_PROJECT", "")
        self._location = os.environ.get("GCP_LOCATION", "us-central1")

    def call(self, system: str, prompt: str, model: str, max_tokens: int = 8192) -> LLMResponse:
        import vertexai
        from vertexai.generative_models import GenerativeModel, GenerationConfig

        vertexai.init(project=self._project, location=self._location)
        model_id = os.environ.get("VERTEX_MODEL_ID", model or "gemini-2.0-flash")

        gen_model = GenerativeModel(
            model_name=model_id,
            system_instruction=[system],
        )
        config = GenerationConfig(max_output_tokens=max_tokens, temperature=0.2)

        start = time.monotonic()
        response = gen_model.generate_content(prompt, generation_config=config)
        duration = time.monotonic() - start

        usage = response.usage_metadata
        return LLMResponse(
            text=response.text,
            model=model_id,
            input_tokens=usage.prompt_token_count if usage else 0,
            output_tokens=usage.candidates_token_count if usage else 0,
            duration_s=duration,
        )

    def list_models(self) -> list[str]:
        return [os.environ.get("VERTEX_MODEL_ID", "gemini-2.0-flash")]
