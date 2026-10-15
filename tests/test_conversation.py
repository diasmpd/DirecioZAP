"""
Testes A/B — conversation.py (fluxo dinâmico via tabela perguntas)
A = fluxo feliz (dados válidos, cadastro completo)
B = fluxos de erro (dados inválidos, max tentativas, expiração)
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

from conversation import ConversationManager, MSGS, MAX_TENTATIVAS
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

    def test_A_confirmacao_salva_supabase(self, manager, mock_session_module):
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
        # A sessão segue para pedir o e-mail do Portal.
        assert mock_session_module["update_session"].call_args[0][1] == "EMAIL_PORTAL"

    def test_A_confirmacao_sim_variantes(self, manager, mock_session_module):
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        for variante in ["SIM", "s", "sim", "YES", "Y"]:
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

    def test_B_confirmacao_negativa_reinicia(self, manager, mock_session_module):
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "N")
        assert MSGS["REINICIO"] in resp
        mock_session_module["save_cadastro"].assert_not_called()
        mock_session_module["delete_session"].assert_called_with(PHONE)

    def test_B_confirmacao_resposta_invalida(self, manager, mock_session_module):
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "talvez")
        assert "S" in resp and "N" in resp
        mock_session_module["save_cadastro"].assert_not_called()

    def test_B_sessao_expirada_reinicia(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_cnpj", horas_atras=25
        )
        resp = manager.process(PHONE, "qualquer coisa")
        mock_session_module["delete_session"].assert_called_once_with(PHONE)
        mock_session_module["create_session"].assert_called_with(PHONE)

    def test_B_erro_ao_salvar_retorna_mensagem_erro(self, manager, mock_session_module):
        mock_session_module["save_cadastro"].side_effect = IOError("Supabase fora do ar")
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "S")
        assert MSGS["ERRO_SALVAR"] in resp
        mock_session_module["delete_session"].assert_not_called()

    def test_B_falha_ao_encerrar_sessao_apos_salvar_ainda_confirma(self, manager, mock_session_module):
        # Cadastro já salvo: o fornecedor não pode ser levado a confirmar de novo (duplicaria).
        mock_session_module["delete_session"].side_effect = IOError("timeout")
        dados = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "S")
        assert MSGS["SUCESSO"] in resp
        mock_session_module["save_cadastro"].assert_called_once()

    def test_B_razao_social_vazia_rejeita(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_razao_social")
        resp = manager.process(PHONE, "   ")
        assert "Razão Social" in resp

    def test_B_sem_perguntas_configuradas(self, manager, mock_session_module):
        mock_session_module["get_perguntas"].return_value = []
        resp = manager.process(PHONE, "oi")
        assert MSGS["SEM_CONFIG"] in resp


class TestFluxoConversacional:
    def test_C_ajuda_durante_pergunta(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_cnpj", {"razao_social": "Empresa X"}
        )
        resp = manager.process(PHONE, "ajuda")
        assert "Exemplo de CNPJ" in resp
        assert "CNPJ" in resp

    def test_C_voltar_para_pergunta_anterior(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_contato", {"razao_social": "X", "cnpj": CNPJ_FMT}
        )
        resp = manager.process(PHONE, "voltar")
        assert "corrigir" in resp.lower()
        update_call = mock_session_module["update_session"].call_args
        assert update_call[0][1] == "AGUARDA_cnpj"

    def test_C_alterar_campo_na_confirmacao(self, manager, mock_session_module):
        dados = {
            "razao_social": "EMPRESA LTDA",
            "cnpj": CNPJ_FMT,
            "contato": "contato@empresa.com",
            "servico": "Consultoria",
            "estados": "MG, SP",
        }
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "alterar cnpj")
        assert "ajustar" in resp.lower()
        assert CNPJ_FMT in resp  # mostra o valor atual
        state, dados_salvos = mock_session_module["update_session"].call_args[0][1:3]
        assert state == "ALTERA_cnpj"
        assert dados_salvos == dados  # nenhum campo apagado

    def test_C_cancelar_fluxo(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_razao_social")
        resp = manager.process(PHONE, "cancelar")
        assert "encerramos" in resp.lower()
        mock_session_module["delete_session"].assert_called_once_with(PHONE)


DADOS_COMPLETOS = {
    "razao_social": "EMPRESA LTDA",
    "cnpj": CNPJ_FMT,
    "contato": "contato@empresa.com",
    "servico": "Consultoria",
    "estados": "MG, SP",
}


class TestComandosSoComRespostaInteira:
    def test_C_resposta_com_palavra_ajuda_e_aceita(self, manager, mock_session_module):
        dados = {k: DADOS_COMPLETOS[k] for k in ("razao_social", "cnpj", "contato")}
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_servico", dados)
        manager.process(PHONE, "Consultoria e ajuda técnica")
        state, dados_salvos = mock_session_module["update_session"].call_args[0][1:3]
        assert state == "AGUARDA_estados"
        assert dados_salvos["servico"] == "Consultoria e ajuda técnica"

    def test_C_resposta_com_palavra_voltar_e_aceita(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_razao_social")
        manager.process(PHONE, "Voltar Engenharia Ltda")
        state = mock_session_module["update_session"].call_args[0][1]
        assert state == "AGUARDA_cnpj"

    def test_C_ajuda_na_saudacao_avanca_para_primeira_pergunta(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("SAUDACAO")
        manager.process(PHONE, "ajuda")
        state = mock_session_module["update_session"].call_args[0][1]
        assert state == "AGUARDA_razao_social"


class TestAlterarCampoUnico:
    def test_C_resposta_valida_volta_para_confirmacao(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("ALTERA_servico", dict(DADOS_COMPLETOS))
        resp = manager.process(PHONE, "Pintura")
        state, dados_salvos = mock_session_module["update_session"].call_args[0][1:3]
        assert state == "CONFIRMACAO"
        assert dados_salvos == {**DADOS_COMPLETOS, "servico": "Pintura"}
        assert "Resumo do cadastro" in resp

    def test_C_voltar_mantem_valor_anterior(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("ALTERA_cnpj", dict(DADOS_COMPLETOS))
        resp = manager.process(PHONE, "voltar")
        state, dados_salvos = mock_session_module["update_session"].call_args[0][1:3]
        assert state == "CONFIRMACAO"
        assert dados_salvos == DADOS_COMPLETOS
        assert "valor anterior" in resp

    def test_C_max_tentativas_mantem_valor_e_nao_apaga_sessao(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "ALTERA_cnpj", dict(DADOS_COMPLETOS), {"cnpj": MAX_TENTATIVAS - 1}
        )
        resp = manager.process(PHONE, "123")
        state, dados_salvos = mock_session_module["update_session"].call_args[0][1:3]
        assert state == "CONFIRMACAO"
        assert dados_salvos["cnpj"] == CNPJ_FMT
        mock_session_module["delete_session"].assert_not_called()
        assert "valor anterior" in resp

    def test_C_resposta_invalida_continua_no_campo(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("ALTERA_cnpj", dict(DADOS_COMPLETOS))
        manager.process(PHONE, "123")
        state = mock_session_module["update_session"].call_args[0][1]
        assert state == "ALTERA_cnpj"

    def test_C_alterar_campo_desconhecido(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dict(DADOS_COMPLETOS))
        resp = manager.process(PHONE, "alterar endereço")
        assert "Não identifiquei" in resp
        mock_session_module["update_session"].assert_not_called()

    def test_C_alterar_por_label(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dict(DADOS_COMPLETOS))
        manager.process(PHONE, "mudar razão social")
        state = mock_session_module["update_session"].call_args[0][1]
        assert state == "ALTERA_razao_social"


class TestConfirmacaoFlexivel:
    DADOS = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Y", "estados": "MG"}

    @pytest.mark.parametrize("texto", ["Sim!", "s.", "Sim, confirmo", "SIM 👍", "ok", "Confirmo", "Correto"])
    def test_A_aceita_variantes_de_sim(self, manager, mock_session_module, texto):
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", self.DADOS)
        assert MSGS["SUCESSO"] in manager.process(PHONE, texto)

    @pytest.mark.parametrize("texto", ["Não.", "nao!", "N", "não, quero corrigir"])
    def test_A_aceita_variantes_de_nao(self, manager, mock_session_module, texto):
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", self.DADOS)
        resp = manager.process(PHONE, texto)
        assert MSGS["REINICIO"] in resp
        mock_session_module["save_cadastro"].assert_not_called()

    @pytest.mark.parametrize("texto", ["sim não", "talvez", "simples", "nada"])
    def test_B_ambiguo_ou_outra_palavra_nao_confirma(self, manager, mock_session_module, texto):
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", self.DADOS)
        resp = manager.process(PHONE, texto)
        assert MSGS["CONFIRMACAO_INVALIDA"] in resp
        mock_session_module["save_cadastro"].assert_not_called()

    def test_A_cadastro_salvo_com_nono_digito(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", self.DADOS)
        manager.process("553195971053", "S")
        mock_session_module["save_cadastro"].assert_called_once_with("5531995971053", self.DADOS)



PERGUNTAS_MENU = [
    *SAMPLE_PERGUNTAS[:3],
    {"id": 4, "ordem": 4, "campo": "servico", "label": "Serviços", "pergunta": "Quais serviços?",
     "tipo": "servicos", "msg_erro": None, "ativo": True},
    {"id": 5, "ordem": 5, "campo": "estados", "label": "Regionais", "pergunta": "Quais regionais?",
     "tipo": "estados_atendidos", "msg_erro": None, "ativo": True},
]


class TestMenus:
    @pytest.fixture(autouse=True)
    def _perguntas(self, mock_session_module):
        mock_session_module["get_perguntas"].return_value = PERGUNTAS_MENU

    def test_A_pergunta_de_servicos_traz_o_menu(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_contato", {"razao_social": "X", "cnpj": CNPJ_FMT})
        resp = manager.process(PHONE, "c@e.com")
        assert "Quais serviços?" in resp and "1. Acompanhamento Topográfico" in resp and "70. " in resp

    def test_A_servicos_por_numero(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com"})
        resp = manager.process(PHONE, "1, 2")
        assert "1. MG" in resp  # próxima pergunta, com o menu de regionais
        assert mock_session_module["update_session"].call_args[0][2]["servico"].count(";") == 1

    def test_B_servico_ambiguo_explica_e_nao_avanca(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com"})
        resp = manager.process(PHONE, "elevador")
        assert "mais de uma opção" in resp
        assert mock_session_module["update_session"].call_args[0][1] == "AGUARDA_servico"

    def test_A_resumo_vem_com_botoes(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_estados", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Gás"})
        resp = manager.process(PHONE, "MG, DF")
        assert "Resumo do cadastro" in resp and "DF/GO" in resp
        assert [b[0] for b in resp.botoes] == ["SIM", "NAO", "ALTERAR"]

    def test_A_botao_alterar_abre_lista_de_campos(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dict(DADOS_COMPLETOS))
        resp = manager.process(PHONE, "ALTERAR")
        assert "Qual informação" in resp
        assert ("ALTERAR Serviços", "Serviços") in resp.lista
        mock_session_module["update_session"].assert_not_called()

    def test_A_item_da_lista_inicia_alteracao(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session("CONFIRMACAO", dict(DADOS_COMPLETOS))
        resp = manager.process(PHONE, "ALTERAR Serviços")
        assert mock_session_module["update_session"].call_args[0][1] == "ALTERA_servico"
        assert "1. Acompanhamento Topográfico" in resp


# ─────────────────────────────────────────────────────────────
#  E-mail do Portal do Fornecedor (depois da confirmação)
# ─────────────────────────────────────────────────────────────

class TestEmailPortal:
    DADOS = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "(31) 99999-0000", "servico": "Y", "estados": "MG"}

    @pytest.fixture
    def mocks(self, mock_session_module, monkeypatch):
        mock_session_module["save_cadastro"].return_value = "id-1"
        completar = MagicMock()
        monkeypatch.setattr("conversation.completar_cadastro", completar)
        mock_session_module["completar_cadastro"] = completar
        return mock_session_module

    def _em_email(self, mocks, sugestao=None, tentativas=None):
        dados = {"_cadastro_id": "id-1"}
        if sugestao:
            dados["_sugestao_email"] = sugestao
        mocks["get_session"].return_value = _make_session("EMAIL_PORTAL", dados, tentativas)

    def test_A_confirmar_pede_email_com_botao_agora_nao(self, manager, mocks):
        mocks["get_session"].return_value = _make_session("CONFIRMACAO", self.DADOS)
        resp = manager.process(PHONE, "S")
        assert MSGS["SUCESSO"] in resp and "Qual e-mail" in resp
        assert resp.botoes == [("PULAR", "Agora não")]
        mocks["update_session"].assert_called_once_with(PHONE, "EMAIL_PORTAL", {"_cadastro_id": "id-1"}, {})
        mocks["delete_session"].assert_not_called()

    def test_A_contato_email_vira_sugestao_de_um_toque(self, manager, mocks):
        dados = dict(self.DADOS, contato="compras@empresa.com.br")
        mocks["get_session"].return_value = _make_session("CONFIRMACAO", dados)
        resp = manager.process(PHONE, "S")
        assert "compras@empresa.com.br" in resp
        assert resp.botoes[0] == ("USAR", "Usar este e-mail")
        assert all(len(t) <= 20 for _, t in resp.botoes)

    @pytest.mark.parametrize("texto", ["USAR", "sim", "Usar este e-mail"])
    def test_A_usar_sugestao(self, manager, mocks, texto):
        self._em_email(mocks, sugestao="compras@empresa.com.br")
        resp = manager.process(PHONE, texto)
        mocks["completar_cadastro"].assert_called_once_with("id-1", {"email_portal": "compras@empresa.com.br"})
        assert "compras@empresa.com.br" in resp
        mocks["delete_session"].assert_called_once_with(PHONE)

    def test_A_email_digitado_vale_mais_que_a_sugestao(self, manager, mocks):
        self._em_email(mocks, sugestao="contato@empresa.com.br")
        manager.process(PHONE, "É o Cotacoes@Empresa.com.br")
        mocks["completar_cadastro"].assert_called_once_with("id-1", {"email_portal": "cotacoes@empresa.com.br"})

    @pytest.mark.parametrize("texto", ["PULAR", "Agora não", "não", "depois"])
    def test_A_pular_manda_link_do_portal(self, manager, mocks, texto):
        self._em_email(mocks)
        resp = manager.process(PHONE, texto)
        assert "fornecedor.direcional.com.br" in resp
        mocks["completar_cadastro"].assert_not_called()
        mocks["delete_session"].assert_called_once_with(PHONE)

    def test_B_texto_sem_email_pede_de_novo(self, manager, mocks):
        self._em_email(mocks)
        resp = manager.process(PHONE, "obrigado")
        assert resp == MSGS["EMAIL_PORTAL_INVALIDO"]
        mocks["completar_cadastro"].assert_not_called()
        assert mocks["update_session"].call_args[0][3] == {"EMAIL_PORTAL": 1}

    def test_B_tentativas_esgotadas_encerra_com_link(self, manager, mocks):
        self._em_email(mocks, tentativas={"EMAIL_PORTAL": MAX_TENTATIVAS - 1})
        resp = manager.process(PHONE, "???")
        assert "fornecedor.direcional.com.br" in resp
        mocks["delete_session"].assert_called_once_with(PHONE)

    def test_B_falha_ao_abrir_etapa_ainda_confirma_com_link(self, manager, mocks):
        mocks["update_session"].side_effect = IOError("timeout")
        mocks["get_session"].return_value = _make_session("CONFIRMACAO", self.DADOS)
        resp = manager.process(PHONE, "S")
        assert MSGS["SUCESSO"] in resp and "fornecedor.direcional.com.br" in resp
        mocks["save_cadastro"].assert_called_once()

    def test_B_falha_ao_gravar_email_mantem_sessao(self, manager, mocks):
        self._em_email(mocks)
        mocks["completar_cadastro"].side_effect = IOError("timeout")
        resp = manager.process(PHONE, "a@b.com")
        assert resp == MSGS["ERRO_TECNICO"]
        mocks["delete_session"].assert_not_called()
