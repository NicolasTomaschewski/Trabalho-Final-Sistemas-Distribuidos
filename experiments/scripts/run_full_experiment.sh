#!/usr/bin/env bash
# =============================================================================
# run_full_experiment.sh - Orquestra todo o experimento: A + B + análise
# =============================================================================
# Roda o cenário desejado em ambos os ambientes e ao final dispara a análise
# comparativa.
#
# Uso:
#   ./run_full_experiment.sh medium
#   ./run_full_experiment.sh stress
#   ./run_full_experiment.sh basic
# =============================================================================
set -euo pipefail

LOAD_TYPE="${1:-medium}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================="
echo "  EXPERIMENTO COMPLETO"
echo "  Carga: $LOAD_TYPE"
echo "========================================="

# Ambiente A
echo ""
echo ">>> AMBIENTE A (BASELINE)"
"$SCRIPT_DIR/run_experiment.sh" A "$LOAD_TYPE"

# Pausa entre ambientes para garantir cleanup
echo ""
echo "Pausa de 30s entre ambientes..."
sleep 30

# Ambiente B
echo ""
echo ">>> AMBIENTE B (OTIMIZADO)"
"$SCRIPT_DIR/run_experiment.sh" B "$LOAD_TYPE"

# Análise comparativa
echo ""
echo ">>> ANÁLISE COMPARATIVA"
python3 "$SCRIPT_DIR/analyze_results.py" \
    --raw-dir "$ROOT_DIR/experiments/raw-data" \
    --out-dir "$ROOT_DIR/experiments/processed"

echo ""
echo "========================================="
echo " EXPERIMENTO COMPLETO CONCLUÍDO"
echo "========================================="
echo "Relatório: $ROOT_DIR/experiments/processed/report.md"
echo "CSV:       $ROOT_DIR/experiments/processed/comparison.csv"
echo "Gráficos:  $ROOT_DIR/experiments/processed/charts/"
