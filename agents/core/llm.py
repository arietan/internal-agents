"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0
    raw: Optional[dict] = field(default=None, repr=False)


class LLMProvider(ABC):
    """Cloud-agnostic interface for LLM inference."""

    @abstractmethod
    def call(
        self,
        system: str,
        prompt: str,
        model: str,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            system: System prompt.
            prompt: User prompt.
            model: Model identifier (alias or full name).
            max_tokens: Maximum tokens in the response.

        Returns:
            LLMResponse with generated text and metadata.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return available model identifiers."""
        ...
