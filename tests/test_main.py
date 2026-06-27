"""
Testes A/B — main.py (endpoints FastAPI + Meta WhatsApp Cloud API)
A = requisições válidas processadas corretamente
B = requisições inválidas / edge cases ignorados/rejeitados
"""
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

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


def _payload_texto(phone=PHONE, text="Olá"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "15556741075", "phone_number_id": "test_phone_number_id"},
                    "contacts": [{"profile": {"name": "Test User"}, "wa_id": phone}],
                    "messages": [{
                        "from": phone,
                        "id": "wamid.test123",
                        "timestamp": "1234567890",
                        "type": "text",
                        "text": {"body": text},
                    }],
                },
            }],
        }],
    }


def _payload_midia(phone=PHONE, tipo="audio"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "15556741075", "phone_number_id": "test_phone_number_id"},
                    "contacts": [{"profile": {"name": "Test User"}, "wa_id": phone}],
                    "messages": [{
                        "from": phone,
                        "id": "wamid.test456",
                        "timestamp": "1234567890",
                        "type": tipo,
                    }],
                },
            }],
        }],
    }


def _payload_status():
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "statuses": [{"id": "wamid.test", "status": "delivered"}],
                },
            }],
        }],
    }


# ─────────────────────────────────────────────────────────────
#  A — HEALTH CHECK
# ─────────────────────────────────────────────────────────────

def test_A_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ─────────────────────────────────────────────────────────────
#  A — VERIFICAÇÃO DE WEBHOOK (GET /webhook)
# ─────────────────────────────────────────────────────────────

class TestWebhookVerificacao:
    def test_A_verifica_webhook_com_token_correto(self, client):
        resp = client.get(
            "/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": TOKEN, "hub.challenge": "challenge_abc"},
        )
        assert resp.status_code == 200
        assert resp.text == "challenge_abc"

    def test_B_rejeita_token_errado(self, client):
        resp = client.get(
            "/webhook",
            params={"hub.mode": "subscribe", "hub.verify_token": "token_errado", "hub.challenge": "challenge_abc"},
        )
        assert resp.status_code == 403

    def test_B_rejeita_mode_errado(self, client):
        resp = client.get(
            "/webhook",
            params={"hub.mode": "unsubscribe", "hub.verify_token": TOKEN, "hub.challenge": "challenge_abc"},
        )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────
#  A — WEBHOOK: MENSAGEM DE TEXTO
# ─────────────────────────────────────────────────────────────

class TestWebhookTexto:
    def test_A_processa_mensagem_de_texto(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_texto(text="Empresa Teste Ltda"))
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_manager.process.assert_called_once_with(PHONE, "Empresa Teste Ltda")

    def test_A_envia_resposta_ao_usuario(self, client, mock_manager, mock_send):
        mock_manager.process.return_value = "Qual o seu CNPJ?"
        client.post("/webhook", json=_payload_texto())
        mock_send.assert_called_once_with(PHONE, "Qual o seu CNPJ?")

    def test_A_extrai_numero_correto(self, client, mock_manager, mock_send):
        client.post("/webhook", json=_payload_texto(phone="5511988887777"))
        mock_manager.process.assert_called_once_with("5511988887777", "Olá")


# ─────────────────────────────────────────────────────────────
#  B — WEBHOOK: CASOS IGNORADOS / SEM PROCESSAMENTO
# ─────────────────────────────────────────────────────────────

class TestWebhookIgnorados:
    def test_B_ignora_objeto_diferente(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json={"object": "instagram", "entry": []})
        assert resp.json()["status"] == "ignored"
        mock_manager.process.assert_not_called()

    def test_B_status_update_nao_processa(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_status())
        assert resp.status_code == 200
        mock_manager.process.assert_not_called()
        mock_send.assert_not_called()

    def test_B_mensagem_audio_envia_aviso_texto(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_midia(tipo="audio"))
        assert resp.status_code == 200
        mock_send.assert_called_once()
        assert "texto" in mock_send.call_args[0][1].lower()
        mock_manager.process.assert_not_called()

    def test_B_mensagem_imagem_envia_aviso_texto(self, client, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_midia(tipo="image"))
        assert resp.status_code == 200
        mock_send.assert_called_once()
        mock_manager.process.assert_not_called()

    def test_B_campo_diferente_de_messages_ignorado(self, client, mock_manager, mock_send):
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{"id": "X", "changes": [{"field": "account_update", "value": {}}]}],
        }
        resp = client.post("/webhook", json=payload)
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
