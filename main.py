import os

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse

from config import settings
from conversation import ConversationManager
from whatsapp import send_message

app = FastAPI(title="DirecioZap Bot")
manager = ConversationManager()


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/webhook")
def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail="Verificação inválida")


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()

    if payload.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            for message in change.get("value", {}).get("messages", []):
                _handle_message(message)

    return {"status": "ok"}


def _handle_message(message: dict):
    phone = message.get("from", "")
    if not phone:
        return

    if message.get("type") == "text":
        text = message.get("text", {}).get("body", "")
    else:
        send_message(phone, "Por favor, responda apenas com texto.")
        return

    if not text:
        return

    response = manager.process(phone, text)
    send_message(phone, response)


@app.get("/exportar")
def exportar(token: str):
    if token != settings.VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")
    path = settings.EXCEL_PATH
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Nenhum cadastro salvo ainda")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="fornecedores.xlsx",
    )
