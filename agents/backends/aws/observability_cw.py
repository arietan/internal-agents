"""AWS observability backend — CloudWatch EMF + X-Ray."""

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Optional

from agents.core.observability import ObservabilityProvider

log = logging.getLogger("backends.aws.observability")


class CloudWatchObservability(ObservabilityProvider):
    """Emits CloudWatch Embedded Metrics Format and X-Ray traces."""

    def __init__(self):
        self._namespace = os.environ.get("CW_NAMESPACE", "InternalAgents")
        self._xray_enabled = os.environ.get("XRAY_ENABLED", "true").lower() == "true"
        self._recorder = None

    def init(self, agent_name: str) -> None:
        if self._xray_enabled:
            try:
                from aws_xray_sdk.core import xray_recorder, patch_all
                xray_recorder.configure(service=agent_name)
                patch_all()
                self._recorder = xray_recorder
                log.info("X-Ray tracing enabled for %s", agent_name)
            except ImportError:
                log.warning("aws-xray-sdk not installed, X-Ray disabled")

    def record_run(self, agent: str) -> None:
        self._emit_metric("AgentRuns", 1, {"Agent": agent})

    def record_pr_created(self, agent: str, repo: str) -> None:
        self._emit_metric("PRsCreated", 1, {"Agent": agent, "Repo": repo})

    def record_review_posted(self, agent: str, recommendation: str) -> None:
        self._emit_metric("ReviewsPosted", 1, {"Agent": agent, "Recommendation": recommendation})

    def record_llm_call(
        self, agent: str, provider: str, model: str,
        duration_s: float, tokens: int = 0, error: bool = False,
    ) -> None:
        dims = {"Agent": agent, "Provider": provider, "Model": model}
        self._emit_metric("LLMCalls", 1, dims)
        self._emit_metric("LLMDuration", duration_s, dims, unit="Seconds")
        if tokens:
            self._emit_metric("LLMTokens", tokens, dims)
        if error:
            self._emit_metric("LLMErrors", 1, dims)

    @contextmanager
    def trace_span(self, name: str, attributes: Optional[dict] = None):
        if self._recorder:
            segment = self._recorder.begin_subsegment(name)
            if attributes:
                for k, v in attributes.items():
                    segment.put_annotation(k, str(v))
            try:
                yield segment
            except Exception as e:
                segment.add_exception(e)
                raise
            finally:
                self._recorder.end_subsegment()
        else:
            yield _NoopSpan()

    def _emit_metric(self, name: str, value: float, dimensions: dict, unit: str = "Count") -> None:
        """Emit a metric via CloudWatch Embedded Metrics Format (EMF)."""
        emf = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [{
                    "Namespace": self._namespace,
                    "Dimensions": [list(dimensions.keys())],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }],
            },
            name: value,
            **dimensions,
        }
        print(json.dumps(emf), file=sys.stdout, flush=True)


class _NoopSpan:
    def set_attribute(self, key, value): pass
    def put_annotation(self, key, value): pass
    def add_exception(self, exc): pass
