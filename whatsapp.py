import requests
from config import settings
from log_setup import get_logger, mascarar

log = get_logger("whatsapp")

# Sessão HTTP reaproveitada: evita um handshake TLS novo com a Meta a cada resposta.
_http = requests.Session()


def send_message(phone: str, text: str) -> bool:
    if settings.WHATSAPP_PROVIDER.lower() == "meta":
        return _send_via_meta(phone, text)
    return _send_via_twilio(phone, text)


def _send_via_twilio(phone: str, text: str) -> bool:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    data = {
        "From": f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}",
        "To": f"whatsapp:+{phone.lstrip('+')}",
        "Body": text,
    }
    try:
        resp = requests.post(
            url,
            data=data,
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        log.error("Erro ao enviar mensagem (Twilio) para %s: %s", mascarar(phone), e)
        return False


# Limites da Meta para mensagens interativas.
_MAX_CORPO_INTERATIVO = 1024
_MAX_TITULO_BOTAO = 20
_MAX_TITULO_ITEM = 24


def _interativo(text: str) -> dict | None:
    """Monta o bloco "interactive" se a resposta tiver botões ou lista; senão None."""
    botoes = getattr(text, "botoes", None)
    lista = getattr(text, "lista", None)
    if botoes:
        return {
            "type": "button",
            "body": {"text": str(text)},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": bid, "title": titulo[:_MAX_TITULO_BOTAO]}}
                for bid, titulo in botoes[:3]
            ]},
        }
    if lista:
        return {
            "type": "list",
            "body": {"text": str(text)},
            "action": {
                "button": (getattr(text, "lista_botao", None) or "Escolher")[:_MAX_TITULO_BOTAO],
                "sections": [{"title": "Opções", "rows": [
                    {"id": iid, "title": titulo[:_MAX_TITULO_ITEM]} for iid, titulo in lista[:10]
                ]}],
            },
        }
    return None


def _post_meta(phone: str, payload: dict) -> bool:
    url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{settings.META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.META_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"messaging_product": "whatsapp", "to": phone.lstrip("+"), **payload}
    try:
        resp = _http.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        log.error("Erro ao enviar mensagem (Meta) para %s: %s", mascarar(phone), e)
        return False
    if not resp.ok:
        # O corpo traz o código da Meta (ex: 131047 fora da janela de 24h, 190 token inválido).
        log.error("Meta recusou a mensagem para %s: HTTP %s %s",
                  mascarar(phone), resp.status_code, resp.text[:500])
        return False
    return True


def _send_via_meta(phone: str, text: str) -> bool:
    interativo = _interativo(text)
    if not interativo:
        return _post_meta(phone, {"type": "text", "text": {"body": str(text)}})
    if len(str(text)) > _MAX_CORPO_INTERATIVO:
        # Corpo grande demais para mensagem interativa: texto completo + botões com corpo curto.
        if not _post_meta(phone, {"type": "text", "text": {"body": str(text)}}):
            return False
        interativo["body"]["text"] = "Escolha uma opção:"
    if _post_meta(phone, {"type": "interactive", "interactive": interativo}):
        return True
    # Se a Meta recusar o interativo, o texto puro ainda funciona (todas as opções podem ser digitadas).
    log.warning("Mensagem interativa recusada para %s; reenviando como texto.", mascarar(phone))
    return _post_meta(phone, {"type": "text", "text": {"body": str(text)}})
