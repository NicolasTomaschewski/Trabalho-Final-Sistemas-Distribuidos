#!/usr/bin/env python3
"""
================================================================================
analyze_results.py - Análise comparativa Env A vs Env B
================================================================================
Lê todos os CSVs de raw-data/, calcula:

    1) Redução de Overhead (RO):
       RO = ((Overhead_A - Overhead_B) / Overhead_A) * 100

       Calculada para:
       - CPU do collector
       - Memória do collector
       - Bytes de rede TX/RX do collector
       - Volume de spans exportados
       - Volume de logs exportados

    2) Taxa de Diagnóstico (TD):
       TD = falhas_detectadas / falhas_injetadas

       'falhas_detectadas' é estimada por:
         - traces com erro presentes no Jaeger (consultando o exporter)
         - logs ERROR/WARN exportados

    3) Estatísticas resumidas (média, p50, p95, p99) por métrica/ambiente

Saídas:
    - experiments/processed/comparison.csv         (tabela)
    - experiments/processed/summary.json           (overview)
    - experiments/processed/charts/*.png           (gráficos comparativos)
    - experiments/processed/report.md              (relatório markdown)

Uso:
    python analyze_results.py --raw-dir experiments/raw-data \
                              --out-dir experiments/processed
================================================================================
"""

import argparse
import csv
import json
import math
import os
import statistics
from pathlib import Path
from collections import defaultdict


def read_csv(path: Path):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def to_float(x):
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def stats(values):
    """Retorna {'mean','p50','p95','p99','min','max','n'} ignorando None."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "p50": None, "p95": None, "p99": None,
                "min": None, "max": None}
    vals_sorted = sorted(vals)
    n = len(vals_sorted)
    def pct(p):
        idx = max(0, min(n - 1, int(round(p * (n - 1)))))
        return vals_sorted[idx]
    return {
        "n":    n,
        "mean": statistics.fmean(vals),
        "p50":  pct(0.50),
        "p95":  pct(0.95),
        "p99":  pct(0.99),
        "min":  vals_sorted[0],
        "max":  vals_sorted[-1],
    }


def aggregate_runs(raw_dir: Path):
    """
    Lê todos os runs e agrupa por (env, load_type).
    Retorna { (env, load): { metric_name: [values...] } }
    """
    grouped = defaultdict(lambda: defaultdict(list))

    for run_dir in sorted(raw_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        meta_path = run_dir / "metadata.json"
        metrics_path = run_dir / "metrics.csv"
        if not meta_path.exists() or not metrics_path.exists():
            continue

        meta = json.loads(meta_path.read_text())
        env = meta.get("env", "?")
        load = meta.get("load_type", "?")
        rows = read_csv(metrics_path)
        if not rows:
            continue

        # Apenas amostras de 'post-load' contam para overhead com carga
        for row in rows:
            if row.get("label") != "post-load":
                continue
            for k, v in row.items():
                if k in ("timestamp", "label", "env"):
                    continue
                fv = to_float(v)
                grouped[(env, load)][k].append(fv)

    return grouped


def reduction(a, b):
    """RO = ((A - B) / A) * 100. Retorna None se A inválido."""
    if a is None or a == 0:
        return None
    if b is None:
        return None
    return ((a - b) / a) * 100.0


def build_comparison(grouped):
    """
    Para cada (load, metric), calcula RO de A->B usando a média.
    Retorna lista de dicts.
    """
    loads = sorted({load for (env, load) in grouped.keys()})
    metrics = set()
    for d in grouped.values():
        metrics.update(d.keys())
    metrics = sorted(metrics)

    rows = []
    for load in loads:
        a_data = grouped.get(("A", load), {})
        b_data = grouped.get(("B", load), {})
        for m in metrics:
            sa = stats(a_data.get(m, []))
            sb = stats(b_data.get(m, []))
            ro = reduction(sa["mean"], sb["mean"])
            rows.append({
                "load":       load,
                "metric":     m,
                "A_mean":     sa["mean"],
                "A_p95":      sa["p95"],
                "A_n":        sa["n"],
                "B_mean":     sb["mean"],
                "B_p95":      sb["p95"],
                "B_n":        sb["n"],
                "RO_percent": ro,
            })
    return rows


def diagnostic_rate(grouped):
    """
    TD = falhas_detectadas / falhas_injetadas, por (env, load).

    falhas_injetadas: soma de worker_injected_total (ground truth)
    falhas_detectadas: aproximada como total de spans exportados de erro
                       (api_error_rate * api_throughput * tempo) somada com
                       logs_exported (filtros do Env B mantém ERROR/WARN).

    Em produção real isto seria medido contra o Jaeger; aqui usamos
    uma proxy via Prometheus.
    """
    out = {}
    for (env, load), data in grouped.items():
        injected = stats(data.get("worker_injected_total", []))["max"] or 0
        # Spans exportados (rate -> integral aproximada via mean * janela)
        spans_exp_mean = stats(data.get("spans_exported_rps", []))["mean"] or 0
        # Janela aproximada = n_amostras * intervalo (5s default)
        n = stats(data.get("spans_exported_rps", []))["n"]
        window = n * 5
        spans_total_estimate = spans_exp_mean * window

        # Erros detectados ~= (taxa de erro vista no API) * throughput * janela
        err_rate_mean = stats(data.get("api_error_rate", []))["mean"] or 0
        api_rps_mean = stats(data.get("api_throughput_rps", []))["mean"] or 0
        detected = err_rate_mean * api_rps_mean * window

        td = (detected / injected) if injected > 0 else None
        out[(env, load)] = {
            "injected_total":    injected,
            "detected_estimate": detected,
            "spans_exported_total_est": spans_total_estimate,
            "TD":                td,
        }
    return out


def write_csv(rows, path):
    if not rows:
        path.write_text("")
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def render_charts(comparison, out_dir):
    """Gera gráficos comparativos. matplotlib opcional."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib não instalado - pulando gráficos")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    # Métricas-chave a plotar
    key_metrics = [
        "collector_cpu_cores",
        "collector_mem_mb",
        "collector_net_tx_bps",
        "spans_exported_rps",
        "logs_exported_rps",
        "api_latency_p95_s",
    ]

    for metric in key_metrics:
        loads = sorted({r["load"] for r in comparison if r["metric"] == metric})
        if not loads:
            continue
        a_vals = []
        b_vals = []
        for L in loads:
            a = next((r["A_mean"] for r in comparison if r["load"] == L and r["metric"] == metric), 0) or 0
            b = next((r["B_mean"] for r in comparison if r["load"] == L and r["metric"] == metric), 0) or 0
            a_vals.append(a)
            b_vals.append(b)

        x = range(len(loads))
        w = 0.35
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar([i - w/2 for i in x], a_vals, w, label="Env A (baseline)", color="#d62728")
        ax.bar([i + w/2 for i in x], b_vals, w, label="Env B (otimizado)", color="#2ca02c")
        ax.set_xticks(list(x))
        ax.set_xticklabels(loads)
        ax.set_title(f"{metric} - A vs B")
        ax.set_ylabel(metric)
        ax.legend()
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        fig.tight_layout()
        fig.savefig(out_dir / f"{metric}.png", dpi=120)
        plt.close(fig)
        print(f"  gráfico: {metric}.png")


