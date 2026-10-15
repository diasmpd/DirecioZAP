"""Aviso por e-mail (Outlook) a cada cadastro concluído.

O bot roda na nuvem, onde não há Outlook; quem envia os avisos é o avisos_pc.py, rodando
neste PC de tempos em tempos: lê no banco os cadastros com notificado_em vazio, envia pelo
Outlook desktop (via COM — sem senha SMTP nem liberação da TI) e marca cada um como avisado.
Se o PC estiver desligado, os avisos ficam pendentes e saem na próxima execução.
Destinatários em NOTIFY_EMAIL (separados por vírgula ou ponto e vírgula); vazio = desligado.
"""
import html
import re
from datetime import datetime, timedelta, timezone

from log_setup import get_logger, mascarar
import portal
import receita

log = get_logger("notificacao")

_FUSO_BRASILIA = timezone(timedelta(hours=-3))


def destinatarios(valor: str | None) -> list[str]:
    return [e.strip() for e in re.split(r"[;,]", valor or "") if e.strip()]


def montar_email(phone: str, dados: dict, perguntas: list[dict], criado_em: str | None = None) -> tuple[str, str]:
    """(assunto, corpo HTML). Tudo que veio do fornecedor é escapado antes de ir para o HTML."""
    labels = {**receita.LABELS, portal.CAMPO_EMAIL: portal.LABEL_EMAIL, **{p["campo"]: p.get("label") or p["campo"] for p in perguntas}}
    nome = dados.get("razao_social") or "(sem razão social)"
    assunto = f"DirecioZAP: novo cadastro de fornecedor — {nome}"

    linhas = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'><b>{html.escape(str(labels.get(c, c)))}</b></td>"
        f"<td style='padding:4px 0'>{html.escape(str(v))}</td></tr>"
        for c, v in dados.items()
    )
    try:
        momento = datetime.fromisoformat(criado_em) if criado_em else datetime.now(timezone.utc)
    except ValueError:
        momento = datetime.now(timezone.utc)
    quando = momento.astimezone(_FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M")
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


def enviar_pendentes(db, para: list[str], enviar=None) -> tuple[int, int]:
    """Envia um e-mail por cadastro ainda não avisado e marca os enviados.
    Retorna (enviados, falhas). Para no primeiro erro do Outlook — se ele está fechado ou
    sem perfil, insistir nos demais só repetiria o erro; eles saem na próxima execução."""
    enviar = enviar or enviar_outlook
    pendentes = db.get_cadastros_sem_aviso()
    if not pendentes or not para:
        return 0, 0
    perguntas = db.get_todas_perguntas()
    enviados = 0
    for c in pendentes:
        assunto, corpo = montar_email(c["phone"], c.get("dados") or {}, perguntas, c.get("criado_em"))
        try:
            enviar(para, assunto, corpo)
        except Exception:
            log.exception("Falha ao enviar aviso do cadastro de %s", mascarar(c["phone"]))
            return enviados, len(pendentes) - enviados
        db.marcar_notificado(c["id"])
        enviados += 1
        log.info("Aviso do cadastro de %s enviado para %s.", mascarar(c["phone"]), ", ".join(para))
    return enviados, 0
