"""
Fixtures compartilhadas entre todos os testes.
"""
import os
import tempfile
import pytest
from unittest.mock import MagicMock

# Os testes não podem depender do .env real (que hoje usa Meta).
os.environ.setdefault("WHATSAPP_PROVIDER", "Twilio")
# Nunca mandar e-mail de verdade nos testes, mesmo que o .env tenha NOTIFY_EMAIL.
os.environ["NOTIFY_EMAIL"] = ""
os.environ["DIRECIOZAP_LOG_DIR"] = tempfile.mkdtemp(prefix="direciozap-logs-")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest000000000000000000000000000000")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_auth_token")
os.environ.setdefault("TWILIO_WHATSAPP_FROM", "+14155238886")
os.environ.setdefault("VERIFY_TOKEN", "test_verify_token")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_RAW_VALIDO = "11222333000181"
CNPJ_INVALIDO = "11.111.111/1111-11"
PHONE = "5531999990000"

SAMPLE_PERGUNTAS = [
    {
        "id": 1, "ordem": 1, "campo": "razao_social", "label": "Razão Social",
        "pergunta": "Qual é a Razão Social da sua empresa?",
        "tipo": "texto", "msg_erro": None, "ativo": True,
    },
    {
        "id": 2, "ordem": 2, "campo": "cnpj", "label": "CNPJ",
        "pergunta": "Me informe o CNPJ da empresa:",
        "tipo": "cnpj", "msg_erro": "⚠️ CNPJ inválido. Informe um CNPJ com 14 dígitos:", "ativo": True,
    },
    {
        "id": 3, "ordem": 3, "campo": "contato", "label": "Contato",
        "pergunta": "Qual o contato principal? (telefone ou e-mail):",
        "tipo": "contato", "msg_erro": "⚠️ Formato inválido. Informe telefone ou e-mail:", "ativo": True,
    },
    {
        "id": 4, "ordem": 4, "campo": "servico", "label": "Serviço",
        "pergunta": "Que tipo de serviço sua empresa oferece?",
        "tipo": "texto", "msg_erro": None, "ativo": True,
    },
    {
        "id": 5, "ordem": 5, "campo": "estados", "label": "Estados",
        "pergunta": "Em quais estados vocês atuam? (Ex: MG, SP, RJ):",
        "tipo": "estados", "msg_erro": "⚠️ Siglas inválidas. Use as siglas oficiais (ex: MG, SP):", "ativo": True,
    },
]


@pytest.fixture
def sample_perguntas():
    return SAMPLE_PERGUNTAS


@pytest.fixture(autouse=True)
def bloquear_outlook(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("notificacao.enviar_outlook", mock)
    return mock


@pytest.fixture(autouse=True)
def sem_consulta_receita(monkeypatch):
    """Nenhum teste consulta a Receita de verdade; por padrão a consulta "falha" (None)."""
    mock = MagicMock(return_value=None)
    monkeypatch.setattr("receita._buscar", mock)
    return mock


@pytest.fixture
def mock_send_message(monkeypatch):
    mock = MagicMock(return_value=True)
    monkeypatch.setattr("whatsapp.send_message", mock)
    return mock
