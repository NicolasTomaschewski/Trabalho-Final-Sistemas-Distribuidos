# Execução do Experimento

## Pré-requisitos

- Docker Engine 24.0+
- Docker Compose v2.20+
- Python 3.10+

---

## Experimento completo (recomendado)

Roda Env A + Env B + análise comparativa em sequência:

```bash
cd experiments/scripts
bash run_full_experiment.sh medium
```

Os resultados ficam em:
- `experiments/processed/report.md` — relatório com tabelas
- `experiments/processed/comparison.csv` — dados brutos consolidados
- `experiments/processed/charts/` — gráficos gerados

---

## Rodar cada ambiente separadamente

```bash
cd experiments/scripts

# Ambiente A (baseline)
bash run_experiment.sh A medium

# Ambiente B (otimizado)
bash run_experiment.sh B medium
```

---

## Só gerar a análise (sem rodar experimento)

Usa os dados brutos já existentes em `experiments/raw-data/`:

```bash
python3 experiments/scripts/analyze_results.py \
    --raw-dir experiments/raw-data \
    --out-dir experiments/processed
```

---

## Subir/derrubar ambientes manualmente

```bash
# Env A — API em :8080, Prometheus em :9090, Grafana em :3000
docker compose -f env-A/docker-compose.yml up -d --build
docker compose -f env-A/docker-compose.yml down -v

# Env B — API em :8090, Prometheus em :9091, Grafana em :3001
docker compose -f env-B/docker-compose.yml up -d --build
docker compose -f env-B/docker-compose.yml down -v
```

Verificar saúde:

```bash
curl http://localhost:8080/health   # Env A
curl http://localhost:8090/health   # Env B
```

---

## Perfis de carga disponíveis

Substitua `medium` por `basic` ou `stress` em qualquer comando acima.

| Perfil | Descrição |
|---|---|
| `basic` | Carga leve, ideal para validar o ambiente |
| `medium` | Carga moderada, usada nos experimentos do artigo |
| `stress` | Carga alta, para testar limites |
