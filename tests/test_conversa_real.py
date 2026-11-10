"""
Mensagens fora do roteiro que chegam de usuários reais: quem não é fornecedor, "oi" em várias
mensagens seguidas, perguntas, áudio/foto, "obrigado" depois do fim, pedido de atendente.
Usa as perguntas padrão (CNPJ primeiro).
"""
import pytest

from conversation import BOTAO_NAO_FORNECEDOR, MSGS, URL_CONTATO_DIRECIONAL, CONTATO_EQUIPE
from db import PERGUNTAS_PADRAO
from tests.conftest import PHONE
from tests.test_conversation import _make_session, manager, mock_session_module  # noqa: F401 (fixtures)

POUCO_TEMPO_ATRAS = 0  # horas: a última mensagem do bot acabou de sair
MINUTOS_ATRAS = 0.05   # horas (3 minutos): fora da janela de rajada


@pytest.fixture
def mocks(mock_session_module):
    perguntas = [
        {"id": o, "ordem": o, "campo": c, "label": l, "pergunta": p, "tipo": t, "msg_erro": e, "ativo": True}
        for o, c, l, p, t, e in PERGUNTAS_PADRAO
    ]
    mock_session_module["get_perguntas"].return_value = perguntas
    return mock_session_module


def _em(mocks, state, dados=None, tentativas=None, horas_atras=POUCO_TEMPO_ATRAS):
    mocks["get_session"].return_value = _make_session(state, dados, tentativas, horas_atras)


def _sem_tentativa(mocks, state, dados=None, tentativas=None):
    """Respondeu sem contar tentativa: a sessão é só renovada (mesmo estado, dados e contagem),
    para a janela de mensagens seguidas valer a partir desta resposta."""
    mocks["update_session"].assert_called_once_with(PHONE, state, dados or {}, tentativas or {})


class TestNaoFornecedor:
    def test_saudacao_tem_botao_nao_sou_fornecedor(self, manager, mocks):
        resp = manager.process(PHONE, "Olá")
        assert MSGS["SAUDACAO"] in resp and "CNPJ" in resp
        assert BOTAO_NAO_FORNECEDOR in resp.botoes
        assert all(len(t) <= 20 for _, t in resp.botoes)

    @pytest.mark.parametrize("texto", ["NAO_FORNECEDOR", "Não sou fornecedor", "nao sou fornecedor!"])
    def test_botao_ou_frase_encerra_com_link(self, manager, mocks, texto):
        _em(mocks, "AGUARDA_cnpj")
        resp = manager.process(PHONE, texto)
        assert URL_CONTATO_DIRECIONAL in resp
        mocks["delete_session"].assert_called_once_with(PHONE)

    @pytest.mark.parametrize("texto", [
        "Quero comprar um apartamento",
        "Tenho uma reclamação do meu apto",
        "vocês têm vaga de emprego?",
        "Onde mando meu currículo",
        "segunda via do boleto",
    ])
    def test_assunto_de_cliente_recebe_link_sem_contar_tentativa(self, manager, mocks, texto):
        _em(mocks, "AGUARDA_cnpj")
        resp = manager.process(PHONE, texto)
        assert URL_CONTATO_DIRECIONAL in resp
        assert "CNPJ" in resp  # quem é fornecedor pode seguir
        _sem_tentativa(mocks, "AGUARDA_cnpj")
        mocks["delete_session"].assert_not_called()

    def test_razao_social_com_palavra_de_cliente_continua_valendo(self, manager, mocks):
        _em(mocks, "AGUARDA_razao_social", {"cnpj": "11.222.333/0001-81"})
        manager.process(PHONE, "Imóveis e Apartamentos Ltda")
        assert mocks["update_session"].call_args[0][2]["razao_social"] == "Imóveis e Apartamentos Ltda"


