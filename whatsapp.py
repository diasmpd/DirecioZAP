import requests
from config import settings


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
        print(f"[whatsapp] Erro ao enviar mensagem (Twilio) para {phone}: {e}")
        return False


def _send_via_meta(phone: str, text: str) -> bool:
    url = f"https://graph.facebook.com/{settings.META_API_VERSION}/{settings.META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.META_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone.lstrip("+"),
        "type": "text",
        "text": {"body": text},
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[whatsapp] Erro ao enviar mensagem (Meta) para {phone}: {e}")
        return False
