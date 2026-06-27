# DirecioZAP — inicializacao local completa
# Rode este script com: powershell -ExecutionPolicy Bypass -File start.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

Write-Host "=== DirecioZAP Start ===" -ForegroundColor Cyan

# 1. Sobe Evolution API + Postgres
Write-Host "`n[1/4] Subindo Evolution API (Docker)..." -ForegroundColor Yellow
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Docker nao esta rodando. Abra o Docker Desktop primeiro." -ForegroundColor Red
    exit 1
}

# Aguarda a Evolution API estar pronta
Write-Host "     Aguardando Evolution API na porta 8080..." -ForegroundColor Gray
$maxTry = 20
for ($i = 0; $i -lt $maxTry; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8080/" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        Write-Host "     Evolution API pronta!" -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 3
    }
    if ($i -eq $maxTry - 1) {
        Write-Host "     Timeout esperando Evolution API." -ForegroundColor Red
    }
}

# 2. Sobe backend FastAPI
Write-Host "`n[2/4] Subindo backend FastAPI (porta 3000)..." -ForegroundColor Yellow
$backend = Start-Process -FilePath "$ROOT\.venv\Scripts\uvicorn.exe" `
    -ArgumentList "main:app --port 3000" `
    -WorkingDirectory $ROOT `
    -PassThru -WindowStyle Minimized
Write-Host "     PID: $($backend.Id)" -ForegroundColor Gray
Start-Sleep -Seconds 2

# 3. Sobe ngrok
Write-Host "`n[3/4] Subindo ngrok (tunelamento porta 3000)..." -ForegroundColor Yellow
$ngrok = Start-Process -FilePath "ngrok" `
    -ArgumentList "http 3000" `
    -PassThru -WindowStyle Minimized
Start-Sleep -Seconds 3

# Pega a URL do ngrok via API local
try {
    $tunnels = (Invoke-WebRequest -Uri "http://localhost:4040/api/tunnels" -UseBasicParsing -TimeoutSec 5 | ConvertFrom-Json)
    $ngrokUrl = ($tunnels.tunnels | Where-Object { $_.proto -eq "https" }).public_url
    Write-Host "     URL publica: $ngrokUrl" -ForegroundColor Green
} catch {
    $ngrokUrl = "http://localhost:4040 (abra para ver a URL)"
    Write-Host "     Abra http://localhost:4040 para ver a URL do ngrok" -ForegroundColor Yellow
}

# 4. Cria instancia + configura webhook na Evolution API
Write-Host "`n[4/4] Configurando Evolution API..." -ForegroundColor Yellow

$API_KEY = (Get-Content "$ROOT\.env" | Where-Object { $_ -match "^EVOLUTION_API_KEY=" }) -replace "EVOLUTION_API_KEY=", ""
$INSTANCE = (Get-Content "$ROOT\.env" | Where-Object { $_ -match "^EVOLUTION_INSTANCE=" }) -replace "EVOLUTION_INSTANCE=", ""
$WEBHOOK_URL = "$ngrokUrl/webhook"

# Cria instancia (ignora erro se ja existir)
try {
    Invoke-RestMethod -Uri "http://localhost:8080/instance/create" `
        -Method POST `
        -Headers @{ "apikey" = $API_KEY; "Content-Type" = "application/json" } `
        -Body (@{ instanceName = $INSTANCE; integration = "WHATSAPP-BAILEYS" } | ConvertTo-Json) `
        -TimeoutSec 10 | Out-Null
    Write-Host "     Instancia '$INSTANCE' criada." -ForegroundColor Green
} catch {
    Write-Host "     Instancia '$INSTANCE' ja existe (ok)." -ForegroundColor Gray
}

# Configura webhook
if ($ngrokUrl -notlike "http://localhost*") {
    try {
        Invoke-RestMethod -Uri "http://localhost:8080/webhook/set/$INSTANCE" `
            -Method POST `
            -Headers @{ "apikey" = $API_KEY; "Content-Type" = "application/json" } `
            -Body (@{
                webhook = @{
                    enabled = $true
                    url = $WEBHOOK_URL
                    events = @("MESSAGES_UPSERT")
                }
            } | ConvertTo-Json -Depth 3) `
            -TimeoutSec 10 | Out-Null
        Write-Host "     Webhook configurado: $WEBHOOK_URL" -ForegroundColor Green
    } catch {
        Write-Host "     Erro ao configurar webhook: $_" -ForegroundColor Red
    }
}

Write-Host "`n=== PRONTO ===" -ForegroundColor Cyan
Write-Host "Backend:      http://localhost:3000" -ForegroundColor White
Write-Host "Evolution UI: http://localhost:8080/manager" -ForegroundColor White
Write-Host "ngrok UI:     http://localhost:4040" -ForegroundColor White
if ($ngrokUrl -notlike "http://localhost*") {
    Write-Host "Webhook URL:  $WEBHOOK_URL" -ForegroundColor White
}
Write-Host "`nProximo passo: conecte o WhatsApp em http://localhost:8080/manager" -ForegroundColor Yellow
Write-Host "  -> Clique na instancia '$INSTANCE' -> Connect -> QR Code" -ForegroundColor Yellow
