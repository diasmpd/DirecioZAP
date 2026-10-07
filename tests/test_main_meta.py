"""
Testes A/B — main.py (webhook Meta WhatsApp Cloud API)
A = requisicoes validas processadas corretamente
B = requisicoes invalidas / edge cases ignorados/rejeitados
"""
import hashlib
import hmac
import json
from collections import OrderedDict

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from main import app

PHONE = "5531999990000"
VERIFY_TOKEN = "meta_verify_test_token"
APP_SECRET = "meta_app_secret_test"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def meta_provider(monkeypatch):
    monkeypatch.setattr("main.settings.WHATSAPP_PROVIDER", "Meta")
    monkeypatch.setattr("main.settings.META_VERIFY_TOKEN", VERIFY_TOKEN)
    monkeypatch.setattr("main.settings.META_APP_SECRET", APP_SECRET)
    monkeypatch.setattr("main._ids_processados", OrderedDict())


def _post_assinado(client, payload, secret=APP_SECRET):
    raw = json.dumps(payload).encode()
    assinatura = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={assinatura}"},
    )


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


def _payload_texto(phone=PHONE, text="Ola"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [{
                        "from": phone,
                        "id": "wamid.test",
                        "type": "text",
                        "text": {"body": text},
                    }],
                },
                "field": "messages",
            }],
        }],
    }


def _payload_midia(phone=PHONE):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "messages": [{
                        "from": phone,
                        "id": "wamid.test",
                        "type": "image",
                        "image": {"id": "media123"},
                    }],
                },
                "field": "messages",
            }],
        }],
    }


def _payload_status():
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "statuses": [{"id": "wamid.test", "status": "delivered"}],
                },
                "field": "messages",
            }],
        }],
    }


# ─────────────────────────────────────────────────────────────
#  A — VERIFICACAO DO WEBHOOK (handshake da Meta)
# ─────────────────────────────────────────────────────────────

class TestVerificacaoWebhook:
    def test_A_challenge_retornado_com_token_correto(self, client, meta_provider):
        resp = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": VERIFY_TOKEN,
                "hub.challenge": "12345",
            },
        )
        assert resp.status_code == 200
        assert resp.text == "12345"

    def test_B_403_com_token_errado(self, client, meta_provider):
        resp = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "token_errado",
                "hub.challenge": "12345",
            },
        )
        assert resp.status_code == 403

    def test_B_403_sem_verify_token_configurado(self, client, meta_provider, monkeypatch):
        monkeypatch.setattr("main.settings.META_VERIFY_TOKEN", None)
        resp = client.get("/webhook", params={"hub.mode": "subscribe", "hub.challenge": "12345"})
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────
#  B — ASSINATURA X-Hub-Signature-256
# ─────────────────────────────────────────────────────────────

class TestAssinatura:
    def test_B_sem_assinatura_rejeitado(self, client, meta_provider, mock_manager, mock_send):
        resp = client.post("/webhook", json=_payload_texto())
        assert resp.status_code == 403
        mock_manager.process.assert_not_called()

    def test_B_assinatura_com_secret_errado_rejeitada(self, client, meta_provider, mock_manager, mock_send):
        resp = _post_assinado(client, _payload_texto(), secret="outro_secret")
        assert resp.status_code == 403
        mock_manager.process.assert_not_called()

    def test_B_sem_app_secret_configurado_rejeita(self, client, meta_provider, mock_manager, mock_send, monkeypatch):
        monkeypatch.setattr("main.settings.META_APP_SECRET", None)
        resp = _post_assinado(client, _payload_texto())
        assert resp.status_code == 403
        mock_manager.process.assert_not_called()


# ─────────────────────────────────────────────────────────────
#  A — WEBHOOK: MENSAGEM DE TEXTO
# ─────────────────────────────────────────────────────────────

class TestWebhookTexto:
    def test_A_processa_mensagem_de_texto(self, client, meta_provider, mock_manager, mock_send):
        resp = _post_assinado(client, _payload_texto(text="Empresa Teste Ltda"))
        assert resp.status_code == 200
        mock_manager.process.assert_called_once_with(PHONE, "Empresa Teste Ltda")

    def test_A_envia_resposta_ao_usuario(self, client, meta_provider, mock_manager, mock_send):
        mock_manager.process.return_value = "Qual o seu CNPJ?"
        _post_assinado(client, _payload_texto())
        mock_send.assert_called_once_with(PHONE, "Qual o seu CNPJ?")


# ─────────────────────────────────────────────────────────────
#  B — WEBHOOK: CASOS IGNORADOS / AVISO
# ─────────────────────────────────────────────────────────────

class TestWebhookIgnorados:
    def test_B_mensagem_midia_envia_aviso_texto(self, client, meta_provider, mock_manager, mock_send):
        resp = _post_assinado(client, _payload_midia())
        assert resp.status_code == 200
        mock_send.assert_called_once()
        assert "texto" in mock_send.call_args[0][1].lower()
        mock_manager.process.assert_not_called()

    def test_B_callback_de_status_ignorado(self, client, meta_provider, mock_manager, mock_send):
        resp = _post_assinado(client, _payload_status())
        assert resp.status_code == 200
        mock_manager.process.assert_not_called()
        mock_send.assert_not_called()

    def test_B_payload_malformado_ignorado(self, client, meta_provider, mock_manager, mock_send):
        resp = _post_assinado(client, {"object": "whatsapp_business_account", "entry": []})
        assert resp.status_code == 200
        mock_manager.process.assert_not_called()

    def test_B_mensagem_duplicada_processada_uma_vez(self, client, meta_provider, mock_manager, mock_send):
        _post_assinado(client, _payload_texto(text="Empresa X"))
        resp = _post_assinado(client, _payload_texto(text="Empresa X"))
        assert resp.status_code == 200
        mock_manager.process.assert_called_once()


class TestFalhaNoProcessamento:
    def test_B_erro_no_processamento_avisa_fornecedor(self, client, meta_provider, mock_manager, mock_send):
        mock_manager.process.side_effect = RuntimeError("Supabase fora do ar")
        resp = _post_assinado(client, _payload_texto())
        assert resp.status_code == 200
        mock_send.assert_called_once()
        assert "problema técnico" in mock_send.call_args[0][1]
