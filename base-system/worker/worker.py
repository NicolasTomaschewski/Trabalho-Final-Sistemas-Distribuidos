"""
================================================================================
Worker - Sistema Distribuído Experimental
================================================================================
Processa tarefas recebidas da API. Simula carga computacional, latência
de I/O e falhas aleatórias para gerar dados experimentais realistas.

Endpoints:
    POST /work    -> Executa tarefa simulada
    GET  /health  -> Health-check
    GET  /metrics -> Métricas Prometheus

Simulações:
    1) Carga CPU - loop de hashes proporcional à `complexity`
    2) Latência I/O - sleep aleatório
    3) Falhas - 5% de exceções, 3% de slow requests (>2s)

Estes percentuais são CONHECIDOS e usados para calcular a Taxa de
Diagnóstico TD = falhas_detectadas / falhas_injetadas no relatório final.
================================================================================
"""

import os
import time
import random
import hashlib
import logging
from flask import Flask, request, jsonify

from otel_config import setup_telemetry, instrument_flask
from prometheus_client import (
    Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
)

# ============================================================================
# Configuração
# ============================================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] [trace_id=%(otelTraceID)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")

ENV_LABEL = os.getenv("ENV_LABEL", "unknown")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "worker")

# Probabilidades de falhas injetadas - DEVEM ser conhecidas para o cálculo
# de Taxa de Diagnóstico (TD = detectadas/injetadas).
FAULT_ERROR_RATE = float(os.getenv("FAULT_ERROR_RATE", "0.05"))      # 5%
FAULT_SLOW_RATE  = float(os.getenv("FAULT_SLOW_RATE",  "0.03"))      # 3%
SLOW_LATENCY_MS  = int(os.getenv("SLOW_LATENCY_MS",   "2500"))       # 2.5s

# ============================================================================
# Aplicação Flask
# ============================================================================
app = Flask(__name__)

setup_telemetry(service_name=SERVICE_NAME)
instrument_flask(app)

# ============================================================================
# Métricas Prometheus
# ============================================================================
WORK_COUNTER = Counter(
    "worker_tasks_total",
    "Total de tarefas processadas pelo worker",
    ["status", "env"],
)

WORK_LATENCY = Histogram(
    "worker_task_duration_seconds",
    "Duração de processamento de tarefas no worker",
    ["env"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
)

INJECTED_FAULTS = Counter(
    "worker_injected_faults_total",
    "Total de falhas INJETADAS (verdade absoluta para TD)",
    ["fault_type", "env"],
)

# ============================================================================
# Funções auxiliares
# ============================================================================
def cpu_burn(complexity: int) -> str:
    """
    Simula carga CPU realizando hashes SHA-256 em sequência.
    `complexity` é multiplicado por 10_000 iterações.

    Retorna o hash final (apenas para impedir o JIT/compilador de otimizar).
    """
    iterations = max(1, complexity) * 10_000
    h = hashlib.sha256()
    for i in range(iterations):
        h.update(f"{i}".encode())
    return h.hexdigest()


# ============================================================================
# Endpoints
# ============================================================================
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": SERVICE_NAME, "env": ENV_LABEL}), 200


@app.route("/metrics", methods=["GET"])
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/work", methods=["POST"])
def work():
    """
    Processa uma tarefa simulada.

    Body:
        { "task_id": "...", "complexity": 1..10 }

    Comportamento:
        - Sleep base aleatório (10..50ms) simulando I/O
        - CPU burn proporcional à complexity
        - Em ~5% dos casos, lança exceção (status 500)
        - Em ~3% dos casos, executa lentamente (>2s) sem erro
    """
    start = time.time()
    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id", "unknown")
    complexity = int(data.get("complexity", 3))

    try:
        # ----- Latência de I/O simulada ----------------------------------
        time.sleep(random.uniform(0.01, 0.05))

        # ----- Falha do tipo "lentidão" (slow) ---------------------------
        if random.random() < FAULT_SLOW_RATE:
            INJECTED_FAULTS.labels(fault_type="slow", env=ENV_LABEL).inc()
            slow_seconds = SLOW_LATENCY_MS / 1000.0
            logger.warning(
                f"injected slow fault task_id={task_id} duration={slow_seconds}s"
            )
            time.sleep(slow_seconds)

        # ----- Falha do tipo "erro" --------------------------------------
        if random.random() < FAULT_ERROR_RATE:
            INJECTED_FAULTS.labels(fault_type="error", env=ENV_LABEL).inc()
            logger.error(f"injected error fault task_id={task_id}")
            raise RuntimeError(f"injected fault for task {task_id}")

        # ----- Carga CPU --------------------------------------------------
        digest = cpu_burn(complexity)

        elapsed = time.time() - start
        WORK_LATENCY.labels(env=ENV_LABEL).observe(elapsed)
        WORK_COUNTER.labels(status="ok", env=ENV_LABEL).inc()

        logger.info(
            f"task completed task_id={task_id} complexity={complexity} "
            f"elapsed_ms={int(elapsed*1000)}"
        )
        return jsonify({
            "task_id": task_id,
            "env": ENV_LABEL,
            "elapsed_ms": int(elapsed * 1000),
            "digest_prefix": digest[:12],
        }), 200

    except Exception as e:
        elapsed = time.time() - start
        WORK_LATENCY.labels(env=ENV_LABEL).observe(elapsed)
        WORK_COUNTER.labels(status="error", env=ENV_LABEL).inc()
        logger.exception(f"task failed task_id={task_id}")
        return jsonify({"error": str(e), "task_id": task_id}), 500


# ============================================================================
# Entrypoint
# ============================================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    logger.warning(
        f"starting worker on :{port} env={ENV_LABEL} "
        f"err_rate={FAULT_ERROR_RATE} slow_rate={FAULT_SLOW_RATE}"
    )
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
