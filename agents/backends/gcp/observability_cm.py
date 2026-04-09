"""GCP observability backend — Cloud Monitoring + Cloud Trace."""

import logging
import os
from contextlib import contextmanager
from typing import Optional

from agents.core.observability import ObservabilityProvider

log = logging.getLogger("backends.gcp.observability")


class CloudMonitoringObservability(ObservabilityProvider):
    """Emits metrics and traces via GCP Cloud Monitoring and Cloud Trace OTel exporters."""

    def __init__(self):
        self._project = os.environ.get("GCP_PROJECT", "")
        self._tracer = None
        self._meter = None
        self._metrics: dict = {}

    def init(self, agent_name: str) -> None:
        if not self._project:
            log.warning("GCP_PROJECT not set, observability disabled")
            return

        try:
            from opentelemetry import trace, metrics
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
            from opentelemetry.exporter.cloud_monitoring import CloudMonitoringMetricsExporter

            resource = Resource.create({"service.name": agent_name, "service.namespace": "internal-agents"})

            tp = TracerProvider(resource=resource)
            tp.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter(project_id=self._project)))
            trace.set_tracer_provider(tp)
            self._tracer = trace.get_tracer(agent_name)

            metric_exporter = CloudMonitoringMetricsExporter(project_id=self._project)
            reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=15000)
            mp = MeterProvider(resource=resource, metric_readers=[reader])
            metrics.set_meter_provider(mp)
            self._meter = metrics.get_meter(agent_name)

            self._metrics["runs"] = self._meter.create_counter("agent_runs_total")
            self._metrics["prs"] = self._meter.create_counter("agent_prs_created_total")
            self._metrics["reviews"] = self._meter.create_counter("agent_reviews_posted_total")
            self._metrics["llm_calls"] = self._meter.create_counter("agent_llm_call_total")
            self._metrics["llm_errors"] = self._meter.create_counter("agent_llm_call_errors_total")
            self._metrics["llm_duration"] = self._meter.create_histogram("agent_llm_call_duration_seconds", unit="s")

            log.info("Cloud Monitoring + Cloud Trace initialised for %s", agent_name)

        except ImportError as e:
            log.warning("GCP OTel exporters not installed: %s", e)

    def record_run(self, agent: str) -> None:
        if "runs" in self._metrics:
            self._metrics["runs"].add(1, {"agent": agent})

    def record_pr_created(self, agent: str, repo: str) -> None:
        if "prs" in self._metrics:
            self._metrics["prs"].add(1, {"agent": agent, "repo": repo})

    def record_review_posted(self, agent: str, recommendation: str) -> None:
        if "reviews" in self._metrics:
            self._metrics["reviews"].add(1, {"agent": agent, "recommendation": recommendation})

    def record_llm_call(
        self, agent: str, provider: str, model: str,
        duration_s: float, tokens: int = 0, error: bool = False,
    ) -> None:
        attrs = {"agent": agent, "provider": provider, "model": model}
        if "llm_calls" in self._metrics:
            self._metrics["llm_calls"].add(1, attrs)
        if "llm_duration" in self._metrics:
            self._metrics["llm_duration"].record(duration_s, attrs)
        if error and "llm_errors" in self._metrics:
            self._metrics["llm_errors"].add(1, attrs)

    @contextmanager
    def trace_span(self, name: str, attributes: Optional[dict] = None):
        if self._tracer:
            with self._tracer.start_as_current_span(name, attributes=attributes or {}) as span:
                yield span
        else:
            yield _NoopSpan()


class _NoopSpan:
    def set_attribute(self, key, value): pass
