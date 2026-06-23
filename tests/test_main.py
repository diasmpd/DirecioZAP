"""
Testes A/B — main.py (endpoints FastAPI)
A = requisições válidas processadas corretamente
B = requisições inválidas / edge cases ignorados/rejeitados
"""
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# Importa a app após as variáveis de ambiente estarem definidas (conftest)
from main import app

PHONE = "5531999990000"
TOKEN = os.environ["VERIFY_TOKEN"]


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


def _payload_texto(phone=PHONE, text="Olá", from_me=False):
    return {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": f"{phone}@s.whatsapp.net",
                "fromMe": from_me,
                "id": "MSGID123",
            },
            "message": {"conversation": text},
            "messageType": "conversation",
        },
    }


def _payload_midia(phone=PHONE, tipo="audioMessage"):
    return {
        "event": "messages.upsert",
        "instance": "test-instance",
        "data": {
            "key": {
                "remoteJid": f"{phone}@s.whatsapp.net",
                "fromMe": False,
                "id": "MSGID456",
            },
            "message": {tipo: {}},
            "messageType": tipo,
        },
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
    def test_A_processa_mensagem_conversation(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_texto(text="Empresa Teste Ltda"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_manager.process.assert_called_once_with(PHONE, "Empresa Teste Ltda")

    def test_A_envia_resposta_ao_usuario(self, client, mock_manager, mock_send):
        mock_manager.process.return_value = "Qual o seu CNPJ?"
        client.post("/webhook", json=_payload_texto())
        mock_send.assert_called_once_with(PHONE, "Qual o seu CNPJ?")

    def test_A_aceita_extended_text_message(self, client, mock_manager, mock_send):
        payload = {
            "event": "messages.upsert",
            "data": {
                "key": {"remoteJid": f"{PHONE}@s.whatsapp.net", "fromMe": False},
                "message": {"extendedTextMessage": {"text": "texto extendido"}},
                "messageType": "extendedTextMessage",
            },
        }
        resp = client.post("/webhook", json=payload)
        assert resp.status_code == 200
        mock_manager.process.assert_called_once_with(PHONE, "texto extendido")


# ─────────────────────────────────────────────────────────────
#  B — WEBHOOK: CASOS IGNORADOS
# ─────────────────────────────────────────────────────────────

class TestWebhookIgnorados:
    def test_B_ignora_evento_diferente(self, client, mock_manager, mock_send):
        payload = {"event": "connection.update", "data": {}}
        resp = client.post("/webhook", json=payload)
        assert resp.json()["status"] == "ignored"
        mock_manager.process.assert_not_called()

    def test_B_ignora_mensagem_do_proprio_bot(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_texto(from_me=True))
        assert resp.json()["status"] == "ignored"
        mock_manager.process.assert_not_called()

    def test_B_ignora_mensagem_de_grupo(self, client, mock_manager, mock_send):
        payload = {
            "event": "messages.upsert",
            "data": {
                "key": {
                    "remoteJid": "1234567890@g.us",
                    "fromMe": False,
                },
                "message": {"conversation": "mensagem de grupo"},
                "messageType": "conversation",
            },
        }
        resp = client.post("/webhook", json=payload)
        assert resp.json()["status"] == "ignored"
        mock_manager.process.assert_not_called()

    def test_B_mensagem_midia_retorna_aviso_texto(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_midia())
        assert resp.json()["status"] == "non-text"
        mock_send.assert_called_once()
        assert "texto" in mock_send.call_args[0][1].lower()
        mock_manager.process.assert_not_called()

    def test_B_ignora_mensagem_de_audio(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_midia(tipo="audioMessage"))
        assert resp.json()["status"] == "non-text"

    def test_B_ignora_mensagem_de_imagem(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_midia(tipo="imageMessage"))
        assert resp.json()["status"] == "non-text"


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

    def test_B_retorna_404_sem_arquivo(self, client, monkeypatch):
        monkeypatch.setattr("main.settings.EXCEL_PATH", "/tmp/nao_existe.xlsx")
        resp = client.get(f"/exportar?token={TOKEN}")
        assert resp.status_code == 404
