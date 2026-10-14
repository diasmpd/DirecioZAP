"""Log em arquivo para o bot.

No .exe (janela sem console) e na tarefa agendada (pythonw) o print() não vai para lugar
nenhum — sem arquivo de log, um erro em produção só aparece como "o bot não respondeu".
Os logs ficam em logs/direciozap.log, ao lado do app, com rotação (5 arquivos de 1 MB).
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "direciozap.log"

_FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configurar_logs() -> None:
    """Idempotente: o Manager recarrega os módulos do bot a cada "Iniciar Bot"."""
    raiz = logging.getLogger("direciozap")
    if raiz.handlers:
        return
    raiz.setLevel(logging.INFO)
    LOG_DIR.mkdir(exist_ok=True)
    arquivo = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    arquivo.setFormatter(logging.Formatter(_FORMATO))
    raiz.addHandler(arquivo)
    if sys.stderr is not None:  # pythonw / .exe sem console não têm stderr
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMATO))
        raiz.addHandler(console)


def mascarar(phone: str) -> str:
    """Telefone parcial no log: dá para achar a conversa sem gravar o número inteiro."""
    p = (phone or "").lstrip("+")
    return p if len(p) <= 6 else f"{p[:4]}…{p[-4:]}"


def get_logger(nome: str) -> logging.Logger:
    return logging.getLogger(f"direciozap.{nome}")
