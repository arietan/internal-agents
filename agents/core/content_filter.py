"""Abstract content filter interface for DLP and safety screening."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FilterFinding:
    """A single sensitive-data finding."""

    pattern_type: str
    severity: str  # high, critical
    action: str  # blocked, redacted, detected
    location: str = ""  # source context (e.g. "prompt", "pr_diff")
    snippet: str = ""  # truncated match for logging (never the full secret)


class ContentFilter(ABC):
    """Cloud-agnostic interface for DLP / content safety screening.

    Local: Python regex scanner (10 patterns).
    AWS: Bedrock Guardrails (ML-based PII + content filters).
    Azure: AI Content Safety (moderation + PII + prompt shields).
    GCP: Cloud DLP API (200+ info types).
    """

    @abstractmethod
    def scan(self, text: str, source: str = "prompt") -> list[FilterFinding]:
        """Scan text for sensitive content.

        Args:
            text: The content to scan.
            source: Context label (e.g. "prompt", "pr_diff", "llm_output").

        Returns:
            List of findings. Empty list means clean.
        """
        ...

    @abstractmethod
    def redact(self, text: str) -> str:
        """Redact detected sensitive patterns from content.

        Args:
            text: The content to redact.

        Returns:
            Text with sensitive patterns replaced by [REDACTED:<type>] tokens.
        """
        ...
