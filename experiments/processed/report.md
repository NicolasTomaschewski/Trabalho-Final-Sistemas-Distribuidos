# Relatório do Experimento - Overhead de Observabilidade

Comparação Ambiente A (baseline) vs Ambiente B (otimizado)


## 1. Redução de Overhead (RO)

| Carga | Métrica | A (mean) | B (mean) | RO % |
|-------|---------|---------:|---------:|-----:|
| medium | collector_cpu_cores | 0.0000 | 0.0000 | - |
| medium | collector_mem_mb | 0.0000 | 0.0000 | - |
| medium | collector_net_tx_bps | 0.0000 | 0.0000 | - |
| medium | logs_exported_rps | 0.0000 | 0.0000 | - |
| medium | spans_exported_rps | 32.0484 | 9.0332 | +71.81% |

## 2. Taxa de Diagnóstico (TD)

| Env | Load | Injetadas | Detectadas (est.) | TD |
|-----|------|----------:|------------------:|---:|
| A | medium | 3944 | 2236.5 | 56.71% |
| B | medium | 3629 | 2074.8 | 57.17% |

## 3. Latência da Aplicação

| Carga | Métrica | A | B | Δ |
|-------|---------|--:|--:|--:|
| medium | api_latency_p50_s | 118.7ms | 116.1ms | -2.5ms |
| medium | api_latency_p95_s | 1907.9ms | 1770.3ms | -137.7ms |
| medium | api_latency_p99_s | 4301.3ms | 3679.8ms | -621.6ms |