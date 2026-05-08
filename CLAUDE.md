# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Academic research project comparing two observability architectures for a distributed system to validate that an optimized configuration reduces overhead (CPU, memory, network) by >50% while maintaining >95% diagnostic capability.

- **Environment A**: Baseline — 100% span/log collection, no sampling
- **Environment B**: Optimized — tail sampling, probabilistic sampling, selective log filtering

## Common Commands

### Start/stop environments

```bash
# Env A — API on :8080, Prometheus on :9090, Grafana on :3000
docker compose -f env-A/docker-compose.yml up -d --build
docker compose -f env-A/docker-compose.yml down -v

# Env B — API on :8090, Prometheus on :9091, Grafana on :3001
docker compose -f env-B/docker-compose.yml up -d --build
docker compose -f env-B/docker-compose.yml down -v

# Health check
curl http://localhost:8080/health   # Env A
curl http://localhost:8090/health   # Env B
```

### Run experiments

```bash
cd experiments/scripts

# Single environment (load profiles: basic | medium | stress)
./run_experiment.sh A medium
./run_experiment.sh B medium

# Full pipeline: run A + B + analysis
./run_full_experiment.sh medium
```

### Analyze results

```bash
python3 experiments/scripts/analyze_results.py \
    --raw-dir experiments/raw-data \
    --out-dir experiments/processed
```

Output: `experiments/processed/` — `comparison.csv`, `summary.json`, `report.md`, charts.

### Run load tests manually

```bash
# Via Docker (inside compose network)
docker compose -f env-A/docker-compose.yml --profile loadtest run --rm \
    -e API_URL=http://api:8080 -e ENV_LABEL=A \
    k6 run /scripts/medium.js

# Locally (requires k6 installed)
k6 run -e API_URL=http://localhost:8080 -e ENV_LABEL=A \
    base-system/load-tests/medium.js
```

### Collect metrics manually

```bash
python3 experiments/scripts/collect_metrics.py \
    --prometheus http://localhost:9090 \
    --env A \
    --output experiments/raw-data/
```

## Architecture

### Services (both environments share the same application code)

```
base-system/
├── api/           Flask API — receives POST /process, forwards to Worker
├── worker/        Flask Worker — simulates CPU workload, injects faults (5% errors, 3% slow)
└── load-tests/    k6 scripts (basic.js / medium.js / stress.js)
```

Each service has its own `otel_config.py` that configures the OpenTelemetry SDK (tracer, meter, logger) and exports via OTLP/gRPC to the collector.

### Per-environment configuration

```
env-A/
├── docker-compose.yml       # No sampling — full export pipeline
└── otel/otel-collector.yaml

env-B/
├── docker-compose.yml       # Tail sampling + log/span filtering
└── otel/otel-collector.yaml
```

**Env B collector pipeline differences:**
- Tail sampling: 100% for error/slow traces, 10% probabilistic for normal traces (`decision_wait=10s`)
- Log filtering: drops DEBUG and INFO, keeps WARN/ERROR/FATAL
- Span filtering: drops `/health` and `/metrics` endpoint spans

### Observability stack

```
observability/
├── prometheus/prometheus.yml     # Scrape configs for both envs
└── grafana/provisioning/         # Dashboard & datasource provisioning
```

Both environments share a single Prometheus + Grafana instance. The collector exposes its own metrics on port `8888`.

### Experiment data flow

```
k6 load test → API → Worker → OTel Collector → Jaeger (traces) + Prometheus (metrics)
                                              ↓
                               collect_metrics.py (22 PromQL queries, sampled every 5s for 60s)
                                              ↓
                               raw-data/<run-id>/{metrics.csv, baseline.csv, k6-output.log, metadata.json}
                                              ↓
                               analyze_results.py → processed/{comparison.csv, report.md, charts/}
```

### Key metrics collected

| Category | Metrics |
|---|---|
| Collector overhead | CPU cores, memory bytes, network TX/RX bytes/s, spans/logs received/exported/dropped |
| Application | API error rate, throughput (req/s), latency p50/p95/p99 |
| Diagnostic | Worker fault count (ground truth), traces with errors preserved |

## Dependencies

**Python** (Flask services): `flask==3.0.3`, `opentelemetry-api/sdk==1.27.0`, `opentelemetry-exporter-otlp-proto-grpc==1.27.0`, `opentelemetry-instrumentation-flask==0.48b0`, `prometheus-client==0.20.0`, `gunicorn==22.0.0`

**Docker images**: `otel/opentelemetry-collector-contrib:0.103.0`, `jaegertracing/all-in-one:1.57`, `prom/prometheus:v2.54.1`, `grafana/grafana:11.1.0`, `grafana/k6:0.51.0`

**Prerequisites**: Docker Engine 24.0+, Docker Compose v2.20+, Python 3.10+
