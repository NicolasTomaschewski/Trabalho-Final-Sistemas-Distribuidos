# Redução de Overhead de Observabilidade em Sistemas Distribuídos

> Projeto experimental acadêmico de Sistemas Distribuídos.
> Compara duas arquiteturas de observabilidade — uma tradicional (Ambiente A)
> e uma otimizada com *tail sampling*, *probabilistic sampling* e filtragem
> seletiva de logs (Ambiente B) — em termos de **overhead** (CPU, memória,
> rede, volume de telemetria) preservando **capacidade diagnóstica**.

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Pré-requisitos](#3-pré-requisitos)
4. [Como executar](#4-como-executar)
5. [Endpoints e portas](#5-endpoints-e-portas)
6. [Como rodar benchmarks](#6-como-rodar-benchmarks)
7. [Como coletar resultados](#7-como-coletar-resultados)
8. [Como interpretar os resultados](#8-como-interpretar-os-resultados)
9. [Estrutura do projeto](#9-estrutura-do-projeto)
10. [Experimentos sugeridos](#10-experimentos-sugeridos)
11. [Referências](#11-referências)

---

## 1. Visão geral

### 1.1 Objetivo

Validar experimentalmente que uma arquitetura de observabilidade otimizada,
combinando **tail sampling**, **probabilistic sampling** e **filtragem por
severidade**, é capaz de reduzir significativamente o consumo de recursos
do pipeline de telemetria sem sacrificar a capacidade de diagnosticar
falhas no sistema observado.

### 1.2 Hipótese experimental

> **H1**: A arquitetura otimizada (Ambiente B) reduz o overhead de
> observabilidade em pelo menos 50% (medido em CPU do collector, bytes
> de rede e volume de spans exportados) sem reduzir a Taxa de Diagnóstico
> abaixo de 95% em relação ao baseline (Ambiente A).

### 1.3 Métricas-alvo

| Sigla | Métrica | Fórmula |
|-------|---------|---------|
| **RO** | Redução de Overhead | `((Overhead_A - Overhead_B) / Overhead_A) * 100` |
| **TD** | Taxa de Diagnóstico | `falhas_detectadas / falhas_injetadas` |

`falhas_injetadas` é **conhecida a priori** — o worker injeta falhas com
probabilidades fixas (`FAULT_ERROR_RATE=0.05`, `FAULT_SLOW_RATE=0.03`) e
incrementa um contador Prometheus (`worker_injected_faults_total`) que
serve como *ground truth*.

---

## 2. Arquitetura

### 2.1 Sistema observado

Um pequeno sistema distribuído composto por dois serviços Flask:

```
   ┌────────┐    HTTP/JSON   ┌──────────┐
   │ Cliente├────────────────► API      │
   │ (k6)   │                │ (Flask)  │
   └────────┘                └────┬─────┘
                                  │ HTTP/JSON
                                  ▼
                            ┌──────────┐
                            │ Worker   │ ← injeção de falhas (5% + 3%)
                            │ (Flask)  │   carga simulada (SHA-256)
                            └──────────┘
```

A API recebe `POST /process`, encaminha ao Worker em `POST /work`. O Worker
simula processamento (CPU + I/O) e injeta falhas controladas para que a
capacidade diagnóstica seja mensurável.

### 2.2 Pipeline de observabilidade

```
       ┌──────────┐  ┌──────────┐
       │   API    │  │  Worker  │
       │  (OTel   │  │  (OTel   │
       │   SDK)   │  │   SDK)   │
       └────┬─────┘  └────┬─────┘
            │ OTLP/gRPC   │ OTLP/gRPC
            └──────┬──────┘
                   ▼
        ┌──────────────────────┐
        │  OTel Collector      │  ← config DIFERENTE entre A e B
        │  (env-A ou env-B)    │
        └─────┬─────────┬──────┘
              │         │
        ┌─────▼───┐  ┌──▼───────┐
        │ Jaeger  │  │ Prometheus│
        │ (UI)    │  │ (TSDB)    │
        └─────────┘  └────┬──────┘
                          │
                     ┌────▼────┐
                     │ Grafana │
                     └─────────┘
```

A diferença experimental está **exclusivamente** na configuração do
OpenTelemetry Collector:

| Aspecto | Env A | Env B |
|---------|-------|-------|
| Sampling de traces | nenhum (100%) | tail sampling com 3 políticas |
| - traces com erro | 100% | 100% (preservado) |
| - traces lentos (>1s) | 100% | 100% (preservado) |
| - traces normais | 100% | **10%** (probabilistic) |
| Logs | tudo (INFO+) | apenas WARN/ERROR/FATAL |
| Filtro de health-checks | não | sim (drop) |

### 2.3 Stack de containers (por ambiente)

| Componente | Imagem | Função |
|------------|--------|--------|
| `api` | python:3.11-slim + Flask | endpoint `/process` |
| `worker` | python:3.11-slim + Flask | processamento + injeção de falhas |
| `otel-collector` | otel/opentelemetry-collector-contrib:0.103.0 | pipeline de telemetria |
| `jaeger` | jaegertracing/all-in-one:1.57 | armazenamento + UI de traces |
| `prometheus` | prom/prometheus:v2.54.1 | TSDB de métricas |
| `grafana` | grafana/grafana:11.1.0 | dashboards |
| `cadvisor` | gcr.io/cadvisor/cadvisor:v0.49.1 | métricas por container |
| `node-exporter` | prom/node-exporter:v1.8.2 | métricas de host |
| `k6` | grafana/k6:0.51.0 | gerador de carga (sob demanda) |

---

## 3. Pré-requisitos

### 3.1 Software necessário

| Ferramenta | Versão mínima | Verificar com |
|------------|---------------|---------------|
| Docker Engine | 24.0+ | `docker --version` |
| Docker Compose | v2.20+ | `docker compose version` |
| Python | 3.10+ | `python --version` |
| (Opcional) k6 local | 0.50+ | `k6 version` |

> **Observação:** k6 já está incluído no docker-compose como serviço com
> profile `loadtest`, então **não é obrigatório** instalá-lo localmente.

### 3.2 Recursos de host recomendados

- 4 vCPU
- 8 GB RAM (cada ambiente consome ~3-4 GB)
- 10 GB de espaço em disco

### 3.3 Instalação (Linux Ubuntu/Debian)

```bash
# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Logout/login para aplicar

# Python + matplotlib (para gerar gráficos)
sudo apt update
sudo apt install -y python3 python3-pip
pip3 install matplotlib
```

### 3.4 Instalação (Windows)

1. Instale **Docker Desktop**: <https://www.docker.com/products/docker-desktop/>
2. Em *Settings → Resources*, garanta no mínimo 4 CPUs e 6 GB RAM.
3. Instale **Python 3.10+**: <https://www.python.org/downloads/>
4. No PowerShell:
   ```powershell
   pip install matplotlib
   ```

> Os scripts de experimento têm versão `.sh` (Linux/macOS) e `.ps1` (Windows).
> Use a que combinar com seu shell.

### 3.5 Instalação (macOS)

```bash
brew install --cask docker
brew install python
pip3 install matplotlib
```

---

## 4. Como executar

### 4.1 Clonar e preparar

```bash
git clone <seu-repo> observability-overhead-experiment
cd observability-overhead-experiment
chmod +x experiments/scripts/*.sh    # apenas Linux/macOS
```

### 4.2 Subir Ambiente A (baseline)

```bash
docker compose -f env-A/docker-compose.yml up -d --build
```

Aguarde os health-checks estabilizarem (~30 segundos):

```bash
docker compose -f env-A/docker-compose.yml ps
```

Acesse:

- API: <http://localhost:8080/health>
- Jaeger UI: <http://localhost:16686>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3000> (admin/admin)
- cAdvisor: <http://localhost:8088>

Faça uma chamada de teste:

```bash
curl -X POST http://localhost:8080/process \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"smoke-test","complexity":3}'
```

Verifique no Jaeger que o trace apareceu, e no Grafana o dashboard
"Experimento Overhead - Visão Geral".

Para derrubar:

```bash
docker compose -f env-A/docker-compose.yml down -v
```

### 4.3 Subir Ambiente B (otimizado)

> **Atenção**: Ambiente B usa portas *shifted* (8090, 9091, 3001, etc.)
> para permitir rodar A e B simultaneamente se desejado.

```bash
docker compose -f env-B/docker-compose.yml up -d --build
```

Acesse:

- API: <http://localhost:8090/health>
- Jaeger UI: <http://localhost:16687>
- Prometheus: <http://localhost:9091>
- Grafana: <http://localhost:3001>
- cAdvisor: <http://localhost:8089>

### 4.4 Rodar um experimento controlado

#### Linux/macOS

```bash
cd experiments/scripts
./run_experiment.sh A medium     # roda A com carga média
./run_experiment.sh B medium     # roda B com mesma carga
python3 analyze_results.py \
  --raw-dir ../raw-data \
  --out-dir ../processed
```

Ou tudo de uma vez:

```bash
./run_full_experiment.sh medium
```

#### Windows (PowerShell)

```powershell
cd experiments\scripts
.\run_experiment.ps1 -Env A -Load medium
.\run_experiment.ps1 -Env B -Load medium
python analyze_results.py --raw-dir ..\raw-data --out-dir ..\processed
```

Ou:

```powershell
.\run_full_experiment.ps1 -Load medium
```

---

## 5. Endpoints e portas

### Ambiente A

| Serviço | URL | Descrição |
|---------|-----|-----------|
| API `/health` | <http://localhost:8080/health> | health-check |
| API `/process` | `POST` <http://localhost:8080/process> | endpoint principal |
| API `/metrics` | <http://localhost:8080/metrics> | métricas Prometheus |
| Worker `/health` | <http://localhost:8081/health> | health-check |
| Worker `/metrics` | <http://localhost:8081/metrics> | métricas Prometheus |
| OTel Collector zPages | <http://localhost:55679/debug/tracez> | debug |
| OTel Collector métricas | <http://localhost:8888/metrics> | métricas internas |
| OTel Collector exporter | <http://localhost:8889/metrics> | métricas exportadas |
| Jaeger UI | <http://localhost:16686> | viewer de traces |
| Prometheus UI | <http://localhost:9090> | TSDB UI |
| Grafana UI | <http://localhost:3000> | dashboards |
| cAdvisor | <http://localhost:8088> | métricas de containers |
| node-exporter | <http://localhost:9100/metrics> | métricas de host |

### Ambiente B (portas +10 / +1)

| Serviço | URL |
|---------|-----|
| API | <http://localhost:8090> |
| Worker | <http://localhost:8091> |
| Jaeger UI | <http://localhost:16687> |
| Prometheus | <http://localhost:9091> |
| Grafana | <http://localhost:3001> |
| cAdvisor | <http://localhost:8089> |

### Payload da API

```http
POST /process HTTP/1.1
Content-Type: application/json

{
  "task_id":    "uuid-opcional",
  "payload":    "string-arbitraria",
  "complexity": 1
}
```

`complexity` ∈ [1, 10] controla o trabalho CPU simulado pelo worker
(`complexity * 10_000` iterações de SHA-256).

---

## 6. Como rodar benchmarks

Existem 3 scripts k6 em `base-system/load-tests/`:

| Script | VUs | Duração | Uso recomendado |
|--------|-----|---------|-----------------|
| `basic.js` | 10 | 1 min | smoke-test, validação |
| `medium.js` | 30 (ramp) | 4-5 min | **cenário principal** |
| `stress.js` | 100 (ramp) | 8 min | stress / saturação |

### 6.1 Executando dentro do compose (recomendado)

```bash
docker compose -f env-A/docker-compose.yml --profile loadtest run --rm \
  -e API_URL=http://api:8080 -e ENV_LABEL=A \
  k6 run /scripts/medium.js
```

> O serviço `k6` tem `profile: loadtest`, então só sobe quando explicitado.

### 6.2 Executando k6 local (host)

```bash
k6 run -e API_URL=http://localhost:8080 -e ENV_LABEL=A base-system/load-tests/medium.js
```

### 6.3 Parâmetros aceitos

Todos os scripts aceitam via `-e`:

| Variável | Default | Descrição |
|----------|---------|-----------|
| `API_URL` | `http://localhost:8080` | URL base da API |
| `ENV_LABEL` | `unknown` | Label de tag em todas as métricas |

Para personalizar VUs/duração, edite a `options` no topo de cada script.

---

## 7. Como coletar resultados

### 7.1 Estrutura de saída

Cada execução de `run_experiment.sh` cria um diretório:

```
experiments/raw-data/
└── envA-medium-20251112-143022/
    ├── baseline.csv      # snapshot de 30s antes da carga
    ├── metrics.csv       # snapshot de 60s pós-carga
    ├── k6-output.log     # stdout do k6
    └── metadata.json     # metadados do run
```

A análise lê **todos** os runs em `raw-data/` e produz:

```
experiments/processed/
├── comparison.csv        # tabela: load × métrica × A/B × RO%
├── summary.json          # diagnóstico TD
├── report.md             # relatório markdown completo
└── charts/
    ├── collector_cpu_cores.png
    ├── collector_mem_mb.png
    ├── collector_net_tx_bps.png
    ├── spans_exported_rps.png
    ├── logs_exported_rps.png
    └── api_latency_p95_s.png
```

### 7.2 Métricas coletadas

`collect_metrics.py` faz **22 queries PromQL** a cada 5 segundos por
60 segundos (default). As principais:

**Aplicação**
- `api_throughput_rps` — req/s
- `api_error_rate` — fração de respostas 5xx
- `api_latency_p50_s`, `_p95_s`, `_p99_s`
- `worker_injected_total` — total de falhas injetadas (ground truth)

**Collector (overhead)**
- `collector_cpu_cores`
- `collector_mem_mb`
- `collector_net_tx_bps`, `_rx_bps`
- `spans_received_rps`, `spans_exported_rps`, `spans_dropped_rps`
- `logs_received_rps`, `logs_exported_rps`

**Sistema**
- `api_cpu_cores`, `api_mem_mb`
- `worker_cpu_cores`, `worker_mem_mb`

### 7.3 Logs e traces

Logs do collector ficam em `docker logs env-X-otel-collector` (no Env B
estão drasticamente reduzidos pelo filter).

Traces ficam no Jaeger em memória. Para preservá-los entre runs, exporte
manualmente via API do Jaeger:

```bash
curl 'http://localhost:16686/api/traces?service=api-env-a&limit=1000' \
  > experiments/raw-data/jaeger-env-a.json
```

---

## 8. Como interpretar os resultados

### 8.1 Redução de Overhead (RO)

Esperado na arquitetura otimizada:

| Métrica | Redução típica |
|---------|----------------|
| Spans exportados | ~80–90% (sampling 10% dos normais) |
| Logs exportados | ~70–95% (drop INFO) |
| CPU do collector | ~30–60% |
| Bytes de rede TX | ~75–90% |

**Importante**: A CPU do *collector* deve cair, mas o tail_sampling tem
custo (precisa armazenar spans em buffer por `decision_wait`). O RO de
CPU é menor que o RO de spans/bytes — isso é esperado e parte da análise.

### 8.2 Taxa de Diagnóstico (TD)

A TD é calculada como aproximação:

```
TD ≈ (api_error_rate × throughput × tempo) / worker_injected_total
```

**Esperado:**

- Env A → TD ≈ 1.0 (todos os erros são vistos)
- Env B → TD ≈ 1.0 (a política `errors-policy` mantém 100% dos traces de erro)

Se a TD do Env B cair abaixo de 0.95, há problema na configuração do
tail_sampling.

### 8.3 Latência da aplicação

A diferença de latência entre A e B deve ser **mínima** (<5%). O sampling
ocorre no Collector — não no SDK das aplicações — portanto a aplicação
gera o mesmo trabalho em ambos os ambientes.

Diferenças significativas indicam:
- saturação de recursos
- contenção de rede para o collector

### 8.4 Caveats experimentais

1. **Storage in-memory do Jaeger**: traces são perdidos ao reiniciar.
   Para experimentos longos, troque para `SPAN_STORAGE_TYPE=badger`.
2. **Docker Desktop (Mac/Windows)**: cAdvisor mede a VM Linux, não o
   host real. Métricas de CPU do host serão imprecisas.
3. **Variabilidade**: rode 3+ replicações de cada cenário e use média/IC.
4. **Faults injetados são pseudoaleatórios**: ao rodar com baixa carga,
   poucos faults serão observados. Use `medium` ou `stress` para
   estatística confiável.

---

## 9. Estrutura do projeto

```
observability-overhead-experiment/
├── README.md                          ← este arquivo
│
├── base-system/                       ← código compartilhado entre A e B
│   ├── api/
│   │   ├── app.py                     ← Flask API instrumentada
│   │   ├── otel_config.py             ← setup OpenTelemetry
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── worker/
│   │   ├── worker.py                  ← Worker com injeção de falhas
│   │   ├── otel_config.py             ← (cópia)
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── load-tests/
│       ├── basic.js                   ← k6 - 10 VUs, 1 min
│       ├── medium.js                  ← k6 - 30 VUs, 4 min
│       └── stress.js                  ← k6 - 100 VUs, 8 min
│
├── env-A/                             ← AMBIENTE BASELINE
│   ├── docker-compose.yml             ← stack completo
│   └── otel/
│       └── otel-collector.yaml        ← config sem sampling
│
├── env-B/                             ← AMBIENTE OTIMIZADO
│   ├── docker-compose.yml             ← stack idêntico em recursos
│   └── otel/
│       └── otel-collector.yaml        ← config com tail_sampling + filter
│
├── observability/                     ← compartilhado entre A e B
│   ├── prometheus/
│   │   └── prometheus.yml             ← scraping de tudo
│   ├── grafana/
│   │   ├── provisioning/
│   │   │   ├── datasources/
│   │   │   │   └── datasources.yml
│   │   │   └── dashboards/
│   │   │       └── dashboards.yml
│   │   └── dashboards/
│   │       └── overview.json          ← dashboard pré-carregado
│   └── jaeger/                        ← reservado p/ configs futuras
│
└── experiments/
    ├── raw-data/                      ← saída de cada run
    │   └── env<X>-<load>-<timestamp>/
    │       ├── baseline.csv
    │       ├── metrics.csv
    │       ├── k6-output.log
    │       └── metadata.json
    │
    ├── processed/                     ← análise comparativa
    │   ├── comparison.csv
    │   ├── summary.json
    │   ├── report.md
    │   └── charts/*.png
    │
    └── scripts/
        ├── run_experiment.sh / .ps1   ← roda 1 ambiente + carga
        ├── run_full_experiment.sh / .ps1  ← A + B + análise
        ├── collect_metrics.py         ← Prometheus → CSV
        ├── analyze_results.py         ← CSV → tabelas + gráficos
        └── inject_faults.py           ← injeção externa de falhas
```

---

## 10. Experimentos sugeridos

### 10.1 Roteiro mínimo (TCC/artigo)

Para gerar dados estatisticamente comparáveis, recomenda-se:

```bash
# 3 replicações de cada cenário
for i in 1 2 3; do
    ./experiments/scripts/run_full_experiment.sh medium
done

# Análise final
python3 experiments/scripts/analyze_results.py \
    --raw-dir experiments/raw-data \
    --out-dir experiments/processed
```

Resultado: 6 runs (3×A + 3×B) sob carga média.

### 10.2 Roteiro completo

| Passo | Cenário | Comando | Por quê |
|-------|---------|---------|---------|
| 1 | smoke | `run_experiment.sh A basic` | validar setup |
| 2 | smoke | `run_experiment.sh B basic` | validar Env B |
| 3 | medium ×3 | `run_full_experiment.sh medium` (3x) | dados de regime |
| 4 | stress ×3 | `run_full_experiment.sh stress` (3x) | overhead amplificado |
| 5 | injeção | `inject_faults.py --action pause --target worker --duration 15` | TD em outage |

### 10.3 Variações dignas de investigação

- **Sampling rate**: alterar `sampling_percentage: 10` para 5 / 20 / 50 e
  refazer a análise.
- **Threshold de slow**: alterar `threshold_ms: 1000` no tail_sampling.
- **Carga assimétrica**: gerar carga no `complexity` para enviesar
  distribuição de latência.
- **Jaeger persistente**: trocar storage para Badger e medir overhead
  adicional de I/O.

---

## 11. Referências

- OpenTelemetry Specification — <https://opentelemetry.io/docs/specs/>
- OTel Collector tail_sampling processor — <https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor>
- Sigelman, B. *et al.* — *Dapper, a Large-Scale Distributed Systems Tracing Infrastructure*. Google Technical Report (2010).
- Mace, J. *et al.* — *Pivot Tracing: Dynamic Causal Monitoring for Distributed Systems*. SOSP'15.
- Las-Casas, P. *et al.* — *Sifter: Scalable Sampling for Distributed Traces*. SoCC'19.
- Davis, C. — *Cloud Native Patterns* (2019).
- Burns, B. — *Designing Distributed Systems* (2018).

---

## Licença e uso acadêmico

Este projeto é destinado a uso acadêmico. Os artefatos foram desenhados para
serem **reproduzíveis** — todos os parâmetros estão fixados em variáveis de
ambiente ou nos compose files, e as imagens estão pinadas em versão exata.

Para citar:

> *"Sistema experimental para avaliação de overhead de observabilidade em
> arquitetura distribuída usando OpenTelemetry"*. Trabalho de Conclusão de
> Curso, [Universidade], [Ano].
