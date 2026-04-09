"""
Shared telemetry module for all agents.

Thin façade over the ObservabilityProvider interface selected by CLOUD_PROVIDER.

  local / cloud-agnostic K8s → OTel + Prometheus + Langfuse
  aws                        → CloudWatch EMF + X-Ray
  azure                      → Application Insights + Azure Monitor
  gcp                        → Cloud Monitoring + Cloud Trace
"""

import logging
import time
from contextlib import contextmanager
from functools import wraps

from agents.core.factory import get_observability

log = logging.getLogger("telemetry")

_initialised = False


def init_telemetry(agent_name: str):
    """Initialise the observability backend. Call once at agent startup."""
    global _initialised
    if _initialised:
        return
    get_observability().init(agent_name)
    _initialised = True


# ── Public API ───────────────────────────────────────────────────────────────


def record_run(agent: str):
    get_observability().record_run(agent)


def record_pr_created(agent: str, repo: str):
    get_observability().record_pr_created(agent, repo)


def record_review_posted(agent: str, recommendation: str):
    get_observability().record_review_posted(agent, recommendation)


def record_llm_call(agent: str, provider: str, model: str, duration_s: float, tokens: int = 0, error: bool = False):
    get_observability().record_llm_call(agent, provider, model, duration_s, tokens, error)


@contextmanager
def trace_span(name: str, attributes: dict | None = None):
    """Context manager that creates a trace span via the active backend."""
    with get_observability().trace_span(name, attributes) as span:
        yield span


def timed_llm_call(agent_name: str, provider: str, model: str):
    """Decorator that records LLM call duration and errors."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.monotonic()
            error = False
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception:
                error = True
                raise
            finally:
                duration = time.monotonic() - start
                record_llm_call(agent_name, provider, model, duration, error=error)
        return wrapper
    return decorator
