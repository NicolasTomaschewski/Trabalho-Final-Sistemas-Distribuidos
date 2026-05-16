#!/usr/bin/env python3
"""
================================================================================
collect_metrics.py - Coleta métricas do Prometheus durante uma janela
================================================================================
Faz queries instantâneas ao Prometheus em intervalos fixos durante `duration`
segundos e grava todos os pontos em CSV.

As métricas coletadas cobrem:
    - CPU/memória dos containers críticos (api, worker, otel-collector)
    - Throughput e latência da API
    - Spans recebidos / exportados / dropados pelo collector
    - Logs recebidos / exportados pelo collector
    - Bytes de rede do collector
    - Falhas injetadas pelo worker

Uso:
    python collect_metrics.py --prom-url http://localhost:9090 \
                              --output run.csv \
                              --duration 60 \
                              --env A
================================================================================
"""

import argparse
import csv
import time
import sys
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.parse import urlencode
import json

# ----------------------------------------------------------------------------
# Queries PromQL - foram escolhidas para casar 1:1 com as métricas-chave
# do trabalho (overhead CPU/rede + capacidade diagnóstica).
# ----------------------------------------------------------------------------
QUERIES = {
    # ----- Aplicação -------------------------------------------------------
    "api_throughput_rps":        'sum(rate(api_requests_total[1m]))',
    "api_error_rate":            'sum(rate(api_requests_total{status=~"5.."}[1m])) / clamp_min(sum(rate(api_requests_total[1m])), 0.001)',
    "api_latency_p50_s":         'histogram_quantile(0.50, sum(rate(api_request_duration_seconds_bucket[1m])) by (le))',
    "api_latency_p95_s":         'histogram_quantile(0.95, sum(rate(api_request_duration_seconds_bucket[1m])) by (le))',
    "api_latency_p99_s":         'histogram_quantile(0.99, sum(rate(api_request_duration_seconds_bucket[1m])) by (le))',
    "worker_tasks_ok":           'sum(rate(worker_tasks_total{status="ok"}[1m]))',
    "worker_tasks_err":          'sum(rate(worker_tasks_total{status="error"}[1m]))',
    "worker_injected_total":     'sum(increase(worker_injected_faults_total[5m]))',
    "worker_injected_error":     'sum(increase(worker_injected_faults_total{fault_type="error"}[5m]))',
    "worker_injected_slow":      'sum(increase(worker_injected_faults_total{fault_type="slow"}[5m]))',

    # ----- Collector (OVERHEAD - métricas-chave do artigo) -----------------
    "collector_cpu_cores":       'rate(otelcol_process_cpu_seconds{job="otel-collector-internal"}[1m])',
    "collector_mem_mb":          'otelcol_process_memory_rss{job="otel-collector-internal"} / (1024*1024)',
    "collector_net_tx_bps":      'sum(rate(container_network_transmit_bytes_total{name=~".*otel-collector.*"}[1m]))',
    "collector_net_rx_bps":      'sum(rate(container_network_receive_bytes_total{name=~".*otel-collector.*"}[1m]))',

    "spans_received_rps":        'sum(rate(otelcol_receiver_accepted_spans[1m]))',
    "spans_exported_rps":        'sum(rate(otelcol_exporter_sent_spans[1m]))',
    "spans_dropped_rps":         'sum(rate(otelcol_processor_dropped_spans[1m])) or vector(0)',
    "spans_refused_rps":         'sum(rate(otelcol_receiver_refused_spans[1m])) or vector(0)',

    "logs_received_rps":         'sum(rate(otelcol_receiver_accepted_log_records[1m])) or vector(0)',
    "logs_exported_rps":         'sum(rate(otelcol_exporter_sent_log_records[1m])) or vector(0)',

    "metrics_received_rps":      'sum(rate(otelcol_receiver_accepted_metric_points[1m])) or vector(0)',
    "metrics_exported_rps":      'sum(rate(otelcol_exporter_sent_metric_points[1m])) or vector(0)',

    # ----- Aplicação - CPU/MEM (contexto de carga) -------------------------
    "api_cpu_cores":             'sum(rate(container_cpu_usage_seconds_total{name=~".*-api"}[1m]))',
    "api_mem_mb":                'sum(container_memory_working_set_bytes{name=~".*-api"}) / (1024*1024)',
    "worker_cpu_cores":          'sum(rate(container_cpu_usage_seconds_total{name=~".*-worker"}[1m]))',
    "worker_mem_mb":             'sum(container_memory_working_set_bytes{name=~".*-worker"}) / (1024*1024)',

    # ----- Jaeger ----------------------------------------------------------
    "jaeger_spans_received":     'sum(increase(jaeger_collector_spans_received_total[5m])) or vector(0)',
    "jaeger_spans_saved":        'sum(increase(jaeger_collector_spans_saved_by_svc_total[5m])) or vector(0)',
}


def query_prom(prom_url: str, expr: str) -> float:
    """Executa uma query instantânea no Prometheus. Retorna primeiro valor ou NaN."""
    try:
        url = f"{prom_url}/api/v1/query?{urlencode({'query': expr})}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if data.get("status") != "success":
            return float("nan")
        result = data["data"]["result"]
        if not result:
            return 0.0  # nada retornado = 0 (importante para taxas)
        # vector retorna [timestamp, "value"] - pegamos o primeiro
        val = result[0]["value"][1]
        return float(val) if val not in ("NaN", "+Inf", "-Inf") else float("nan")
    except Exception as e:
        print(f"  [warn] query failed: {expr[:60]}... -> {e}", file=sys.stderr)
        return float("nan")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prom-url", required=True)
    ap.add_argument("--output",   required=True)
    ap.add_argument("--duration", type=int, default=60, help="seconds")
    ap.add_argument("--interval", type=int, default=5,  help="seconds between samples")
    ap.add_argument("--label",    default="run")
    ap.add_argument("--env",      default="unknown")
    args = ap.parse_args()

    fieldnames = ["timestamp", "label", "env"] + list(QUERIES.keys())
    rows = []

    end_at = time.time() + args.duration
    samples = 0
    while time.time() < end_at:
        ts = datetime.utcnow().isoformat() + "Z"
        row = {"timestamp": ts, "label": args.label, "env": args.env}
        for name, expr in QUERIES.items():
            row[name] = query_prom(args.prom_url, expr)
        rows.append(row)
        samples += 1
        print(f"  sample {samples}: t={ts} cpu={row.get('collector_cpu_cores'):.4f} "
              f"spans_in={row.get('spans_received_rps'):.1f} "
              f"spans_out={row.get('spans_exported_rps'):.1f}")
        time.sleep(args.interval)

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\nGravado: {args.output} ({samples} amostras)")


if __name__ == "__main__":
    main()
