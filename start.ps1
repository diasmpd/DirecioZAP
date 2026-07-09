# DirecioZAP - inicializacao local para Twilio
# Rode com: powershell -ExecutionPolicy Bypass -File start.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

function Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[AVISO] $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERRO]  $msg" -ForegroundColor Red; exit 1 }

Info "DirecioZAP start (Twilio + ngrok)"

$venvCandidates = @(
    (Join-Path $ROOT ".venv\Scripts\uvicorn.exe"),
    (Join-Path (Split-Path -Parent $ROOT) ".venv\Scripts\uvicorn.exe")
)
$venvUvicorn = $venvCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $venvUvicorn) {
    Fail "Uvicorn nao encontrado em .venv local nem na pasta pai. Instale as dependencias com: .venv\Scripts\python.exe -m pip install -r requirements.txt"
}

$envPath = Join-Path $ROOT ".env"
if (-not (Test-Path $envPath)) {
    Fail "Arquivo .env nao encontrado. Copie .env.example para .env e preencha as credenciais."
}

$envMap = @{}
Get-Content $envPath | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    $parts = $_ -split "=", 2
    if ($parts.Count -eq 2) {
        $envMap[$parts[0].Trim()] = $parts[1].Trim()
    }
}

if (-not $envMap.ContainsKey("TWILIO_ACCOUNT_SID") -or -not $envMap["TWILIO_ACCOUNT_SID"]) {
    Fail "TWILIO_ACCOUNT_SID nao configurado no .env"
}
if (-not $envMap.ContainsKey("TWILIO_AUTH_TOKEN") -or -not $envMap["TWILIO_AUTH_TOKEN"]) {
    Fail "TWILIO_AUTH_TOKEN nao configurado no .env"
}
if (-not $envMap.ContainsKey("SUPABASE_URL") -or -not $envMap["SUPABASE_URL"]) {
    Fail "SUPABASE_URL nao configurado no .env"
}
if (-not $envMap.ContainsKey("SUPABASE_KEY") -or -not $envMap["SUPABASE_KEY"]) {
    Fail "SUPABASE_KEY nao configurado no .env"
}

$ngrokCmd = Get-Command ngrok -ErrorAction SilentlyContinue
if (-not $ngrokCmd) {
    Fail "ngrok nao encontrado no PATH. Instale com: winget install Ngrok.Ngrok"
}

if ($envMap.ContainsKey("NGROK_AUTH_TOKEN") -and $envMap["NGROK_AUTH_TOKEN"]) {
    try {
        & ngrok config add-authtoken $envMap["NGROK_AUTH_TOKEN"] | Out-Null
        Ok "NGROK_AUTH_TOKEN aplicado"
    } catch {
        Warn "Falha ao aplicar NGROK_AUTH_TOKEN. Continuando sem atualizar config do ngrok."
    }
}

Info "[1/3] Subindo backend FastAPI na porta 3000"
$backend = Start-Process -FilePath $venvUvicorn `
    -ArgumentList "main:app --host 0.0.0.0 --port 3000" `
    -WorkingDirectory $ROOT `
    -PassThru -WindowStyle Minimized
Ok "Backend iniciado (PID $($backend.Id))"

Info "[2/3] Subindo ngrok"
$ngrokArgs = "http 3000"
if ($envMap.ContainsKey("NGROK_DOMAIN") -and $envMap["NGROK_DOMAIN"]) {
    $ngrokArgs = "http 3000 --domain=$($envMap['NGROK_DOMAIN'])"
}
$ngrokProc = Start-Process -FilePath "ngrok" -ArgumentList $ngrokArgs -PassThru -WindowStyle Minimized
Ok "ngrok iniciado (PID $($ngrokProc.Id))"

Info "[3/3] Coletando URL publica"
$ngrokUrl = $null
for ($i = 0; $i -lt 15; $i++) {
    try {
        $tunnels = Invoke-WebRequest -Uri "http://localhost:4040/api/tunnels" -UseBasicParsing -TimeoutSec 3 | ConvertFrom-Json
        $ngrokUrl = ($tunnels.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1).public_url
        if ($ngrokUrl) { break }
    } catch {
        # espera proximo ciclo
    }
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "=== PRONTO ===" -ForegroundColor Cyan
Write-Host "Backend:  http://localhost:3000" -ForegroundColor White
Write-Host "ngrok UI: http://localhost:4040" -ForegroundColor White
if ($ngrokUrl) {
    Write-Host "Webhook:  $ngrokUrl/webhook" -ForegroundColor Green
    Write-Host ""
    Write-Host "Configure esta URL no Twilio Sandbox > When a message comes in:" -ForegroundColor Yellow
    Write-Host "  $ngrokUrl/webhook" -ForegroundColor Yellow
} else {
    Warn "Nao foi possivel detectar a URL publica. Abra http://localhost:4040 e copie manualmente o webhook (/webhook)."
}

Write-Host ""
Write-Host "Para parar os processos: encerre os PIDs $($backend.Id) e $($ngrokProc.Id) no Gerenciador de Tarefas." -ForegroundColor Gray
