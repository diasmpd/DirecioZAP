"""
Fixtures compartilhadas entre todos os testes.
"""
import os
import pytest
from unittest.mock import MagicMock, patch

# Variáveis de ambiente mínimas para importar config sem .env real
os.environ.setdefault("EVOLUTION_API_URL", "http://localhost:8080")
os.environ.setdefault("EVOLUTION_API_KEY", "test_api_key")
os.environ.setdefault("EVOLUTION_INSTANCE", "test-instance")
os.environ.setdefault("VERIFY_TOKEN", "test_verify_token")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test_supabase_key")
os.environ.setdefault("EXCEL_PATH", "/tmp/test_fornecedores.xlsx")


@pytest.fixture
def mock_supabase(monkeypatch):
    """Mock do cliente Supabase para evitar chamadas reais."""
    mock = MagicMock()
    monkeypatch.setattr("supabase_session._client", mock)
    return mock


@pytest.fixture
def mock_send_message(monkeypatch):
    """Mock do envio de mensagem via Evolution API."""
    mock = MagicMock(return_value=True)
    monkeypatch.setattr("whatsapp.send_message", mock)
    return mock


@pytest.fixture(autouse=True)
def limpar_excel_teste():
    """Remove o Excel de teste antes e depois de cada teste."""
    path = os.environ["EXCEL_PATH"]
    if os.path.exists(path):
        os.remove(path)
    yield
    if os.path.exists(path):
        os.remove(path)


CNPJ_VALIDO = "11.222.333/0001-81"
CNPJ_RAW_VALIDO = "11222333000181"
CNPJ_INVALIDO = "11.111.111/1111-11"
PHONE = "5531999990000"
