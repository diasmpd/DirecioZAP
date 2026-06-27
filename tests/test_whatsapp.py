"""
Testes A/B — whatsapp.py (cliente Twilio WhatsApp)
A = envio bem-sucedido
B = falhas de rede / API
"""
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

    def test_A_chama_url_twilio_correta(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        url = mock_post.call_args[0][0]
        assert "api.twilio.com" in url
        assert "Messages.json" in url

    def test_A_envia_payload_correto(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        data = mock_post.call_args[1]["data"]
        assert data["Body"] == TEXT
        assert PHONE in data["To"]
        assert data["To"].startswith("whatsapp:")
        assert data["From"].startswith("whatsapp:")

    def test_A_usa_basic_auth(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message(PHONE, TEXT)
        auth = mock_post.call_args[1]["auth"]
        assert auth is not None
        assert len(auth) == 2

    def test_A_normaliza_phone_com_plus(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        with patch("whatsapp.requests.post", return_value=mock_resp) as mock_post:
            send_message("+5531999990000", TEXT)
        data = mock_post.call_args[1]["data"]
        assert data["To"] == "whatsapp:+5531999990000"

    # ── B — FALHAS ─────────────────────────────────────────────

    def test_B_retorna_false_em_connection_error(self):
        with patch("whatsapp.requests.post", side_effect=requests.ConnectionError()):
            assert send_message(PHONE, TEXT) is False

    def test_B_retorna_false_em_timeout(self):
        with patch("whatsapp.requests.post", side_effect=requests.Timeout()):
            assert send_message(PHONE, TEXT) is False

    def test_B_retorna_false_em_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401")
        with patch("whatsapp.requests.post", return_value=mock_resp):
            assert send_message(PHONE, TEXT) is False

    def test_B_nao_lanca_excecao_em_falha(self):
        with patch("whatsapp.requests.post", side_effect=Exception("erro genérico")):
            assert send_message(PHONE, TEXT) is False
