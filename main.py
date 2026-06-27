import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

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

    response = manager.process(phone, text)
    send_message(phone, response)

    return Response(status_code=200)


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
