"""
Testes A/B — conversation.py (fluxo dinâmico via tabela perguntas)
A = fluxo feliz (dados válidos, cadastro completo)
B = fluxos de erro (dados inválidos, max tentativas, expiração)
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

from conversation import ConversationManager, MSGS
from tests.conftest import SAMPLE_PERGUNTAS, CNPJ_VALIDO, CNPJ_RAW_VALIDO, PHONE

CNPJ_FMT = CNPJ_VALIDO


def _make_session(state="SAUDACAO", dados=None, tentativas=None, horas_atras=0):
    ts = datetime.now(timezone.utc) - timedelta(hours=horas_atras)
    return {
        "phone": PHONE,
        "state": state,
        "dados": dados or {},
        "tentativas": tentativas or {},
        "criado_em": ts.isoformat(),
        "atualizado_em": ts.isoformat(),
    }


@pytest.fixture
def manager():
    return ConversationManager()


@pytest.fixture
def mock_session_module(monkeypatch, sample_perguntas):
    mocks = {
        "get_session": MagicMock(return_value=None),
        "create_session": MagicMock(side_effect=lambda p: _make_session()),
        "update_session": MagicMock(),
        "delete_session": MagicMock(),
        "get_perguntas": MagicMock(return_value=sample_perguntas),
        "save_cadastro": MagicMock(),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(f"conversation.{name}", mock)
    return mocks


@pytest.fixture
def mock_excel(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("conversation.append_fornecedor", mock)
    return mock


# ─────────────────────────────────────────────────────────────
#  A — FLUXO FELIZ COMPLETO
# ─────────────────────────────────────────────────────────────

class TestFluxoFeliz:
    def test_A_saudacao_nova_sessao(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = None
        resp = manager.process(PHONE, "Quero me cadastrar")
        assert "Razão Social" in resp
        mock_session_module["create_session"].assert_called_once_with(PHONE)

    def test_A_coleta_razao_social(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_razao_social")
        resp = manager.process(PHONE, "empresa exemplo ltda")
        assert "CNPJ" in resp
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][1] == "AGUARDA_cnpj"
        assert update_call[0][2]["razao_social"] == "empresa exemplo ltda"

    def test_A_coleta_cnpj_sem_pontuacao(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_cnpj", {"razao_social": "EMPRESA EXEMPLO LTDA"}
        )
        resp = manager.process(PHONE, CNPJ_RAW_VALIDO)
        assert "contato" in resp.lower()
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][2]["cnpj"] == CNPJ_FMT

    def test_A_coleta_contato_celular(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_contato", {"razao_social": "X", "cnpj": CNPJ_FMT}
        )
        resp = manager.process(PHONE, "31999990000")
        assert "serviço" in resp.lower()
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][2]["contato"] == "(31) 99999-0000"

    def test_A_coleta_contato_email(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_contato", {"razao_social": "X", "cnpj": CNPJ_FMT}
        )
        resp = manager.process(PHONE, "contato@empresa.com")
        assert "serviço" in resp.lower()
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][2]["contato"] == "contato@empresa.com"

    def test_A_coleta_servico(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico",
            {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "contato@e.com"},
        )
        resp = manager.process(PHONE, "consultoria em ti")
        assert "estados" in resp.lower()
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][2]["servico"] == "consultoria em ti"

    def test_A_coleta_estados(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_estados",
            {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "TI"},
        )
        resp = manager.process(PHONE, "MG, SP")
        assert "Resumo" in resp
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][2]["estados"] == "MG, SP"

    def test_A_confirmacao_salva_supabase_e_excel(self, manager, mock_session_module, mock_excel):
        dados = {
            "razao_social": "EMPRESA LTDA",
            "cnpj": CNPJ_FMT,
            "contato": "c@e.com",
            "servico": "TI",
            "estados": "MG, SP",
        }
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "S")
        assert MSGS["SUCESSO"] in resp
        mock_session_module["save_cadastro"].assert_called_once_with(PHONE, dados)
        mock_excel.assert_called_once_with(PHONE, dados, SAMPLE_PERGUNTAS)
        mock_session_module["delete_session"].assert_called_once_with(PHONE)

    def test_A_confirmacao_sim_variantes(self, manager, mock_session_module, mock_excel):
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        for variante in ["SIM", "s", "sim", "YES", "Y"]:
            mock_excel.reset_mock()
            mock_session_module["save_cadastro"].reset_mock()
            mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
            resp = manager.process(PHONE, variante)
            assert MSGS["SUCESSO"] in resp


# ─────────────────────────────────────────────────────────────
#  B — FLUXOS DE ERRO
# ─────────────────────────────────────────────────────────────

class TestFluxoErro:
    def test_B_cnpj_invalido_primeira_vez(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_cnpj", {"razao_social": "X"}
        )
        resp = manager.process(PHONE, "12345678000000")
        assert "inválido" in resp
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][1] == "AGUARDA_cnpj"
        assert update_call[0][3].get("cnpj") == 1

    def test_B_cnpj_invalido_segunda_vez(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_cnpj", {"razao_social": "X"}, {"cnpj": 1}
        )
        resp = manager.process(PHONE, "00000000000000")
        assert "inválido" in resp
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][3].get("cnpj") == 2

    def test_B_cnpj_invalido_max_tentativas(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_cnpj", {"razao_social": "X"}, {"cnpj": 2}
        )
        resp = manager.process(PHONE, "00000000000000")
        assert MSGS["MAX_TENTATIVAS"] in resp
        mock_session_module["delete_session"].assert_called_once_with(PHONE)

    def test_B_contato_invalido_max_tentativas(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_contato", {"razao_social": "X", "cnpj": CNPJ_FMT}, {"contato": 2}
        )
        resp = manager.process(PHONE, "invalido")
        assert MSGS["MAX_TENTATIVAS"] in resp
        mock_session_module["delete_session"].assert_called_once_with(PHONE)

    def test_B_estados_invalidos_max_tentativas(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_estados",
            {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y"},
            {"estados": 2},
        )
        resp = manager.process(PHONE, "ZZ")
        assert MSGS["MAX_TENTATIVAS"] in resp

    def test_B_confirmacao_negativa_reinicia(self, manager, mock_session_module, mock_excel):
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "N")
        assert MSGS["REINICIO"] in resp
        mock_excel.assert_not_called()
        mock_session_module["delete_session"].assert_called_with(PHONE)

    def test_B_confirmacao_resposta_invalida(self, manager, mock_session_module, mock_excel):
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "talvez")
        assert "S" in resp and "N" in resp
        mock_excel.assert_not_called()

    def test_B_sessao_expirada_reinicia(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_cnpj", horas_atras=25
        )
        resp = manager.process(PHONE, "qualquer coisa")
        mock_session_module["delete_session"].assert_called_once_with(PHONE)
        mock_session_module["create_session"].assert_called_with(PHONE)

    def test_B_erro_ao_salvar_retorna_mensagem_erro(self, manager, mock_session_module, mock_excel):
        mock_excel.side_effect = IOError("disco cheio")
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "S")
        assert MSGS["ERRO_SALVAR"] in resp

    def test_B_razao_social_vazia_rejeita(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_razao_social")
        resp = manager.process(PHONE, "   ")
        assert "Razão Social" in resp

    def test_B_sem_perguntas_configuradas(self, manager, mock_session_module):
        mock_session_module["get_perguntas"].return_value = []
        resp = manager.process(PHONE, "oi")
        assert MSGS["SEM_CONFIG"] in resp
