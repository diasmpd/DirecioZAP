"""Tarefa do PC enquanto o bot roda na nuvem (Render).

Executada a cada 5 minutos pela tarefa agendada "DirecioZAP Avisos" (register_task.ps1):
1. envia pelo Outlook deste PC os avisos de cadastros ainda não avisados (NOTIFY_EMAIL);
2. cadastra no Portal do Fornecedor os fornecedores que deram o e-mail (PORTAL_ENVIO=auto;
   "revisar" deixa todos para aprovar no Manager; vazio = desligado) — ver portal.py;
3. faz um GET no bot (BOT_URL) — o plano gratuito do Render adormece o serviço após 15 min
   sem requisições, e a primeira mensagem de um fornecedor levaria 30-60 s para ser
   respondida. Com o ping, o bot fica acordado enquanto este PC estiver ligado.

Uso manual:  ..\\.venv\\Scripts\\python.exe avisos_pc.py
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

from log_setup import configurar_logs, get_logger  # noqa: E402

configurar_logs()
log = get_logger("avisos_pc")


def acordar_bot(url: str) -> None:
    import requests
    try:
        r = requests.get(url.rstrip("/") + "/", timeout=90)  # 90 s: cobre o "acordar" do Render
        if not r.ok:
            log.warning("Bot em %s respondeu HTTP %s.", url, r.status_code)
    except Exception as ex:
        log.warning("Bot em %s inacessível: %s", url, ex)


def main() -> int:
    from dotenv import dotenv_values

    from db import Database
    from notificacao import destinatarios, enviar_pendentes

    cfg = dotenv_values(BASE_DIR / ".env")
    bot_url = (cfg.get("BOT_URL") or "").strip()
    if bot_url:
        acordar_bot(bot_url)

    para = destinatarios(cfg.get("NOTIFY_EMAIL"))
    url = (cfg.get("DATABASE_URL") or "").strip()
    if not url:
        return 0
    db = Database(url)
    codigo = 0
    if para:
        try:
            enviados, falhas = enviar_pendentes(db, para)
        except Exception:
            log.exception("Falha ao buscar cadastros pendentes de aviso")
            enviados, falhas = 0, 1
        if enviados or falhas:
            log.info("Avisos: %d enviado(s), %d pendente(s) para a próxima execução.", enviados, falhas)
        codigo = 1 if falhas else 0
    return max(codigo, portal_pc(db, cfg.get("PORTAL_ENVIO"), para))


def portal_pc(db, modo: str | None, para: list[str]) -> int:
    """Envia ao Portal os cadastros pendentes e manda um resumo por e-mail se algo mudou."""
    import portal
    from notificacao import enviar_outlook, montar_email_portal

    try:
        resultados = portal.processar_pendentes(db, modo or "")
    except Exception:
        # Portal fora do ar ou banco inacessível: os não processados ficam para a próxima.
        log.exception("Falha ao processar os envios ao Portal do Fornecedor")
        return 1
    for r in resultados:
        log.info("Portal: %s — %s (%s)", (r["cadastro"].get("dados") or {}).get("cnpj"),
                 r["status"], r["detalhe"])
    if resultados and para:
        try:
            enviar_outlook(para, *montar_email_portal(resultados))
        except Exception:
            log.exception("Falha ao enviar o resumo do Portal por e-mail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
