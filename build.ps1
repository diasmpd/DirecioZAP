# DirecioZAP Manager — build script
# Gera o executavel em dist\DirecioZAP_Manager\
# Requisitos: Python 3.11+ no PATH, pip, pyinstaller

param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root  = $PSScriptRoot
$Dist  = Join-Path $Root "dist"
$Build = Join-Path $Root "build"

function Info($msg) { Write-Host "[BUILD] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Err($msg)  { Write-Host "[ERRO]  $msg" -ForegroundColor Red; exit 1 }

Info "DirecioZAP Manager — iniciando build"

# 1. Limpar artefatos anteriores (opcional)
if ($Clean) {
    Info "Limpando dist\ e build\"
    Remove-Item -Recurse -Force $Dist  -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $Build -ErrorAction SilentlyContinue
}

# 2. Verificar Python
$PyVer = python --version 2>&1
if (-not $?) { Err "Python nao encontrado no PATH. Instale Python 3.11+ e tente novamente." }
Info "Usando $PyVer"

# 3. Instalar dependencias do manager
Info "Instalando dependencias do manager..."
python -m pip install -q -r "$Root\requirements_manager.txt"
if (-not $?) { Err "Falha ao instalar dependencias." }

# 4. Instalar PyInstaller
python -m pip install -q pyinstaller
if (-not $?) { Err "Falha ao instalar PyInstaller." }
Ok "Dependencias instaladas."

# 5. Localizar pacote customtkinter para incluir no bundle
$CtkPath = python -c "import customtkinter, os; print(os.path.dirname(customtkinter.__file__))" 2>&1
if (-not $?) { Err "customtkinter nao instalado corretamente." }
Info "customtkinter em: $CtkPath"

# 6. Executar PyInstaller
Info "Executando PyInstaller..."
$Args = @(
    "manager_app.py",
    "--name=DirecioZAP_Manager",
    "--onedir",
    "--windowed",
    "--noconfirm",
    "--add-data=$CtkPath;customtkinter/",
    "--add-data=main.py;.",
    "--add-data=config.py;.",
    "--add-data=conversation.py;.",
    "--add-data=whatsapp.py;.",
    "--add-data=supabase_session.py;.",
    "--add-data=excel_writer.py;.",
    "--add-data=validators.py;.",
    "--hidden-import=customtkinter",
    "--hidden-import=PIL",
    "--hidden-import=PIL._tkinter_finder",
    "--hidden-import=fastapi",
    "--hidden-import=uvicorn",
    "--hidden-import=uvicorn.logging",
    "--hidden-import=uvicorn.loops",
    "--hidden-import=uvicorn.loops.asyncio",
    "--hidden-import=uvicorn.protocols",
    "--hidden-import=uvicorn.protocols.http",
    "--hidden-import=uvicorn.protocols.http.auto",
    "--hidden-import=uvicorn.protocols.websockets",
    "--hidden-import=uvicorn.protocols.websockets.auto",
    "--hidden-import=uvicorn.lifespan",
    "--hidden-import=uvicorn.lifespan.on",
    "--hidden-import=openpyxl",
    "--hidden-import=pydantic_settings",
    "--hidden-import=supabase",
    "--hidden-import=postgrest",
    "--hidden-import=gotrue",
    "--hidden-import=realtime",
    "--hidden-import=storage3",
    "--hidden-import=requests",
    "--hidden-import=anyio",
    "--hidden-import=anyio._backends._asyncio",
    "--hidden-import=httpx",
    "--collect-all=customtkinter",
    "--collect-all=uvicorn"
)

Set-Location $Root
pyinstaller @Args
if (-not $?) { Err "PyInstaller falhou. Verifique os erros acima." }

# 7. Copiar arquivos de configuracao para dist (sem sobrescrever se ja existir)
$DestDir = Join-Path $Dist "DirecioZAP_Manager"
$EnvSrc  = Join-Path $Root ".env.example"
$EnvDst  = Join-Path $DestDir ".env"

if ((Test-Path $EnvSrc) -and (-not (Test-Path $EnvDst))) {
    Copy-Item $EnvSrc $EnvDst
    Info "Copiado .env.example -> .env no diretorio do executavel."
}

# 8. Criar pasta data/ no dist
$DataDir = Join-Path $DestDir "data"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

Ok "Build concluido!"
Ok "Executavel em: $DestDir\DirecioZAP_Manager.exe"
Write-Host ""
Write-Host "Para distribuir, compacte a pasta '$DestDir' inteira e entregue ao usuario." -ForegroundColor Yellow
Write-Host "O usuario deve editar o arquivo .env com suas credenciais antes de abrir o .exe." -ForegroundColor Yellow
