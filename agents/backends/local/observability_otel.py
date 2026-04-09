"""Local observability backend — OTel tracing + Prometheus metrics."""

import logging
import os
from contextlib import contextmanager
from typing import Optional

from agents.core.observability import ObservabilityProvider

log = logging.getLogger("backends.local.observability")

_tracer = None
_meter = None
_metrics: dict = {}


class OtelObservability(ObservabilityProvider):
    """OTel + Prometheus implementation for K8s deployments (local and cloud-agnostic)."""

    def init(self, agent_name: str) -> None:
        global _tracer, _meter, _metrics

        if os.environ.get("OTEL_ENABLED", "true").lower() != "true":
            log.info("OpenTelemetry disabled (OTEL_ENABLED != true)")
            return

        try:
            from opentelemetry import trace, metrics
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.prometheus import PrometheusMetricReader
            from prometheus_client import start_http_server

            endpoint = os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://otel-collector.ai-observability.svc.cluster.local:4317",
            )
            resource = Resource.create({
                "service.name": os.environ.get("OTEL_SERVICE_NAME", agent_name),
                "service.namespace": "internal-agents",
                "agent.name": agent_name,
            })

            tp = TracerProvider(resource=resource)
            tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
            trace.set_tracer_provider(tp)
            _tracer = trace.get_tracer(agent_name)

            prom_reader = PrometheusMetricReader()
            otlp_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint, insecure=True),
                export_interval_millis=15000,
            )
            mp = MeterProvider(resource=resource, metric_readers=[prom_reader, otlp_reader])
            metrics.set_meter_provider(mp)
            _meter = metrics.get_meter(agent_name)

            _metrics["runs"] = _meter.create_counter("agent_runs_total")
            _metrics["prs"] = _meter.create_counter("agent_prs_created_total")
            _metrics["reviews"] = _meter.create_counter("agent_reviews_posted_total")
            _metrics["llm_calls"] = _meter.create_counter("agent_llm_call_total")
            _metrics["llm_errors"] = _meter.create_counter("agent_llm_call_errors_total")
            _metrics["llm_tokens"] = _meter.create_counter("agent_llm_tokens_total")
            _metrics["llm_duration"] = _meter.create_histogram("agent_llm_call_duration_seconds", unit="s")
            _metrics["review_rec"] = _meter.create_counter("agent_review_recommendation_total")

            metrics_port = int(os.environ.get("METRICS_PORT", "9464"))
            start_http_server(metrics_port)
            log.info("Telemetry → %s, /metrics on :%d", endpoint, metrics_port)

        except ImportError as e:
            log.warning("OTel packages not installed: %s", e)
        except Exception as e:
            log.warning("Failed to init telemetry: %s", e)

    def record_run(self, agent: str) -> None:
        if "runs" in _metrics:
            _metrics["runs"].add(1, {"agent": agent})

    def record_pr_created(self, agent: str, repo: str) -> None:
        if "prs" in _metrics:
            _metrics["prs"].add(1, {"agent": agent, "repo": repo})

    def record_review_posted(self, agent: str, recommendation: str) -> None:
        if "reviews" in _metrics:
            _metrics["reviews"].add(1, {"agent": agent})
        if "review_rec" in _metrics:
            _metrics["review_rec"].add(1, {"recommendation": recommendation})

    def record_llm_call(
        self, agent: str, provider: str, model: str,
        duration_s: float, tokens: int = 0, error: bool = False,
    ) -> None:
        attrs = {"agent": agent, "provider": provider, "model": model}
        if "llm_calls" in _metrics:
            _metrics["llm_calls"].add(1, attrs)
        if "llm_duration" in _metrics:
            _metrics["llm_duration"].record(duration_s, attrs)
        if tokens and "llm_tokens" in _metrics:
            _metrics["llm_tokens"].add(tokens, attrs)
        if error and "llm_errors" in _metrics:
            _metrics["llm_errors"].add(1, attrs)

    @contextmanager
    def trace_span(self, name: str, attributes: Optional[dict] = None):
        if _tracer:
            with _tracer.start_as_current_span(name, attributes=attributes or {}) as span:
                yield span
        else:
            yield _NoopSpan()


class _NoopSpan:
    def set_attribute(self, key, value): pass
    def set_status(self, status): pass
    def record_exception(self, exc): pass
    def add_event(self, name, attributes=None): pass
