"""Aviso por e-mail (Outlook) a cada cadastro concluído.

Usa o Outlook desktop já configurado neste PC (via COM), então não precisa de senha SMTP
nem de liberação da TI. O envio roda numa thread à parte: o fornecedor recebe a resposta
na hora e uma falha no e-mail nunca afeta o cadastro, que já está salvo no banco.
Destinatários em NOTIFY_EMAIL (separados por vírgula ou ponto e vírgula); vazio = desligado.
"""
import html
import re
import threading
from datetime import datetime, timedelta, timezone

from log_setup import get_logger, mascarar

log = get_logger("notificacao")

_FUSO_BRASILIA = timezone(timedelta(hours=-3))


def destinatarios(valor: str | None) -> list[str]:
    return [e.strip() for e in re.split(r"[;,]", valor or "") if e.strip()]


def montar_email(phone: str, dados: dict, perguntas: list[dict]) -> tuple[str, str]:
    """(assunto, corpo HTML). Tudo que veio do fornecedor é escapado antes de ir para o HTML."""
    labels = {p["campo"]: p.get("label") or p["campo"] for p in perguntas}
    nome = dados.get("razao_social") or "(sem razão social)"
    assunto = f"DirecioZAP: novo cadastro de fornecedor — {nome}"

    linhas = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'><b>{html.escape(str(labels.get(c, c)))}</b></td>"
        f"<td style='padding:4px 0'>{html.escape(str(v))}</td></tr>"
        for c, v in dados.items()
    )
    quando = datetime.now(_FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M")
    corpo = (
        "<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px'>"
        "<p>Um fornecedor concluiu o cadastro pelo WhatsApp.</p>"
        f"<table>{linhas}"
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'><b>WhatsApp</b></td><td>+{html.escape(phone)}</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'><b>Data</b></td><td>{quando}</td></tr>"
        "</table>"
        "<p style='color:#888;font-size:12px'>A planilha completa está no DirecioZAP Manager "
        "(Mensagens → Baixar Excel).</p></div>"
    )
    return assunto, corpo


def enviar_outlook(para: list[str], assunto: str, corpo_html: str) -> None:
    """Envia pelo Outlook do usuário logado. Levanta exceção se falhar."""
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()  # cada thread precisa inicializar o COM
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.To = "; ".join(para)
        mail.Subject = assunto
        mail.HTMLBody = corpo_html
        mail.Send()
    finally:
        pythoncom.CoUninitialize()


def notificar_novo_cadastro(phone: str, dados: dict, perguntas: list[dict]) -> threading.Thread | None:
    from config import settings

    para = destinatarios(settings.NOTIFY_EMAIL)
    if not para:
        return None
    assunto, corpo = montar_email(phone, dados, perguntas)

    def _enviar():
        try:
            enviar_outlook(para, assunto, corpo)
            log.info("Aviso de cadastro de %s enviado para %s.", mascarar(phone), ", ".join(para))
        except Exception:
            log.exception("Falha ao enviar aviso por e-mail do cadastro de %s", mascarar(phone))

    t = threading.Thread(target=_enviar, name="aviso-email", daemon=True)
    t.start()
    return t
