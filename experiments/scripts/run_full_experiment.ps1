<#
================================================================================
run_full_experiment.ps1 - Orquestrador completo (Windows)
================================================================================
Uso:
    .\run_full_experiment.ps1 -Load medium
================================================================================
#>
param(
    [Parameter(Mandatory=$false)][ValidateSet("basic","medium","stress")]
    [string]$Load = "medium"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Resolve-Path (Join-Path $ScriptDir "..\..")

Write-Host "========================================="
Write-Host "  EXPERIMENTO COMPLETO"
Write-Host "  Carga: $Load"
Write-Host "========================================="

# Ambiente A
Write-Host ""
Write-Host ">>> AMBIENTE A (BASELINE)"
& (Join-Path $ScriptDir "run_experiment.ps1") -Env A -Load $Load

Write-Host ""
Write-Host "Pausa de 30s entre ambientes..."
Start-Sleep -Seconds 30

# Ambiente B
Write-Host ""
Write-Host ">>> AMBIENTE B (OTIMIZADO)"
& (Join-Path $ScriptDir "run_experiment.ps1") -Env B -Load $Load

# Análise
Write-Host ""
Write-Host ">>> ANALISE COMPARATIVA"
python (Join-Path $ScriptDir "analyze_results.py") `
    --raw-dir (Join-Path $RootDir "experiments\raw-data") `
    --out-dir (Join-Path $RootDir "experiments\processed")

Write-Host ""
Write-Host "========================================="
Write-Host " EXPERIMENTO COMPLETO CONCLUIDO"
Write-Host "========================================="
Write-Host "Relatorio:  $RootDir\experiments\processed\report.md"
Write-Host "CSV:        $RootDir\experiments\processed\comparison.csv"
Write-Host "Graficos:   $RootDir\experiments\processed\charts\"
