import hashlib
import hmac
import json
from collections import OrderedDict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from config import settings
from conversation import MSGS, ConversationManager
from excel_writer import gerar_excel
from supabase_session import get_cadastros, get_todas_perguntas
from whatsapp import send_message

app = FastAPI(title="DirecioZap Bot")
manager = ConversationManager()

# A Meta pode reenviar o mesmo webhook; guardamos os últimos IDs para não processar duas vezes.
_MAX_IDS_PROCESSADOS = 1000
_ids_processados: "OrderedDict[str, None]" = OrderedDict()


def _ja_processado(msg_id: str) -> bool:
    if not msg_id:
        return False
    if msg_id in _ids_processados:
        return True
    _ids_processados[msg_id] = None
    if len(_ids_processados) > _MAX_IDS_PROCESSADOS:
        _ids_processados.popitem(last=False)
    return False


def _assinatura_meta_valida(raw_body: bytes, header: str | None) -> bool:
    """Confere o header X-Hub-Signature-256 (HMAC-SHA256 do corpo com o App Secret)."""
    if not settings.META_APP_SECRET:
        print("[webhook] META_APP_SECRET não configurado — webhook Meta rejeitado.")
        return False
    if not header or not header.startswith("sha256="):
        return False
    esperado = hmac.new(
        settings.META_APP_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperado, header[len("sha256="):])


def _responder(phone: str, text: str) -> None:
    """Processa a mensagem e responde. Uma falha (ex: Supabase fora do ar) não pode
    sumir em silêncio: o fornecedor recebe um aviso para tentar de novo."""
    try:
        response = manager.process(phone, text)
    except Exception as exc:
        print(f"[webhook] Erro ao processar mensagem de {phone}: {exc!r}")
        send_message(phone, MSGS["ERRO_TECNICO"])
        return
    send_message(phone, response)


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/webhook")
def verify_webhook(request: Request):
    """Handshake exigido pela Meta ao configurar o webhook."""
    params = request.query_params
    if (
        settings.META_VERIFY_TOKEN
        and params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == settings.META_VERIFY_TOKEN
    ):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="Verify token inválido")


@app.post("/webhook")
async def webhook(request: Request):
    if settings.WHATSAPP_PROVIDER.lower() == "meta":
        return await _handle_meta(request)
    return await _handle_twilio(request)


async def _handle_twilio(request: Request):
    form = await request.form()

    num_media = int(form.get("NumMedia", "0"))
    phone = form.get("From", "").replace("whatsapp:", "").lstrip("+")
    text = form.get("Body", "").strip()

    if not phone:
        return Response(status_code=200)

    if num_media > 0:
        send_message(phone, "Por favor, responda apenas com texto.")
        return Response(status_code=200)

    if not text:
        return Response(status_code=200)

    _responder(phone, text)

    return Response(status_code=200)


async def _handle_meta(request: Request):
    raw_body = await request.body()
    if not _assinatura_meta_valida(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="Assinatura inválida")

    try:
        body = json.loads(raw_body)
    except ValueError:
        return Response(status_code=200)

    try:
        value = body["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
    except (KeyError, IndexError, TypeError, AttributeError):
        return Response(status_code=200)

    if not messages:
        # Callback de status (enviado/entregue/lido), não é mensagem do usuário.
        return Response(status_code=200)

    msg = messages[0]
    if _ja_processado(msg.get("id", "")):
        return Response(status_code=200)

    phone = msg.get("from", "").lstrip("+")

    if not phone:
        return Response(status_code=200)

    if msg.get("type") != "text":
        send_message(phone, "Por favor, responda apenas com texto.")
        return Response(status_code=200)

    text = msg.get("text", {}).get("body", "").strip()
    if not text:
        return Response(status_code=200)

    _responder(phone, text)

    return Response(status_code=200)


@app.get("/exportar")
def exportar(token: str):
    if token != settings.VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")
    cadastros = get_cadastros()
    if not cadastros:
        raise HTTPException(status_code=404, detail="Nenhum cadastro salvo ainda")
    conteudo = gerar_excel(cadastros, get_todas_perguntas())
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="fornecedores.xlsx"'},
    )
