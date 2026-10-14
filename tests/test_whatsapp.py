"""
Testes A/B — whatsapp.py (cliente Twilio WhatsApp)
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


# ─── Mensagens interativas (Meta) ──────────────────────────────

from conversation import Resposta
import whatsapp


@pytest.fixture
def meta(monkeypatch):
    monkeypatch.setattr("whatsapp.settings.WHATSAPP_PROVIDER", "Meta")
    post = MagicMock(return_value=MagicMock(ok=True))
    monkeypatch.setattr("whatsapp._http.post", post)
    return post


def test_A_botoes_viram_interactive_button(meta):
    whatsapp.send_message("5531", Resposta("Resumo", botoes=[("SIM", "Confirmar"), ("NAO", "Recomeçar")]))
    body = meta.call_args.kwargs["json"]
    assert body["type"] == "interactive" and body["interactive"]["type"] == "button"
    assert [b["reply"]["id"] for b in body["interactive"]["action"]["buttons"]] == ["SIM", "NAO"]


def test_A_lista_vira_interactive_list_com_titulos_cortados(meta):
    whatsapp.send_message("5531", Resposta("Qual?", lista=[("ALTERAR X", "Um título bem comprido demais aqui")]))
    row = meta.call_args.kwargs["json"]["interactive"]["action"]["sections"][0]["rows"][0]
    assert row["id"] == "ALTERAR X" and len(row["title"]) <= 24


def test_A_texto_longo_vai_antes_e_botoes_com_corpo_curto(meta):
    whatsapp.send_message("5531", Resposta("x" * 1500, botoes=[("SIM", "Confirmar")]))
    primeiro, segundo = [c.kwargs["json"] for c in meta.call_args_list]
    assert primeiro["type"] == "text" and len(primeiro["text"]["body"]) == 1500
    assert segundo["interactive"]["body"]["text"] == "Escolha uma opção:"


def test_B_interativo_recusado_cai_para_texto(meta):
    meta.side_effect = [MagicMock(ok=False, status_code=400, text="erro"), MagicMock(ok=True)]
    assert whatsapp.send_message("5531", Resposta("Resumo", botoes=[("SIM", "Confirmar")])) is True
    assert meta.call_args.kwargs["json"]["type"] == "text"


def test_A_texto_simples_continua_text(meta):
    whatsapp.send_message("5531", "olá")
    assert meta.call_args.kwargs["json"] == {"messaging_product": "whatsapp", "to": "5531", "type": "text", "text": {"body": "olá"}}
