# Tarefas agendadas do DirecioZAP neste PC.
#
# Padrao (bot na nuvem/Render): registra "DirecioZAP Avisos", que a cada 5 minutos envia
# pelo Outlook os avisos de novos cadastros e mantem o bot do Render acordado.
#   powershell -ExecutionPolicy Bypass -File register_task.ps1
#
# Bot local (sem Render; so funciona fora da rede corporativa, que bloqueia a Meta):
# registra "DirecioZAP Bot", que roda bot + ngrok em segundo plano a cada logon.
#   powershell -ExecutionPolicy Bypass -File register_task.ps1 -BotLocal
#
# Remover as duas:
#   powershell -ExecutionPolicy Bypass -File register_task.ps1 -Remove
#
# So rodam com o PC ligado e o seu usuario logado (o Outlook precisa da sua sessao).

param([switch]$Remove, [switch]$BotLocal)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$botTask = "DirecioZAP Bot"
$avisosTask = "DirecioZAP Avisos"

function Remove-IfExists($name) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Tarefa '$name' removida."
    }
}

if ($Remove) {
    Remove-IfExists $botTask
    Remove-IfExists $avisosTask
    exit 0
}

$candidates = @(
    (Join-Path $scriptDir ".venv\Scripts\pythonw.exe"),
    (Join-Path (Split-Path -Parent $scriptDir) ".venv\Scripts\pythonw.exe")
)
$pythonw = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $pythonw) { throw "pythonw.exe nao encontrado em .venv (nesta pasta ou na pasta pai)." }

$user = "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

if ($BotLocal) {
    $action = New-ScheduledTaskAction -Execute $pythonw `
        -Argument "`"$(Join-Path $scriptDir 'run_bot.py')`"" -WorkingDirectory $scriptDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    # Sem limite de duracao; se o processo sair com erro, tenta de novo a cada minuto.
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $botTask -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal `
        -Description "DirecioZAP: bot de cadastro de fornecedores (WhatsApp) + ngrok em segundo plano" `
        -Force | Out-Null
    Start-ScheduledTask -TaskName $botTask
    Write-Host "Tarefa '$botTask' registrada e iniciada. Ela sobe sozinha a cada logon."
    exit 0
}

# Bot na nuvem: o bot local nao deve competir pelo webhook nem manter o ngrok aberto.
Remove-IfExists $botTask

$action = New-ScheduledTaskAction -Execute $pythonw `
    -Argument "`"$(Join-Path $scriptDir 'avisos_pc.py')`"" -WorkingDirectory $scriptDir
# Repete a cada 5 minutos a partir de agora (sem fim), e roda tambem logo no logon.
# A repeticao so num gatilho de logon comecaria apenas no PROXIMO logon.
$repetir = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)
$noLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger = @($repetir, $noLogon)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $avisosTask -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "DirecioZAP: avisos de novos cadastros pelo Outlook + mantem o bot do Render acordado" `
    -Force | Out-Null
Start-ScheduledTask -TaskName $avisosTask
Write-Host "Tarefa '$avisosTask' registrada: roda a cada 5 minutos. Logs em logs\direciozap.log."
