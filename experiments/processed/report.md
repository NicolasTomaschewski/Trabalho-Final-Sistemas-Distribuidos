# Relatório do Experimento - Overhead de Observabilidade

Comparação Ambiente A (baseline) vs Ambiente B (otimizado)


## 1. Redução de Overhead (RO)

| Carga | Métrica | A (mean) | B (mean) | RO % |
|-------|---------|---------:|---------:|-----:|
| medium | collector_cpu_cores | - | - | - |
| medium | collector_mem_mb | - | - | - |
| medium | collector_net_tx_bps | - | - | - |
| medium | logs_exported_rps | - | - | - |
| medium | spans_exported_rps | - | - | - |

## 2. Taxa de Diagnóstico (TD)

| Env | Load | Injetadas | Detectadas (est.) | TD |
|-----|------|----------:|------------------:|---:|
| A | medium | 0 | 0.0 | - |
| B | medium | 0 | 0.0 | - |

## 3. Latência da Aplicação

| Carga | Métrica | A | B | Δ |
|-------|---------|--:|--:|--:|
| medium | api_latency_p50_s | - | - | - |
| medium | api_latency_p95_s | - | - | - |
| medium | api_latency_p99_s | - | - | - |