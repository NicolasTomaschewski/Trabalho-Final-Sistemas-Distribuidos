# Relatório do Experimento - Overhead de Observabilidade

Comparação Ambiente A (baseline) vs Ambiente B (otimizado)


## 1. Redução de Overhead (RO)

| Carga | Métrica | A (mean ± IC95%) | B (mean ± IC95%) | RO % |
|-------|---------|----------------:|----------------:|-----:|
| basic | collector_cpu_cores | 0.0038 ± 0.0001 | 0.0050 ± 0.0002 | -32.67% |
| basic | collector_mem_mb | 173.5176 ± 1.4015 | 174.6647 ± 0.4545 | -0.66% |
| basic | collector_net_tx_bps | 0.0000 | 0.0000 | - |
| basic | logs_exported_rps | 0.0000 | 0.0000 | - |
| basic | spans_exported_rps | 32.4783 ± 9.1105 | 7.5805 ± 1.3064 | +76.66% |
| medium | collector_cpu_cores | 0.0018 ± 0.0006 | 0.0020 ± 0.0007 | -15.33% |
| medium | collector_mem_mb | 60.8577 ± 20.0211 | 68.1499 ± 22.4231 | -11.98% |
| medium | collector_net_tx_bps | 0.0000 | 0.0000 | - |
| medium | logs_exported_rps | 0.0000 | 0.0000 | - |
| medium | spans_exported_rps | 34.1156 ± 4.8807 | 9.8804 ± 1.0700 | +71.04% |
| stress | collector_cpu_cores | 0.0041 ± 0.0001 | 0.0053 ± 0.0001 | -28.89% |
| stress | collector_mem_mb | 194.1908 ± 0.1525 | 207.8906 | -7.05% |
| stress | collector_net_tx_bps | 0.0000 | 0.0000 | - |
| stress | logs_exported_rps | 0.0000 | 0.0000 | - |
| stress | spans_exported_rps | 34.1417 ± 10.8521 | 11.5179 ± 2.2029 | +66.26% |

## 2. Taxa de Diagnóstico (TD)

| Env | Load | Taxa erro observada | Taxa erro esperada | TD |
|-----|------|--------------------:|-------------------:|---:|
| A | basic | 5.42% | 5.00% | 100.00% |
| A | medium | 5.17% | 5.00% | 100.00% |
| A | stress | 5.08% | 5.00% | 100.00% |
| B | basic | 5.29% | 5.00% | 100.00% |
| B | medium | 4.83% | 5.00% | 96.57% |
| B | stress | 5.22% | 5.00% | 100.00% |

## 3. Latência da Aplicação

| Carga | Métrica | A (mean ± IC95%) | B (mean ± IC95%) | Δ |
|-------|---------|----------------:|----------------:|--:|
| basic | api_latency_p50_s | 62.5 ± 15.9ms | 38.9 ± 2.1ms | -23.6ms |
| basic | api_latency_p95_s | 1734.6 ± 50.6ms | 732.7 ± 145.5ms | -1001.9ms |
| basic | api_latency_p99_s | 4158.2 ± 25.6ms | 3400.6 ± 599.8ms | -757.6ms |
| medium | api_latency_p50_s | 116.2 ± 3.0ms | 113.3 ± 3.5ms | -2.9ms |
| medium | api_latency_p95_s | 2047.0 ± 49.9ms | 1794.6 ± 132.7ms | -252.4ms |
| medium | api_latency_p99_s | 4347.8 ± 15.0ms | 3976.0 ± 262.3ms | -371.8ms |
| stress | api_latency_p50_s | 158.5 ± 0.2ms | 164.4 ± 11.2ms | +5.8ms |
| stress | api_latency_p95_s | 1945.8 ± 12.3ms | 2075.3 ± 30.0ms | +129.6ms |
| stress | api_latency_p99_s | 4284.0 ± 9.5ms | 4174.4 ± 299.7ms | -109.6ms |