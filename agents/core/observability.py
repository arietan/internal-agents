"""Abstract observability provider interface."""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Optional


class ObservabilityProvider(ABC):
    """Cloud-agnostic interface for metrics, traces, and structured logging.

    Local / cloud-agnostic K8s: OTel SDK + Prometheus + Langfuse.
    AWS: CloudWatch EMF + X-Ray.
    Azure: Application Insights + Azure Monitor.
    GCP: Cloud Monitoring + Cloud Trace.
    """

    @abstractmethod
    def init(self, agent_name: str) -> None:
        """Initialise telemetry for the given agent. Call once at startup."""
        ...

    @abstractmethod
    def record_run(self, agent: str) -> None:
        """Increment the agent run counter."""
        ...

    @abstractmethod
    def record_pr_created(self, agent: str, repo: str) -> None:
        """Record that a PR was created."""
        ...

    @abstractmethod
    def record_review_posted(self, agent: str, recommendation: str) -> None:
        """Record that a review was posted."""
        ...

    @abstractmethod
    def record_llm_call(
        self,
        agent: str,
        provider: str,
        model: str,
        duration_s: float,
        tokens: int = 0,
        error: bool = False,
    ) -> None:
        """Record an LLM call with timing and error information."""
        ...

    @abstractmethod
    @contextmanager
    def trace_span(self, name: str, attributes: Optional[dict] = None):
        """Context manager that creates a trace span.

        Usage::

            with obs.trace_span("clone-repo", {"repo": "owner/repo"}) as span:
                # ... do work ...
                span.set_attribute("files", 42)
        """
        ...