class TestSemCnpj:
    @pytest.mark.parametrize("texto", ["não tenho CNPJ", "sou pessoa física", "123.456.789-09"])
    def test_explica_que_precisa_de_cnpj(self, manager, mocks, texto):
        _em(mocks, "AGUARDA_cnpj")
        resp = manager.process(PHONE, texto)
        assert resp == MSGS["SEM_CNPJ"]
        assert CONTATO_EQUIPE in resp
        _sem_tentativa(mocks, "AGUARDA_cnpj")


class TestAtendente:
    @pytest.mark.parametrize("texto", ["ATENDENTE", "Falar com alguém", "quero falar com um atendente"])
    def test_comando_mostra_contato_e_repete_pergunta(self, manager, mocks, texto):
        _em(mocks, "AGUARDA_cnpj")
        resp = manager.process(PHONE, texto)
        assert CONTATO_EQUIPE in resp and "CNPJ" in resp
        _sem_tentativa(mocks, "AGUARDA_cnpj")

    def test_pedido_no_meio_da_frase(self, manager, mocks):
        _em(mocks, "AGUARDA_email_portal", {"cnpj": "x", "razao_social": "X"})
        resp = manager.process(PHONE, "prefiro falar com uma pessoa por favor")
        assert CONTATO_EQUIPE in resp
        _sem_tentativa(mocks, "AGUARDA_email_portal", {"cnpj": "x", "razao_social": "X"})

    def test_pergunta_qualquer_nao_conta_tentativa(self, manager, mocks):
        _em(mocks, "AGUARDA_cnpj")
        resp = manager.process(PHONE, "quanto tempo demora a aprovação?")
        assert CONTATO_EQUIPE in resp and "CNPJ" in resp
        _sem_tentativa(mocks, "AGUARDA_cnpj")

    def test_pergunta_nao_vira_razao_social(self, manager, mocks):
        _em(mocks, "AGUARDA_razao_social", {"cnpj": "11.222.333/0001-81"})
        resp = manager.process(PHONE, "O que é razão social?")
        assert "Razão Social" in resp
        _sem_tentativa(mocks, "AGUARDA_razao_social", {"cnpj": "11.222.333/0001-81"})

    def test_ajuda_lista_o_comando(self):
        assert "ATENDENTE" in MSGS["AJUDA_GERAL"]


class TestMensagensSeguidas:
    @pytest.mark.parametrize("texto", ["oi", "Tudo bem?", "Bom dia!!", "quero me cadastrar", "👍", "vi no linkedin"])
    def test_conversa_logo_depois_do_bot_fica_sem_resposta(self, manager, mocks, texto):
        _em(mocks, "AGUARDA_cnpj", horas_atras=POUCO_TEMPO_ATRAS)
        assert manager.process(PHONE, texto) == ""
        mocks["update_session"].assert_not_called()

    def test_conversa_depois_de_um_tempo_repete_a_pergunta(self, manager, mocks):
        _em(mocks, "AGUARDA_cnpj", horas_atras=MINUTOS_ATRAS)
        resp = manager.process(PHONE, "oi")
        assert MSGS["CONTINUAR"] in resp and "CNPJ" in resp
        _sem_tentativa(mocks, "AGUARDA_cnpj")

    def test_oi_nao_vira_razao_social(self, manager, mocks):
        _em(mocks, "AGUARDA_razao_social", {"cnpj": "x"}, horas_atras=MINUTOS_ATRAS)
        manager.process(PHONE, "Oi")
        _sem_tentativa(mocks, "AGUARDA_razao_social", {"cnpj": "x"})

    def test_cnpj_valido_logo_depois_continua_valendo(self, manager, mocks):
        _em(mocks, "AGUARDA_cnpj", horas_atras=POUCO_TEMPO_ATRAS)
        manager.process(PHONE, "11.222.333/0001-81")
        assert mocks["update_session"].call_args[0][2]["cnpj"]


