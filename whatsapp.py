import requests
from config import settings

_GRAPH_URL = "https://graph.facebook.com/v21.0"


def send_message(phone: str, text: str) -> bool:
    url = f"{_GRAPH_URL}/{settings.META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {settings.META_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text},
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[whatsapp] Erro ao enviar mensagem para {phone}: {e}")
        return False
