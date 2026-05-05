"""
================================================================================
API Flask - Sistema Distribuído Experimental
================================================================================
Componente principal do sistema. Recebe requisições HTTP, gera traces
distribuídos via OpenTelemetry e delega processamento ao worker.

Endpoints:
    POST /process   -> Encaminha tarefa ao worker e retorna resultado
    GET  /health    -> Health-check (não instrumentado para reduzir ruído)
    GET  /metrics   -> Métricas Prometheus (instrumentadas pelo middleware)

Instrumentação:
    - OpenTelemetry SDK (traces + metrics) via OTLP -> OTel Collector
    - prometheus_client expõe /metrics no formato Prometheus
    - propagação W3C TraceContext nas chamadas API -> Worker

Variáveis de ambiente esperadas:
    OTEL_SERVICE_NAME           Nome do serviço (ex: api-env-a)
    OTEL_EXPORTER_OTLP_ENDPOINT Endpoint do collector (ex: http://otel-collector:4317)
    WORKER_URL                  URL do worker (ex: http://worker:8081)
    ENV_LABEL                   Identificador do ambiente (A ou B)
================================================================================
"""

import os
import time
import random
import logging
import requests
from flask import Flask, request, jsonify

# ---- Instrumentação OpenTelemetry ---------------------------------------------
from otel_config import setup_telemetry, instrument_flask, instrument_requests

# ---- Métricas Prometheus nativas (exposição direta em /metrics) ---------------
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
)

# ============================================================================
# Configuração de logging
# ============================================================================
# O nível de log é controlado por LOG_LEVEL para permitir comparação
# entre ambientes (Env A: DEBUG/INFO completo / Env B: WARNING+).
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] [trace_id=%(otelTraceID)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api")

# ============================================================================
# Configuração da aplicação
# ============================================================================
app = Flask(__name__)

WORKER_URL = os.getenv("WORKER_URL", "http://worker:8081")
ENV_LABEL = os.getenv("ENV_LABEL", "unknown")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "api")

# Telemetry deve ser inicializada antes de instrumentar Flask/Requests
setup_telemetry(service_name=SERVICE_NAME)
instrument_flask(app)
instrument_requests()

# ============================================================================
# Métricas Prometheus customizadas
# ============================================================================
# Estas métricas alimentam Grafana e permitem comparar overhead/latência
# entre os ambientes A e B.

REQUEST_COUNT = Counter(
    "api_requests_total",
    "Total de requisições recebidas pela API",
    ["method", "endpoint", "status", "env"],
)

REQUEST_LATENCY = Histogram(
    "api_request_duration_seconds",
    "Latência das requisições da API em segundos",
    ["endpoint", "env"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

INFLIGHT = Gauge(
    "api_inflight_requests",
    "Número de requisições em processamento",
    ["env"],
)

WORKER_FAILURES = Counter(
    "api_worker_failures_total",
    "Falhas observadas ao chamar o worker",
    ["reason", "env"],
)

# ============================================================================
# Endpoints
# ============================================================================
@app.route("/health", methods=["GET"])
def health():
    """
    Health-check leve. Não realiza chamadas externas.
    Usado por orquestradores (Docker healthcheck) - retorna 200 OK.
    """
    return jsonify({"status": "ok", "service": SERVICE_NAME, "env": ENV_LABEL}), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    """Exposição de métricas no formato Prometheus para scraping."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/process", methods=["POST"])
def process():
    """
    Endpoint principal. Recebe um payload JSON e delega ao worker.

    Body esperado:
        {
            "task_id": "uuid-opcional",
            "payload": "string-arbitrária",
            "complexity": 1..10  # opcional, controla carga simulada
        }

    Comportamento:
        1) Valida payload mínimo
        2) Encaminha ao worker via HTTP (instrumentado)
        3) Retorna resultado ou erro

    Falhas simuladas:
        - Em ~2% das requisições injeta erro 500 (controle de baseline
          de erros para a Taxa de Diagnóstico TD do artigo).
    """
    INFLIGHT.labels(env=ENV_LABEL).inc()
    start = time.time()
    status_code = 200
    endpoint = "/process"

    try:
        data = request.get_json(silent=True) or {}
        task_id = data.get("task_id", f"task-{random.randint(1, 10**9)}")
        complexity = int(data.get("complexity", 3))

        logger.info(f"received task task_id={task_id} complexity={complexity}")

        # Injeção de falha controlada (2% das requisições) - permite medir
        # a capacidade diagnóstica do sistema de observabilidade.
        if random.random() < 0.02:
            logger.error(f"injected fault in api task_id={task_id}")
            WORKER_FAILURES.labels(reason="injected", env=ENV_LABEL).inc()
            status_code = 500
            return jsonify({"error": "injected fault", "task_id": task_id}), 500

        # Chamada ao worker - propagação de contexto W3C automática via
        # RequestsInstrumentor. O collector verá o span pai (api) e o
        # span filho (worker) compondo o trace distribuído.
        try:
            r = requests.post(
                f"{WORKER_URL}/work",
                json={"task_id": task_id, "complexity": complexity},
                timeout=10,
            )
            r.raise_for_status()
            result = r.json()
        except requests.exceptions.Timeout:
            logger.error(f"worker timeout task_id={task_id}")
            WORKER_FAILURES.labels(reason="timeout", env=ENV_LABEL).inc()
            status_code = 504
            return jsonify({"error": "worker timeout", "task_id": task_id}), 504
        except requests.exceptions.RequestException as e:
            logger.error(f"worker error task_id={task_id} err={e}")
            WORKER_FAILURES.labels(reason="error", env=ENV_LABEL).inc()
            status_code = 502
            return jsonify({"error": str(e), "task_id": task_id}), 502

        return jsonify({
            "task_id": task_id,
            "env": ENV_LABEL,
            "result": result,
        }), 200

    finally:
        INFLIGHT.labels(env=ENV_LABEL).dec()
        elapsed = time.time() - start
        REQUEST_LATENCY.labels(endpoint=endpoint, env=ENV_LABEL).observe(elapsed)
        REQUEST_COUNT.labels(
            method="POST", endpoint=endpoint, status=str(status_code), env=ENV_LABEL
        ).inc()


# ============================================================================
# Entrypoint
# ============================================================================
if __name__ == "__main__":
    # 0.0.0.0 para escutar em todas as interfaces dentro do container
    port = int(os.getenv("PORT", "8080"))
    logger.warning(f"starting api on :{port} env={ENV_LABEL} worker={WORKER_URL}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
