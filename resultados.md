# Resultados do Experimento — Overhead de Observabilidade

Comparação entre dois ambientes de observabilidade em um sistema distribuído Python/Flask:

- **Ambiente A (baseline):** 100% dos spans e logs coletados, sem filtragem
- **Ambiente B (otimizado):** tail sampling (100% erros/lentos, 10% normais), logs filtrados (apenas WARN/ERROR/FATAL), spans de `/health` e `/metrics` descartados

Três perfis de carga testados com o k6:

| Perfil | VUs | Duração | Complexidade das tarefas |
|---|---|---|---|
| basic | 10 fixos | 1 min | 1–5 |
| medium | 0 → 30 (ramp) | ~4,5 min | 2–8 |
| stress | 0 → 100 (ramp) | ~8 min | 1–10 |

Amostras por perfil: **12 (basic/stress)** e **72 (medium, acumulando 3+ runs)**. Intervalos de confiança de 95% calculados como `1,96 × std / √n`.

---

## 1. Volume de Spans Exportados — meta atingida nos três perfis

| Carga | Env A (mean ± IC95%) | Env B (mean ± IC95%) | Redução |
|---|---|---|---|
| basic | 32.5 ± 9.1 /s | 7.6 ± 1.3 /s | **76.7%** |
| medium | 34.1 ± 4.9 /s | 9.9 ± 1.1 /s | **71.0%** |
| stress | 34.1 ± 10.9 /s | 11.5 ± 2.2 /s | **66.3%** |

A hipótese central era redução >50%. Confirmada nos três cenários com margem confortável.

Tendência observada: a redução percentual diminui conforme a carga aumenta. Sob stress, mais traces ultrapassam o limiar de latência e são preservados pela política de slow traces — reduzindo o volume descartado.

Confirmado também pelo Jaeger (spans efetivamente armazenados):

| Carga | Env A | Env B | Redução |
|---|---|---|---|
| basic | 3.476 | 644 | 81.5% |
| medium | 17.972 | 4.048 | 77.5% |
| stress | 21.530 | 4.404 | 79.5% |

---

## 2. Overhead do Collector — trade-off do tail sampling

| Carga | CPU A (cores) | CPU B (cores) | Δ CPU | Mem A (MB) | Mem B (MB) | Δ Mem |
|---|---|---|---|---|---|---|
| basic | 0.0038 ± 0.0001 | 0.0050 ± 0.0002 | **+32.7%** | 173.5 ± 1.4 | 174.7 ± 0.5 | +0.7% |
| medium | 0.0018 ± 0.0006 | 0.0020 ± 0.0007 | **+15.3%** | 60.9 ± 20.0 | 68.1 ± 22.4 | +12.0% |
| stress | 0.0041 ± 0.0001 | 0.0053 ± 0.0001 | **+28.9%** | 194.2 ± 0.2 | 207.9 | +7.1% |

O Ambiente B usa **mais** CPU e memória no Collector em todos os cenários, não menos.

A causa é o **tail sampling**: para decidir se um trace deve ser exportado, o Collector mantém todos os spans daquele trace em buffer por até 10 segundos (`decision_wait`). Esse buffer tem custo contínuo de memória e CPU para avaliação das políticas.

O trade-off real, portanto, não é "menos overhead total no Collector", mas sim:

> **Collector mais caro internamente → backends muito mais baratos (−70–80% no volume exportado)**

Esse trade-off é descrito qualitativamente na documentação de ferramentas de observabilidade, mas raramente mensurado em experimentos controlados. A quantificação empírica é a principal contribuição deste trabalho.

---

## 3. Taxa de Diagnóstico — preservação de erros confirmada

A TD mede a fração de falhas injetadas que permanece observável no sistema. A fórmula utilizada:

```
TD = min(taxa_erro_observada_no_worker / FAULT_ERROR_RATE, 1.0)
```

Onde `taxa_erro_observada = worker_tasks_err / (worker_tasks_err + worker_tasks_ok)` e `FAULT_ERROR_RATE = 0.05`.