class TestTentativas:
    def test_terceiro_erro_mantem_respostas_e_oferece_equipe(self, manager, mocks):
        dados = {"cnpj": "x", "razao_social": "X"}
        _em(mocks, "AGUARDA_email_portal", dados, {"email_portal": 2})
        resp = manager.process(PHONE, "nao sei")
        assert CONTATO_EQUIPE in resp and "e-mail" in resp
        mocks["delete_session"].assert_not_called()
        _, state, dados_salvos, tentativas = mocks["update_session"].call_args[0]
        assert state == "AGUARDA_email_portal" and dados_salvos == dados and tentativas == {}


class TestDepoisDoCadastro:
    @pytest.mark.parametrize("texto", ["Obrigado!", "👍", "ok", "12.345.678/0001-90"])
    def test_mensagem_depois_do_fim_nao_abre_cadastro_novo(self, manager, mocks, texto):
        _em(mocks, "CONCLUIDO")
        resp = manager.process(PHONE, texto)
        assert resp == MSGS["CONCLUIDO"]
        mocks["create_session"].assert_not_called()
        mocks["update_session"].assert_not_called()

    def test_recomecar_abre_cadastro_novo(self, manager, mocks):
        _em(mocks, "CONCLUIDO")
        resp = manager.process(PHONE, "RECOMEÇAR")
        assert "CNPJ" in resp
        assert mocks["update_session"].call_args[0][1] == "AGUARDA_cnpj"


class TestMidia:
    def test_audio_avisa_e_repete_a_pergunta(self, manager, mocks):
        _em(mocks, "AGUARDA_cnpj", {}, {"cnpj": 1})
        resp = manager.process_midia(PHONE, "audio")
        assert MSGS["MIDIA_AUDIO"] in resp and "CNPJ" in resp
        _sem_tentativa(mocks, "AGUARDA_cnpj", {}, {"cnpj": 1})

    def test_foto_no_resumo_repete_o_resumo_com_botoes(self, manager, mocks):
        dados = {"cnpj": "x", "razao_social": "X", "email_portal": "a@b.com", "servico": "Y", "estados": "MG"}
        _em(mocks, "CONFIRMACAO", dados)
        resp = manager.process_midia(PHONE, "image")
        assert MSGS["MIDIA_ARQUIVO"] in resp and "Resumo do cadastro" in resp
        assert resp.botoes

    def test_figurinha_como_primeira_mensagem_recebe_saudacao(self, manager, mocks):
        resp = manager.process_midia(PHONE, "sticker")
        assert MSGS["SAUDACAO"] in resp

    @pytest.mark.parametrize("tipo", ["reaction", "unsupported", "system"])
    def test_reacao_e_sistema_ficam_sem_resposta(self, manager, mocks, tipo):
        assert manager.process_midia(PHONE, tipo) == ""

    def test_midia_depois_do_fim(self, manager, mocks):
        _em(mocks, "CONCLUIDO")
        assert manager.process_midia(PHONE, "audio") == MSGS["CONCLUIDO"]


