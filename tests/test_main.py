"""
Testes A/B — main.py (endpoints FastAPI + Twilio WhatsApp)
A = requisições válidas processadas corretamente
B = requisições inválidas / edge cases ignorados/rejeitados
"""
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from main import app

PHONE = "5531999990000"
TOKEN = os.environ["VERIFY_TOKEN"]
SANDBOX_FROM = "whatsapp:+14155238886"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_manager(monkeypatch):
    mock = MagicMock()
    mock.process.return_value = "mensagem de resposta"
    monkeypatch.setattr("main.manager", mock)
    return mock


@pytest.fixture
def mock_send(monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr("main.send_message", mock)
    return mock


def _form_texto(phone=PHONE, text="Olá"):
    return {
        "From": f"whatsapp:+{phone}",
        "To": SANDBOX_FROM,
        "Body": text,
        "NumMedia": "0",
        "MessageSid": "SMtest123",
    }


def _form_midia(phone=PHONE, num_media=1):
    return {
        "From": f"whatsapp:+{phone}",
        "To": SANDBOX_FROM,
        "Body": "",
        "NumMedia": str(num_media),
        "MessageSid": "SMtest456",
        "MediaContentType0": "image/jpeg",
        "MediaUrl0": "https://api.twilio.com/media/test.jpg",
    }


# ─────────────────────────────────────────────────────────────
#  A — HEALTH CHECK
# ─────────────────────────────────────────────────────────────

def test_A_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ─────────────────────────────────────────────────────────────
#  A — WEBHOOK: MENSAGEM DE TEXTO
# ─────────────────────────────────────────────────────────────

class TestWebhookTexto:
    def test_A_processa_mensagem_de_texto(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", data=_form_texto(text="Empresa Teste Ltda"))
        assert resp.status_code == 200
        mock_manager.process.assert_called_once_with(PHONE, "Empresa Teste Ltda")

    def test_A_envia_resposta_ao_usuario(self, client, mock_manager, mock_send):
        mock_manager.process.return_value = "Qual o seu CNPJ?"
        client.post("/webhook", data=_form_texto())
        mock_send.assert_called_once_with(PHONE, "Qual o seu CNPJ?")

    def test_A_extrai_numero_sem_plus(self, client, mock_manager, mock_send):
        client.post("/webhook", data=_form_texto(phone="5511988887777"))
        mock_manager.process.assert_called_once_with("5511988887777", "Olá")

    def test_A_strip_espacos_no_texto(self, client, mock_manager, mock_send):
        client.post("/webhook", data=_form_texto(text="  Empresa Ltda  "))
        mock_manager.process.assert_called_once_with(PHONE, "Empresa Ltda")


# ─────────────────────────────────────────────────────────────
#  B — WEBHOOK: CASOS IGNORADOS / AVISO
# ─────────────────────────────────────────────────────────────

class TestWebhookIgnorados:
    def test_B_mensagem_midia_envia_aviso_texto(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", data=_form_midia())
        assert resp.status_code == 200
        mock_send.assert_called_once()
        assert "texto" in mock_send.call_args[0][1].lower()
        mock_manager.process.assert_not_called()

    def test_B_body_vazio_sem_midia_ignorado(self, client, mock_manager, mock_send):
        form = _form_texto(text="")
        resp = client.post("/webhook", data=form)
        assert resp.status_code == 200
        mock_manager.process.assert_not_called()
        mock_send.assert_not_called()

    def test_B_sem_from_ignorado(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", data={"Body": "oi", "NumMedia": "0"})
        assert resp.status_code == 200
        mock_manager.process.assert_not_called()

    def test_B_num_media_maior_que_zero_bloqueia(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", data=_form_midia(num_media=2))
        assert resp.status_code == 200
        mock_manager.process.assert_not_called()


# ─────────────────────────────────────────────────────────────
#  A/B — ENDPOINT /exportar
# ─────────────────────────────────────────────────────────────

class TestExportar:
    def test_A_retorna_arquivo_com_token_correto(self, client, tmp_path, monkeypatch):
        path = str(tmp_path / "fornecedores.xlsx")
        import openpyxl
        wb = openpyxl.Workbook()
        wb.save(path)
        monkeypatch.setattr("main.settings.EXCEL_PATH", path)
        resp = client.get(f"/exportar?token={TOKEN}")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]

    def test_B_retorna_403_com_token_errado(self, client):
        resp = client.get("/exportar?token=token_errado")
        assert resp.status_code == 403

    def test_B_retorna_403_sem_token(self, client):
        resp = client.get("/exportar")
        assert resp.status_code == 422

    def test_B_retorna_404_sem_arquivo(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("main.settings.EXCEL_PATH", str(tmp_path / "nao_existe.xlsx"))
        resp = client.get(f"/exportar?token={TOKEN}")
        assert resp.status_code == 404
