#!/usr/bin/env bash
# =============================================================================
# run_experiment.sh - Roda um experimento completo
# =============================================================================
# Sobe o ambiente, espera health-checks, executa carga k6, coleta métricas
# do Prometheus e salva em CSV. Fecha o ambiente ao final.
#
# Uso:
#   ./run_experiment.sh A medium
#   ./run_experiment.sh B medium
#   ./run_experiment.sh A stress
#
# Args:
#   $1 = ambiente (A ou B)
#   $2 = tipo de carga (basic | medium | stress)
# =============================================================================
set -euo pipefail

ENV_NAME="${1:?uso: $0 <A|B> <basic|medium|stress>}"
LOAD_TYPE="${2:?uso: $0 <A|B> <basic|medium|stress>}"

if [[ "$ENV_NAME" != "A" && "$ENV_NAME" != "B" ]]; then
    echo "ERRO: ambiente deve ser A ou B" >&2
    exit 1
fi

if [[ ! "$LOAD_TYPE" =~ ^(basic|medium|stress)$ ]]; then
    echo "ERRO: load deve ser basic, medium ou stress" >&2
    exit 1
fi

# Diretórios
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/env-${ENV_NAME}/docker-compose.yml"
RAW_DATA_DIR="$ROOT_DIR/experiments/raw-data"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
RUN_ID="env${ENV_NAME}-${LOAD_TYPE}-${TIMESTAMP}"
RUN_DIR="$RAW_DATA_DIR/$RUN_ID"

mkdir -p "$RUN_DIR"

# Portas variam por ambiente
if [[ "$ENV_NAME" == "A" ]]; then
    API_PORT=8080
    PROM_PORT=9090
else
    API_PORT=8090
    PROM_PORT=9091
fi

API_URL="http://localhost:${API_PORT}"
PROM_URL="http://localhost:${PROM_PORT}"

echo "=================================================================="
echo " EXPERIMENT RUN"
echo "   env:        $ENV_NAME"
echo "   load:       $LOAD_TYPE"
echo "   run_id:     $RUN_ID"
echo "   api_url:    $API_URL"
echo "   prom_url:   $PROM_URL"
echo "   output:     $RUN_DIR"
echo "=================================================================="

# -----------------------------------------------------------------------------
# 1) Subir ambiente
# -----------------------------------------------------------------------------
echo "[1/6] Subindo ambiente $ENV_NAME..."
docker compose -f "$COMPOSE_FILE" up -d --build

# -----------------------------------------------------------------------------
# 2) Aguardar health-check da API
# -----------------------------------------------------------------------------
echo "[2/6] Aguardando API ficar saudável..."
for i in {1..30}; do
    if curl -sf "$API_URL/health" >/dev/null 2>&1; then
        echo "  API ready (after ${i}s)"
        break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
        echo "ERRO: API não ficou saudável em 60s" >&2
        docker compose -f "$COMPOSE_FILE" logs api
        exit 1
    fi
done

# Aguarda alguns segundos extras para o collector estabilizar
echo "  aguardando 10s para collector estabilizar..."
sleep 10

# -----------------------------------------------------------------------------
# 3) Snapshot pré-teste (baseline ocioso)
# -----------------------------------------------------------------------------
echo "[3/6] Coletando baseline (sistema ocioso)..."
python3 "$SCRIPT_DIR/collect_metrics.py" \
    --prom-url "$PROM_URL" \
    --output "$RUN_DIR/baseline.csv" \
    --duration 30 \
    --label "baseline" \
    --env "$ENV_NAME"

# -----------------------------------------------------------------------------
# 4) Rodar k6
# -----------------------------------------------------------------------------
echo "[4/6] Executando carga k6 ($LOAD_TYPE)..."
docker compose -f "$COMPOSE_FILE" --profile loadtest run --rm \
    -e API_URL="http://api:8080" \
    -e ENV_LABEL="$ENV_NAME" \
    k6 run "/scripts/${LOAD_TYPE}.js" \
    --summary-export="/results/summary-${RUN_ID}.json" \
    | tee "$RUN_DIR/k6-output.log"

# -----------------------------------------------------------------------------
# 5) Coletar métricas pós-teste
# -----------------------------------------------------------------------------
echo "[5/6] Coletando métricas do Prometheus..."
python3 "$SCRIPT_DIR/collect_metrics.py" \
    --prom-url "$PROM_URL" \
    --output "$RUN_DIR/metrics.csv" \
    --duration 60 \
    --label "post-load" \
    --env "$ENV_NAME"

# Salva metadados do experimento
cat > "$RUN_DIR/metadata.json" <<EOF
{
  "run_id":         "$RUN_ID",
  "env":            "$ENV_NAME",
  "load_type":      "$LOAD_TYPE",
  "timestamp":      "$TIMESTAMP",
  "api_url":        "$API_URL",
  "prom_url":       "$PROM_URL",
  "fault_error_rate": 0.05,
  "fault_slow_rate":  0.03,
  "compose_file":   "$COMPOSE_FILE"
}
EOF

# -----------------------------------------------------------------------------
# 6) Tear down
# -----------------------------------------------------------------------------
echo "[6/6] Derrubando ambiente..."
docker compose -f "$COMPOSE_FILE" down -v --remove-orphans

echo ""
echo "=================================================================="
echo " EXPERIMENTO CONCLUÍDO"
echo "   Resultados em: $RUN_DIR"
echo "=================================================================="
ls -la "$RUN_DIR"
