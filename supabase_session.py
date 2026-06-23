from datetime import datetime, timezone
from supabase import create_client, Client
from config import settings

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    return _client


def get_session(phone: str) -> dict | None:
    result = _get_client().table("sessions").select("*").eq("phone", phone).execute()
    return result.data[0] if result.data else None


def create_session(phone: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    session = {
        "phone": phone,
        "state": "SAUDACAO",
        "dados": {},
        "tentativas": {},
        "criado_em": now,
        "atualizado_em": now,
    }
    _get_client().table("sessions").upsert(session).execute()
    return session


def update_session(phone: str, state: str, dados: dict, tentativas: dict) -> None:
    _get_client().table("sessions").upsert(
        {
            "phone": phone,
            "state": state,
            "dados": dados,
            "tentativas": tentativas,
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()


def delete_session(phone: str) -> None:
    _get_client().table("sessions").delete().eq("phone", phone).execute()
