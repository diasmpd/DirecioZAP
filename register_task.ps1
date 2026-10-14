# Registra uma Tarefa Agendada do Windows que roda o DirecioZAP em segundo plano
# (bot + ngrok, sem janela) sempre que voce faz logon, e o reinicia se cair.
#
#   Registrar e iniciar:  powershell -ExecutionPolicy Bypass -File register_task.ps1
#   Remover:              powershell -ExecutionPolicy Bypass -File register_task.ps1 -Remove
#
# So roda enquanto este PC estiver ligado e com o seu usuario logado (o Outlook,
# usado no aviso por e-mail, precisa da sua sessao). Logs em logs\.

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$taskName = "DirecioZAP Bot"
$scriptDir = $PSScriptRoot

if ($Remove) {
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Tarefa '$taskName' removida. O bot volta a rodar so pelo Manager."
    exit 0
}

$candidates = @(
    (Join-Path $scriptDir ".venv\Scripts\pythonw.exe"),
    (Join-Path (Split-Path -Parent $scriptDir) ".venv\Scripts\pythonw.exe")
)
$pythonw = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $pythonw) { throw "pythonw.exe nao encontrado em .venv (nesta pasta ou na pasta pai)." }

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "`"$(Join-Path $scriptDir 'run_bot.py')`"" -WorkingDirectory $scriptDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
# Sem limite de duracao; se o processo sair com erro, tenta de novo a cada minuto.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "DirecioZAP: bot de cadastro de fornecedores (WhatsApp) + ngrok em segundo plano" `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName
Write-Host "Tarefa '$taskName' registrada e iniciada. Ela sobe sozinha a cada logon."
Write-Host "Acompanhe em logs\direciozap.log. Para remover: register_task.ps1 -Remove"
