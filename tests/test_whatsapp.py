"""
Testes A/B — whatsapp.py (cliente Evolution API)
A = envio bem-sucedido
B = falhas de rede / API
"""
import pytest
from unittest.mock import MagicMock, patch
import requests

from whatsapp import send_message


PHONE = "5531999990000"
TEXT = "Olá! Seja bem-vindo."


# ─────────────────────────────────────────────────────────────
#  A — ENVIO BEM-SUCEDIDO
# ─────────────────────────────────────────────────────────────

class TestEnvioWhatsApp:
    def test_A_retorna_true_em_sucesso(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            result = send_message(PHONE, TEXT)
        assert result is True

    def test_A_chama_url_correta(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        call_kwargs = mock_post.call_args
        url = call_kwargs[0][0]
        assert "message/sendText" in url
        assert "test-instance" in url

    def test_A_envia_number_e_text_corretos(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        payload = mock_post.call_args[1]["json"]
        assert payload["number"] == PHONE
        assert payload["text"] == TEXT

    def test_A_envia_apikey_no_header(self, monkeypatch):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        headers = mock_post.call_args[1]["headers"]
        assert "apikey" in headers

    # ─────────────────────────────────────────────────────────────
    #  B — FALHAS
    # ─────────────────────────────────────────────────────────────

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
            # não deve propagar a exceção
            result = send_message(PHONE, TEXT)
        assert result is False