class TestRevisao721e3fe:
    """Achados da revisão do commit 721e3fe."""

    @pytest.fixture
    def com_pergunta_texto(self, mocks):
        extra = {"id": 9, "ordem": 9, "campo": "alvara", "label": "Alvará", "pergunta": "Possui alvará?",
                 "tipo": "texto", "msg_erro": None, "ativo": True}
        mocks["get_perguntas"].return_value = mocks["get_perguntas"].return_value + [extra]
        return mocks

    @pytest.mark.parametrize("texto", ["Sim", "Ok", "Vi no Instagram", "Não", "Cadastro"])
    def test_texto_livre_aceita_sim_ok_instagram(self, manager, com_pergunta_texto, texto):
        _em(com_pergunta_texto, "AGUARDA_alvara", {"cnpj": "x"})
        manager.process(PHONE, texto)
        assert com_pergunta_texto["update_session"].call_args[0][2]["alvara"] == texto

    @pytest.mark.parametrize("texto", ["oi", "Bom dia!", "tudo bem?"])
    def test_texto_livre_ainda_ignora_cumprimento(self, manager, com_pergunta_texto, texto):
        _em(com_pergunta_texto, "AGUARDA_alvara", {"cnpj": "x"})
        assert manager.process(PHONE, texto) == ""

    @pytest.mark.parametrize("texto", ["ok", "Vi no Instagram", "sim"])
    def test_campo_estruturado_ainda_ignora_conversa(self, manager, mocks, texto):
        _em(mocks, "AGUARDA_cnpj")
        assert manager.process(PHONE, texto) == ""

    @pytest.mark.parametrize("texto", ["pintura, assistencia tecnica xyz", "manutenção de imóvel qualquer"])
    def test_servico_com_palavra_de_cliente_explica_o_item_invalido(self, manager, mocks, texto):
        _em(mocks, "AGUARDA_servico", {"cnpj": "x", "razao_social": "X", "email_portal": "a@b.com"})
        resp = manager.process(PHONE, texto)
        assert URL_CONTATO_DIRECIONAL not in resp
        assert "Não consegui entender" in resp

    def test_celular_no_cnpj_nao_vira_aviso_de_cpf(self, manager, mocks):
        _em(mocks, "AGUARDA_cnpj")
        resp = manager.process(PHONE, "(31) 99999-0000")
        assert resp != MSGS["SEM_CNPJ"]
        assert mocks["update_session"].call_args[0][3] == {"cnpj": 1}  # conta como tentativa

    def test_atendente_como_primeira_mensagem_abre_o_cadastro(self, manager, mocks):
        resp = manager.process(PHONE, "atendente")
        assert CONTATO_EQUIPE in resp and MSGS["SAUDACAO"] in resp and "CNPJ" in resp
        assert mocks["update_session"].call_args[0][1] == "AGUARDA_cnpj"

    def test_cpf_valido(self):
        from conversation import _cpf_valido
        assert _cpf_valido("12345678909")
        assert not _cpf_valido("31999990000")
        assert not _cpf_valido("11111111111")


class TestCartaoDeContato:
    from conversation import CARTAO_EQUIPE as CARTAO

    @pytest.mark.parametrize("state,texto", [
        ("AGUARDA_cnpj", "ATENDENTE"),
        ("AGUARDA_cnpj", "prefiro falar com uma pessoa"),
        ("AGUARDA_cnpj", "quanto tempo demora?"),
        ("AGUARDA_cnpj", "não tenho CNPJ"),
        ("SAUDACAO", "atendente"),
    ])
    def test_respostas_com_a_equipe_levam_o_cartao(self, manager, mocks, state, texto):
        _em(mocks, state)
        assert manager.process(PHONE, texto).cartao == self.CARTAO

    def test_terceiro_erro_leva_o_cartao(self, manager, mocks):
        _em(mocks, "AGUARDA_cnpj", {}, {"cnpj": 2})
        assert manager.process(PHONE, "123").cartao == self.CARTAO

    def test_atendente_no_resumo_mantem_os_botoes(self, manager, mocks):
        dados = {"cnpj": "x", "razao_social": "X", "email_portal": "a@b.com", "servico": "Y", "estados": "MG"}
        _em(mocks, "CONFIRMACAO", dados)
        resp = manager.process(PHONE, "atendente")
        assert resp.cartao == self.CARTAO and resp.botoes

    @pytest.mark.parametrize("state,texto", [("AGUARDA_cnpj", "123"), ("CONCLUIDO", "obrigado")])
    def test_demais_respostas_sem_cartao(self, manager, mocks, state, texto):
        _em(mocks, state)
        assert getattr(manager.process(PHONE, texto), "cartao", None) is None

    def test_wa_id_e_telefone_do_cartao(self):
        fone = self.CARTAO["phones"][0]
        assert fone["wa_id"] == "553197581137" and "99758-1137" in fone["phone"]
