import requests
from config import settings


def send_message(phone: str, text: str) -> bool:
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
        print(f"[whatsapp] Erro ao enviar mensagem para {phone}: {e}")
        return False
