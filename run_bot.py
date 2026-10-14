"""Roda o bot sem o Manager: servidor na porta 3000 + túnel ngrok, vigiado.

Pensado para a tarefa agendada (register_task.ps1), que o inicia com pythonw no logon do
Windows e o reinicia se o processo cair. Este script:
- espera a porta 3000 ficar livre (se o Manager estiver rodando o bot, não briga com ele);
- reaproveita um túnel ngrok já aberto para o domínio, ou abre um, e o reabre se cair;
- grava tudo em logs/ (pythonw não tem console).

Uso manual:  ..\\.venv\\Scripts\\python.exe run_bot.py
"""
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

from log_setup import LOG_DIR, configurar_logs, get_logger  # noqa: E402

LOG_DIR.mkdir(exist_ok=True)
if sys.stderr is None:  # pythonw: sem isso, saídas do uvicorn/ngrok se perdem ou quebram
    _console = open(LOG_DIR / "console.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _console

configurar_logs()
log = get_logger("run_bot")

PORTA = int(os.environ.get("DIRECIOZAP_PORTA", "3000"))  # override só para testes
_INTERVALO_VIGIA_S = 30


def _porta_ocupada(porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def _ngrok_bin() -> str | None:
    embutido = BASE_DIR / "ngrok.exe"
    return str(embutido) if embutido.exists() else shutil.which("ngrok")


def _tunel_ativo(dominio: str) -> bool:
    import requests
    try:
        tuneis = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3).json().get("tunnels", [])
    except Exception:
        return False
    return any(dominio in (t.get("public_url") or "") for t in tuneis)


def _abrir_ngrok(dominio: str, authtoken: str) -> subprocess.Popen | None:
    ngrok = _ngrok_bin()
    if not ngrok:
        log.error("ngrok não encontrado (nem ngrok.exe ao lado do bot, nem no PATH).")
        return None
    args = [ngrok, "http", f"127.0.0.1:{PORTA}", "--log", str(LOG_DIR / "ngrok.log")]
    if dominio:
        args += ["--domain", dominio]
    if authtoken and authtoken != "coloque_aqui":
        args += ["--authtoken", authtoken]
    # CREATE_NO_WINDOW: sob pythonw, um processo de console abriria uma janela preta.
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    log.info("ngrok iniciado (pid %s) para %s.", proc.pid, dominio or "URL aleatória")
    return proc


def _vigiar_ngrok(dominio: str, authtoken: str, parar: threading.Event) -> None:
    proc = None
    while not parar.is_set():
        if not _tunel_ativo(dominio or "ngrok"):
            if proc and proc.poll() is None:
                log.warning("Túnel ngrok sumiu; reiniciando o ngrok.")
                proc.terminate()
            proc = _abrir_ngrok(dominio, authtoken)
            if proc:
                for _ in range(15):  # espera o túnel subir antes de checar de novo
                    if parar.wait(1) or _tunel_ativo(dominio or "ngrok"):
                        break
                if not _tunel_ativo(dominio or "ngrok"):
                    log.error("ngrok não abriu o túnel — domínio em uso em outro PC/sessão "
                              "ou authtoken inválido. Veja logs/ngrok.log.")
        parar.wait(_INTERVALO_VIGIA_S)
    if proc and proc.poll() is None:
        proc.terminate()


def main() -> None:
    from dotenv import dotenv_values

    cfg = dotenv_values(BASE_DIR / ".env")
    if _porta_ocupada(PORTA):
        log.info("Porta %d em uso (bot aberto pelo Manager?). Aguardando liberar...", PORTA)
        while _porta_ocupada(PORTA):
            time.sleep(60)

    parar = threading.Event()
    vigia = threading.Thread(
        target=_vigiar_ngrok,
        args=((cfg.get("NGROK_DOMAIN") or "").strip(), (cfg.get("NGROK_AUTH_TOKEN") or "").strip(), parar),
        name="vigia-ngrok", daemon=True,
    )
    vigia.start()

    import uvicorn
    from main import app

    try:
        uvicorn.run(app, host="127.0.0.1", port=PORTA, log_config=None)
    finally:
        parar.set()
        vigia.join(5)
    # uvicorn só retorna se o servidor parar (erro ou sinal). Sair com código != 0 faz a
    # tarefa agendada reiniciar o bot.
    log.error("Servidor parou; saindo para a tarefa agendada reiniciar.")
    sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        log.exception("Falha fatal no run_bot")
        sys.exit(1)
