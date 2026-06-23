import requests
from config import settings


def send_message(phone: str, text: str) -> bool:
    url = f"{settings.EVOLUTION_API_URL}/message/sendText/{settings.EVOLUTION_INSTANCE}"
    headers = {
        "apikey": settings.EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"number": phone, "text": text}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[whatsapp] Erro ao enviar mensagem para {phone}: {e}")
        return False
