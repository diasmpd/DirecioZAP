import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from config import settings
from conversation import ConversationManager
from whatsapp import send_message

app = FastAPI(title="DirecioZap Bot")
manager = ConversationManager()


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()

    event = payload.get("event", "")
    if event != "messages.upsert":
        return {"status": "ignored"}

    data = payload.get("data", {})
    key = data.get("key", {})

    if key.get("fromMe"):
        return {"status": "ignored"}

    remote_jid: str = key.get("remoteJid", "")

    # Ignorar grupos e broadcasts
    if "@g.us" in remote_jid or "@broadcast" in remote_jid:
        return {"status": "ignored"}

    phone = remote_jid.replace("@s.whatsapp.net", "").strip()
    if not phone:
        return {"status": "ignored"}

    msg_type: str = data.get("messageType", "")
    message: dict = data.get("message", {})

    if msg_type == "conversation":
        text = message.get("conversation", "")
    elif msg_type == "extendedTextMessage":
        text = message.get("extendedTextMessage", {}).get("text", "")
    else:
        send_message(phone, "Por favor, responda apenas com texto.")
        return {"status": "non-text"}

    if not text:
        return {"status": "ignored"}

    response = manager.process(phone, text)
    send_message(phone, response)

    return {"status": "ok"}


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