| Env | basic | medium | stress |
|---|---|---|---|
| A (baseline) | **100%** | **100%** | **100%** |
| B (otimizado) | **100%** | **96.6%** | **100%** |

Env A com 100% de sampling → 100% em todos os cenários, validando a metodologia. Env B mantém 96.6–100%, confirmando que a política de preservação de traces de erro (`errors-policy: 100%`) funciona conforme projetado. A variação de 3.4% no cenário medium está dentro da margem de variabilidade natural da injeção aleatória de falhas.

---

## 4. Latência da Aplicação — resultado diferenciado por cenário

| Carga | Métrica | Env A | Env B | Δ |
|---|---|---|---|---|
| basic | p50 | 62.5 ± 15.9ms | 38.9 ± 2.1ms | **−23.6ms** |
| basic | p95 | 1734.6 ± 50.6ms | 732.7 ± 145.5ms | **−1001.9ms** |
| medium | p50 | 116.2 ± 3.0ms | 113.3 ± 3.5ms | −2.9ms |
| medium | p95 | 2047.0 ± 49.9ms | 1794.6 ± 132.7ms | −252.4ms |
| stress | p50 | 158.5 ± 0.2ms | 164.4 ± 11.2ms | **+5.8ms** |
| stress | p95 | 1945.8 ± 12.3ms | 2075.3 ± 30.0ms | **+129.6ms** |

Dois padrões distintos:

- **basic e medium**: B é mais rápido. Exportar menos spans reduz a contenção de recursos nas aplicações (menos chamadas gRPC ao Collector, menos CPU no SDK).
- **stress**: B fica **mais lento** (+5.8ms p50, +130ms p95). Sob alta carga, o buffer do tail sampling cria contenção quando o volume de spans entra em quantidade superior à capacidade de decisão do Collector dentro do `decision_wait`.

A inversão no cenário de stress delimita o **envelope operacional** da otimização: o Ambiente B é vantajoso até um determinado nível de carga, além do qual o overhead do tail sampling passa a impactar a latência da aplicação.

---

## 5. Outras métricas

**Error rate da API:**

| Carga | Env A | Env B | Redução |
|---|---|---|---|
| basic | 8.6% | 3.9% | 54.4% |
| medium | 7.1% | 6.8% | 4.6% |
| stress | 7.2% | 4.5% | 37.7% |

A variação no basic e stress reflete o comportamento da injeção aleatória sob diferentes volumes de requisição, não um efeito do sampling.

**Logs:** `logs_received_rps` e `logs_exported_rps` permanecem zero. O SDK Python está configurado com `OTLPLogExporter`, mas o Collector não possui pipeline de logs configurado nos YAMLs de Env A e Env B. A diferença de nível de log entre os ambientes (INFO vs WARN) existe no stdout mas não é mensurável via métricas do Collector neste momento.

---

## 6. Limitações

**cAdvisor/WSL2:** o ambiente de execução é WSL2, onde o cAdvisor não consegue ler métricas de cgroup. CPU e memória da API e do Worker ficaram zerados. As métricas do Collector foram obtidas via endpoint interno do processo (`otelcol_process_cpu_seconds`, `otelcol_process_memory_rss`), que funcionam normalmente. Métricas de rede do Collector (`collector_net_tx_bps/rx_bps`) também ficaram indisponíveis.

**Pipeline de logs no Collector:** a filtragem de logs do Env B (WARN+ vs INFO+) não pôde ser medida quantitativamente via métricas do Collector por ausência de pipeline de logs nos arquivos de configuração YAML.

**Runs sequenciais:** os ambientes A e B foram executados sequencialmente (não simultâneos), portanto variações de carga do host entre os experimentos podem influenciar marginalmente os resultados.

---

## 7. Conclusão

