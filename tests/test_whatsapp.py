"""
Testes A/B — whatsapp.py (cliente Meta WhatsApp Cloud API)
A = envio bem-sucedido
B = falhas de rede / API
"""
import pytest
from unittest.mock import MagicMock, patch
import requests

from whatsapp import send_message


PHONE = "5531999990000"
TEXT = "Olá! Seja bem-vindo."


class TestEnvioWhatsApp:

    # ── A — ENVIO BEM-SUCEDIDO ─────────────────────────────────

    def test_A_retorna_true_em_sucesso(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp):
            result = send_message(PHONE, TEXT)
        assert result is True

    def test_A_chama_url_correta(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        url = mock_post.call_args[0][0]
        assert "graph.facebook.com" in url
        assert "test_phone_number_id" in url
        assert "messages" in url

    def test_A_envia_payload_correto(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        payload = mock_post.call_args[1]["json"]
        assert payload["to"] == PHONE
        assert payload["text"]["body"] == TEXT
        assert payload["messaging_product"] == "whatsapp"
        assert payload["type"] == "text"

    def test_A_envia_bearer_token_no_header(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        headers = mock_post.call_args[1]["headers"]
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer ")

    # ── B — FALHAS ─────────────────────────────────────────────

    def test_B_retorna_false_em_connection_error(self):
        with patch("whatsapp.requests.post", side_effect=requests.ConnectionError()):
            result = send_message(PHONE, TEXT)
        assert result is False

    def test_B_retorna_false_em_timeout(self):
        with patch("whatsapp.requests.post", side_effect=requests.Timeout()):
            result = send_message(PHONE, TEXT)
        assert result is False

    def test_B_retorna_false_em_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401")
        with patch("whatsapp.requests.post", return_value=mock_resp):
            result = send_message(PHONE, TEXT)
        assert result is False

    def test_B_nao_lanca_excecao_em_falha(self):
        with patch("whatsapp.requests.post", side_effect=Exception("erro genérico")):
            result = send_message(PHONE, TEXT)
        assert result is False
