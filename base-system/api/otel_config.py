"""
================================================================================
Configuração de telemetria OpenTelemetry
================================================================================
Módulo compartilhado entre API e Worker que:
    - Configura provedor de tracing
    - Configura provedor de métricas
    - Exporta via OTLP/gRPC para o OTel Collector
    - Registra resource attributes (service.name, env, version)
    - Integra logs Python ao trace_id corrente

A escolha por OTLP/gRPC (porta 4317) é proposital:
    * Mais eficiente que HTTP/JSON (binário Protobuf)
    * Suportado nativamente pelo OTel Collector
    * Permite batching e compressão

Referência:
    https://opentelemetry.io/docs/languages/python/
================================================================================
"""

import os
import logging

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor


def setup_telemetry(service_name: str, service_version: str = "1.0.0") -> None:
    """
    Inicializa providers de tracing e métricas.

    Args:
        service_name:    Nome do serviço (usado como service.name no OTLP)
        service_version: Versão do serviço (resource attribute)
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    env_label = os.getenv("ENV_LABEL", "unknown")

    # ----- Resource: descreve o serviço para o backend de observabilidade -----
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": env_label,
        "experiment.environment": env_label,  # tag custom para filtrar A vs B
    })

    # ----- Tracing -----------------------------------------------------------
    # BatchSpanProcessor agrupa spans antes de enviar para reduzir RPC.
    # Em ambos os ambientes usamos batching - o que muda é o Collector.
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    tracer_provider.add_span_processor(BatchSpanProcessor(
        span_exporter,
        max_queue_size=2048,
        schedule_delay_millis=5000,
        max_export_batch_size=512,
    ))
    trace.set_tracer_provider(tracer_provider)

    # ----- Métricas (OTLP) ---------------------------------------------------
    # Usamos OTLP para métricas no SDK Python; o Collector também recebe
    # métricas do prometheus_client via /metrics scrape.
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=15000,
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )
    metrics.set_meter_provider(meter_provider)

    # ----- Integração de logs com traces -------------------------------------
    # Adiciona %(otelTraceID)s e %(otelSpanID)s ao LogRecord para correlação
    # log -> trace no Jaeger/Grafana.
    LoggingInstrumentor().instrument(set_logging_format=False)


def instrument_flask(app) -> None:
    """Instrumenta uma aplicação Flask para tracing automático."""
    FlaskInstrumentor().instrument_app(
        app,
        # Health checks são excluídos para não poluir os traces - são milhares
        # de chamadas que não agregam valor diagnóstico.
        excluded_urls="/health,/metrics",
    )


def instrument_requests() -> None:
    """Instrumenta a biblioteca `requests` para propagar trace context."""
    RequestsInstrumentor().instrument()