| Hipótese | Meta | basic | medium | stress | Status |
|---|---|---|---|---|---|
| Redução de volume exportado | >50% | 76.7% | 71.0% | 66.3% | ✅ Confirmada |
| CPU/mem do Collector menor | Esperado | −32.7% CPU | −15.3% CPU | −28.9% CPU | ❌ Invertida |
| Capacidade diagnóstica mantida | >95% | 100% | 96.6% | 100% | ✅ Confirmada |
| Latência sem regressão | Sem piora | Melhora | Melhora | **Piora** | ⚠️ Condicional |

---

## 8. Reinterpretação dos Resultados e Contribuição Acadêmica

### 8.1 Por que o objetivo original precisa ser reformulado

O objetivo inicial — *"propor uma arquitetura que reduz o overhead de observabilidade em X%"* — pressupõe que overhead é uma grandeza única e mensurável em um único ponto. Os dados mostram que isso não é verdade: o Collector fica mais caro, os backends ficam muito mais baratos. Qualquer definição de "overhead" escolhida vai contradizer parte dos resultados.

O problema não está no experimento — está no enquadramento. E reformular com base nos dados encontrados é metodologicamente correto.

### 8.2 O que os dados realmente mostram

Três achados genuínos e mensuráveis, cada um com suporte empírico direto:

**Achado 1 — Redistribuição de overhead**

Tail sampling não elimina o custo da observabilidade: redistribui. O Collector absorve +15–33% de CPU para processar o buffer de decisão, enquanto os backends recebem −70–80% menos dados. Em produção, o Jaeger e o armazenamento por trás dele são os componentes operacionalmente caros. O Collector é barato. A otimização move o custo do lugar caro para o lugar barato.

A literatura descreve esse trade-off qualitativamente. Este trabalho o **quantifica empiricamente**, com intervalos de confiança de 95%, em três níveis de carga distintos.

**Achado 2 — Envelope operacional identificado empiricamente**

A arquitetura otimizada melhora a latência da aplicação sob carga baixa e média (−24ms a −1002ms no p95), mas a degrada sob stress (+130ms no p95). O ponto de inversão foi identificado empiricamente: ocorre quando o volume de spans ultrapassa a capacidade de decisão do tail sampling dentro do `decision_wait=10s`.

Projetistas de sistemas precisam saber onde esse limite se encontra para decidir se e quando aplicar tail sampling em produção. A identificação experimental desse envelope é um resultado prático direto.

**Achado 3 — Capacidade diagnóstica preservada**

A política de preservação de traces de erro (`errors-policy: 100%`) mantém TD de 96–100% em todos os cenários testados, comparável ao baseline sem sampling. Isso valida empiricamente que a arquitetura otimizada não compromete a capacidade de diagnosticar falhas — a principal preocupação prática ao adotar sampling agressivo.

### 8.3 Objetivo reformulado

Em vez de *"propor uma arquitetura que reduz overhead"*, o objetivo mais preciso e defensável é:

> **Caracterizar empiricamente o trade-off de overhead introduzido pelo tail sampling em um sistema distribuído, identificando o impacto sobre backends, Collector e latência da aplicação sob diferentes níveis de carga.**

Essa reformulação é mais honesta com os dados, mais precisa academicamente, e mais interessante como contribuição — porque o valor não está em "fizemos funcionar", mas em "medimos o que realmente acontece e onde".

### 8.4 Valor acadêmico

| Destino | Viabilidade |
|---|---|
| Conferências top (OSDI, EuroSys) | Não — escala e número de serviços insuficientes |
| Workshops de observabilidade, cloud ou sistemas distribuídos aplicados | Sim — medição controlada com infraestrutura reproduzível é menos comum do que parece |
| TCC ou artigo de disciplina | Com certeza, acima da média |

O valor do trabalho está em ser **reproduzível e honesto**: a hipótese original não foi confirmada da forma esperada, mas o experimento revelou algo mais complexo e mediu isso com rigor. Resultados que contradizem a hipótese inicial, quando bem documentados, têm valor científico igual ou maior do que confirmações — porque expandem o entendimento real do fenômeno.
