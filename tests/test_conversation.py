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
        mock_session_module["delete_session"].assert_called_once_with(PHONE)

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

    def test_A_pergunta_de_servicos_traz_as_categorias(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_contato", {"razao_social": "X", "cnpj": CNPJ_FMT})
        resp = manager.process(PHONE, "c@e.com")
        assert "Quais serviços?" in resp and "1. Apoio à obra" in resp
        assert resp.index("Ver categorias") < resp.index("1. Apoio à obra")  # instrução antes do menu
        assert ("CATEGORIA 2", "Equipamentos") in resp.lista and len(resp.lista) <= 10

    def test_A_servicos_por_categoria_e_concluir(self, manager, mock_session_module):
        base = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com"}
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_servico", dict(base))
        resp = manager.process(PHONE, "CATEGORIA 2")  # toque em "Equipamentos"
        assert "*Equipamentos*" in resp and "Grua" in resp
        dados = mock_session_module["update_session"].call_args[0][2]
        assert dados["_etapa"] == "cat:1" and "servico" not in dados

        mock_session_module["get_session"].return_value = _make_session("AGUARDA_servico", dados)
        resp = manager.process(PHONE, "3, 5")
        assert "Adicionado: Grua; Manipulador Telescópico" in resp
        assert resp.lista[0] == ("CONCLUIR", "✓ Concluir")
        dados = mock_session_module["update_session"].call_args[0][2]

        mock_session_module["get_session"].return_value = _make_session("AGUARDA_servico", dados)
        resp = manager.process(PHONE, "CONCLUIR")
        assert "Quais regionais?" in resp  # próxima pergunta
        estado, dados = mock_session_module["update_session"].call_args[0][1:3]
        assert estado == "AGUARDA_estados"
        assert dados["servico"] == "Grua; Manipulador Telescópico"
        assert "_etapa" not in dados and "_parcial" not in dados

    def test_A_servico_pelo_nome_sem_abrir_categoria(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com"})
        resp = manager.process(PHONE, "gás, pintura")
        assert "Adicionado: Gás; Pintura" in resp
        assert mock_session_module["update_session"].call_args[0][2]["_parcial"] == [
            "Gás", "Pintura (Interna / Externa / Limpeza)"]

    def test_A_voltar_dentro_da_categoria_volta_as_categorias(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "_etapa": "cat:1"})
        resp = manager.process(PHONE, "VOLTAR")
        assert "1. Apoio à obra" in resp
        estado, dados = mock_session_module["update_session"].call_args[0][1:3]
        assert estado == "AGUARDA_servico" and "_etapa" not in dados and dados["contato"] == "c@e.com"

    def test_B_servico_ambiguo_explica_e_nao_avanca(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com"})
        resp = manager.process(PHONE, "reservatório")
        assert "mais de uma opção" in resp
        assert mock_session_module["update_session"].call_args[0][1] == "AGUARDA_servico"

    def test_B_varios_numeros_sem_categoria_aberta(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com"})
        resp = manager.process(PHONE, "3, 15")
        assert "uma categoria por vez" in resp
        assert mock_session_module["update_session"].call_args[0][3] == {"servico": 1}

    def test_B_concluir_sem_nada_escolhido(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com"})
        resp = manager.process(PHONE, "CONCLUIR")
        assert "pelo menos um serviço" in resp

    def test_A_regional_tocada_pergunta_se_quer_mais(self, manager, mock_session_module):
        base = {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Gás"}
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_estados", dict(base))
        resp = manager.process(PHONE, "MG")
        assert "Regionais escolhidas até agora: MG" in resp
        assert resp.lista[0] == ("CONCLUIR", "✓ Concluir") and ("MG", "MG") not in resp.lista
        dados = mock_session_module["update_session"].call_args[0][2]

        mock_session_module["get_session"].return_value = _make_session("AGUARDA_estados", dados)
        manager.process(PHONE, "SP")
        dados = mock_session_module["update_session"].call_args[0][2]
        mock_session_module["get_session"].return_value = _make_session("AGUARDA_estados", dados)
        resp = manager.process(PHONE, "Concluir")
        assert "Resumo do cadastro" in resp and "MG, SP" in resp

    def test_A_pergunta_de_regionais_tem_lista_com_todas(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_servico", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com",
                                "_parcial": ["Gás"], "_etapa": "mais"})
        resp = manager.process(PHONE, "concluir")
        assert "Quais regionais?" in resp
        assert ("TODAS", "Todas as regionais") in resp.lista and len(resp.lista) == 9

    def test_A_voltar_nas_regionais_volta_para_servicos(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_estados", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Gás",
                                "_parcial": ["MG"], "_etapa": "mais"})
        resp = manager.process(PHONE, "VOLTAR")
        assert "Quais serviços?" in resp
        estado, dados = mock_session_module["update_session"].call_args[0][1:3]
        assert estado == "AGUARDA_servico" and "_parcial" not in dados and "servico" not in dados

    def test_A_regional_todas(self, manager, mock_session_module):
        mock_session_module["get_session"].return_value = _make_session(
            "AGUARDA_estados", {"razao_social": "X", "cnpj": CNPJ_FMT, "contato": "c@e.com", "servico": "Gás"})
        resp = manager.process(PHONE, "TODAS")
        assert "Resumo do cadastro" in resp and "MG, SP, RJ, BA, PE, DF/GO, CE, AM" in resp

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
        assert "1. Apoio à obra" in resp and resp.lista
