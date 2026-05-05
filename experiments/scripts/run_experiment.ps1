<#
================================================================================
run_experiment.ps1 - Versão PowerShell (Windows) do run_experiment.sh
================================================================================
Uso:
    .\run_experiment.ps1 -Env A -Load medium
    .\run_experiment.ps1 -Env B -Load stress
================================================================================
#>
param(
    [Parameter(Mandatory=$true)][ValidateSet("A","B")][string]$Env,
    [Parameter(Mandatory=$true)][ValidateSet("basic","medium","stress")][string]$Load
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Resolve-Path (Join-Path $ScriptDir "..\..")
$ComposeFile = Join-Path $RootDir "env-$Env\docker-compose.yml"
$RawDataDir  = Join-Path $RootDir "experiments\raw-data"
$Timestamp   = Get-Date -Format "yyyyMMdd-HHmmss"
$RunId       = "env$Env-$Load-$Timestamp"
$RunDir      = Join-Path $RawDataDir $RunId

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

if ($Env -eq "A") { $ApiPort = 8080; $PromPort = 9090 }
else              { $ApiPort = 8090; $PromPort = 9091 }

$ApiUrl  = "http://localhost:$ApiPort"
$PromUrl = "http://localhost:$PromPort"

Write-Host "=================================================================="
Write-Host " EXPERIMENT RUN"
Write-Host "   env:        $Env"
Write-Host "   load:       $Load"
Write-Host "   run_id:     $RunId"
Write-Host "   api_url:    $ApiUrl"
Write-Host "   prom_url:   $PromUrl"
Write-Host "   output:     $RunDir"
Write-Host "=================================================================="

# -----------------------------------------------------------------------------
# 1) Subir ambiente
# -----------------------------------------------------------------------------
Write-Host "[1/6] Subindo ambiente $Env..."
docker compose -f $ComposeFile up -d --build

# -----------------------------------------------------------------------------
# 2) Aguardar health-check
# -----------------------------------------------------------------------------
Write-Host "[2/6] Aguardando API ficar saudavel..."
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        Invoke-WebRequest -Uri "$ApiUrl/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        Write-Host "  API ready (after ${i}s)"
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $ready) {
    Write-Error "API nao ficou saudavel em 60s"
    docker compose -f $ComposeFile logs api
    exit 1
}

Write-Host "  aguardando 10s para collector estabilizar..."
Start-Sleep -Seconds 10

# -----------------------------------------------------------------------------
# 3) Baseline ocioso
# -----------------------------------------------------------------------------
Write-Host "[3/6] Coletando baseline..."
python (Join-Path $ScriptDir "collect_metrics.py") `
    --prom-url $PromUrl `
    --output (Join-Path $RunDir "baseline.csv") `
    --duration 30 `
    --label "baseline" `
    --env $Env

# -----------------------------------------------------------------------------
# 4) Carga k6
# -----------------------------------------------------------------------------
Write-Host "[4/6] Executando carga k6 ($Load)..."
docker compose -f $ComposeFile --profile loadtest run --rm `
    -e API_URL="http://api:8080" `
    -e ENV_LABEL=$Env `
    k6 run "/scripts/$Load.js" `
    --summary-export="/results/summary-$RunId.json" `
    | Tee-Object -FilePath (Join-Path $RunDir "k6-output.log")

# -----------------------------------------------------------------------------
# 5) Pos-teste
# -----------------------------------------------------------------------------
Write-Host "[5/6] Coletando metricas pos-teste..."
python (Join-Path $ScriptDir "collect_metrics.py") `
    --prom-url $PromUrl `
    --output (Join-Path $RunDir "metrics.csv") `
    --duration 60 `
    --label "post-load" `
    --env $Env

# Metadata
$metadata = @{
    run_id         = $RunId
    env            = $Env
    load_type      = $Load
    timestamp      = $Timestamp
    api_url        = $ApiUrl
    prom_url       = $PromUrl
    fault_error_rate = 0.05
    fault_slow_rate  = 0.03
    compose_file   = $ComposeFile
}
$metadata | ConvertTo-Json | Set-Content (Join-Path $RunDir "metadata.json")

# -----------------------------------------------------------------------------
# 6) Tear down
# -----------------------------------------------------------------------------
Write-Host "[6/6] Derrubando ambiente..."
docker compose -f $ComposeFile down -v --remove-orphans

Write-Host ""
Write-Host "=================================================================="
Write-Host " EXPERIMENTO CONCLUIDO"
Write-Host "   Resultados em: $RunDir"
Write-Host "=================================================================="
Get-ChildItem $RunDir