def write_report(comparison, td, out_path):
    """Gera relatório markdown."""
    lines = []
    lines.append("# Relatório do Experimento - Overhead de Observabilidade\n")
    lines.append("Comparação Ambiente A (baseline) vs Ambiente B (otimizado)\n")

    # ----- Redução de Overhead -----
    lines.append("\n## 1. Redução de Overhead (RO)\n")
    lines.append("| Carga | Métrica | A (mean) | B (mean) | RO % |")
    lines.append("|-------|---------|---------:|---------:|-----:|")
    key_metrics = [
        "collector_cpu_cores",
        "collector_mem_mb",
        "collector_net_tx_bps",
        "spans_exported_rps",
        "logs_exported_rps",
    ]
    for r in comparison:
        if r["metric"] not in key_metrics:
            continue
        a = r["A_mean"]
        b = r["B_mean"]
        ro = r["RO_percent"]
        a_s = f"{a:.4f}" if a is not None else "-"
        b_s = f"{b:.4f}" if b is not None else "-"
        ro_s = f"{ro:+.2f}%" if ro is not None else "-"
        lines.append(f"| {r['load']} | {r['metric']} | {a_s} | {b_s} | {ro_s} |")

    # ----- Taxa de Diagnóstico -----
    lines.append("\n## 2. Taxa de Diagnóstico (TD)\n")
    lines.append("| Env | Load | Injetadas | Detectadas (est.) | TD |")
    lines.append("|-----|------|----------:|------------------:|---:|")
    for (env, load), v in sorted(td.items()):
        td_s = f"{v['TD']:.2%}" if v['TD'] is not None else "-"
        lines.append(f"| {env} | {load} | {v['injected_total']:.0f} | "
                     f"{v['detected_estimate']:.1f} | {td_s} |")

    # ----- Latência (não deve degradar entre A e B) -----
    lines.append("\n## 3. Latência da Aplicação\n")
    lines.append("| Carga | Métrica | A | B | Δ |")
    lines.append("|-------|---------|--:|--:|--:|")
    for r in comparison:
        if r["metric"] not in ("api_latency_p50_s", "api_latency_p95_s",
                                "api_latency_p99_s"):
            continue
        a = r["A_mean"]; b = r["B_mean"]
        delta = (b - a) if (a is not None and b is not None) else None
        a_s = f"{a*1000:.1f}ms" if a else "-"
        b_s = f"{b*1000:.1f}ms" if b else "-"
        d_s = f"{delta*1000:+.1f}ms" if delta is not None else "-"
        lines.append(f"| {r['load']} | {r['metric']} | {a_s} | {b_s} | {d_s} |")

    out_path.write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    raw = Path(args.raw_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Lendo runs de {raw} ...")
    grouped = aggregate_runs(raw)
    if not grouped:
        print("ERRO: nenhum run encontrado em raw-data/", flush=True)
        return 1
    print(f"  encontrados runs: {sorted(grouped.keys())}")

    print("Calculando comparação A vs B ...")
    comparison = build_comparison(grouped)
    write_csv(comparison, out / "comparison.csv")
    print(f"  salvo: {out/'comparison.csv'}")

    print("Calculando Taxa de Diagnóstico ...")
    td = diagnostic_rate(grouped)
    summary = {
        "diagnostic_rate": {f"{e}-{l}": v for (e, l), v in td.items()},
        "n_runs": {f"{e}-{l}": stats(grouped[(e, l)].get("collector_cpu_cores", []))["n"]
                   for (e, l) in grouped},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"  salvo: {out/'summary.json'}")

    print("Renderizando gráficos ...")
    render_charts(comparison, out / "charts")

    print("Gerando relatório markdown ...")
    write_report(comparison, td, out / "report.md")
    print(f"  salvo: {out/'report.md'}")
    print("\nConcluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
