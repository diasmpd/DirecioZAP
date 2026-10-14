"""
Testes A/B — consulta do CNPJ na Receita (receita.py) e o que ela muda na conversa
A = consulta encontra a empresa / fluxo segue
B = consulta falha, CNPJ inativo ou não encontrado
"""
import pytest
from unittest.mock import MagicMock

import receita
from conversation import ConversationManager
from tests.conftest import CNPJ_VALIDO, PHONE, SAMPLE_PERGUNTAS
from tests.test_conversation import _make_session

RAZAO, CNPJ_P, CONTATO = SAMPLE_PERGUNTAS[0], SAMPLE_PERGUNTAS[1], SAMPLE_PERGUNTAS[2]
# Ordem nova: CNPJ antes da Razão Social.
PERGUNTAS_CNPJ_PRIMEIRO = [{**CNPJ_P, "ordem": 1}, {**RAZAO, "ordem": 2}, *SAMPLE_PERGUNTAS[2:]]


def _resposta_api(status=200, json=None):
    resp = MagicMock()
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.json.return_value = json or {}
    return resp


EMPRESA_ATIVA = {
    "razao_social": "EMPRESA TESTE LTDA",
    "descricao_situacao_cadastral": "ATIVA",
    "municipio": "BELO HORIZONTE",
    "uf": "MG",
}


@pytest.fixture
def manager():
    return ConversationManager()


@pytest.fixture
def sessao(monkeypatch):
    mocks = {
        "get_session": MagicMock(return_value=None),
        "create_session": MagicMock(side_effect=lambda p: _make_session()),
        "update_session": MagicMock(),
        "delete_session": MagicMock(),
        "get_perguntas": MagicMock(return_value=PERGUNTAS_CNPJ_PRIMEIRO),
        "save_cadastro": MagicMock(),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(f"conversation.{name}", mock)
    return mocks


# ── receita.consultar_cnpj ─────────────────────────────────────

RECEITAWS_ATIVA = {"status": "OK", "nome": "EMPRESA TESTE LTDA", "situacao": "ATIVA",
                   "municipio": "BELO HORIZONTE", "uf": "MG"}
ESPERADO = {"razao_social": "EMPRESA TESTE LTDA", "situacao": "ATIVA",
            "municipio": "Belo Horizonte", "uf": "MG"}


def _por_fonte(receitaws=None, brasilapi=None):
    return lambda url: receitaws if "receitaws" in url else brasilapi


def test_A_consulta_pela_receitaws(sem_consulta_receita):
    sem_consulta_receita.side_effect = _por_fonte(receitaws=_resposta_api(json=RECEITAWS_ATIVA))
    assert receita.consultar_cnpj(CNPJ_VALIDO) == ESPERADO
    sem_consulta_receita.assert_called_once_with("https://receitaws.com.br/v1/cnpj/11222333000181")


@pytest.mark.parametrize("receitaws", [None, _resposta_api(status=429), _resposta_api(json={})])
def test_A_receitaws_falha_usa_a_brasilapi(sem_consulta_receita, receitaws):
    sem_consulta_receita.side_effect = _por_fonte(receitaws, _resposta_api(json=EMPRESA_ATIVA))
    assert receita.consultar_cnpj(CNPJ_VALIDO) == ESPERADO


@pytest.mark.parametrize("receitaws, brasilapi", [
    (_resposta_api(json={"status": "ERROR", "message": "CNPJ rejeitado pela Receita Federal"}), None),
    (None, _resposta_api(status=404)),
])
def test_B_cnpj_desconhecido_na_receita(sem_consulta_receita, receitaws, brasilapi):
    sem_consulta_receita.side_effect = _por_fonte(receitaws, brasilapi)
    assert receita.consultar_cnpj(CNPJ_VALIDO) == {"situacao": receita.NAO_ENCONTRADO}


@pytest.mark.parametrize("resposta", [None, _resposta_api(status=429), _resposta_api(json={})])
def test_B_as_duas_fontes_falham_devolve_none(sem_consulta_receita, resposta):
    sem_consulta_receita.return_value = resposta
    assert receita.consultar_cnpj(CNPJ_VALIDO) is None


# ── Conversa ───────────────────────────────────────────────────

def test_A_cnpj_preenche_razao_social_e_pula_a_pergunta(manager, sessao, sem_consulta_receita):
    sem_consulta_receita.return_value = _resposta_api(json=EMPRESA_ATIVA)
    sessao["get_session"].return_value = _make_session("AGUARDA_cnpj")
    resp = manager.process(PHONE, CNPJ_VALIDO)
    assert "*EMPRESA TESTE LTDA* (Belo Horizonte/MG)" in resp
    assert CONTATO["pergunta"] in resp and RAZAO["pergunta"] not in resp
    estado, dados = sessao["update_session"].call_args[0][1:3]
    assert estado == "AGUARDA_contato"
    assert dados["razao_social"] == "EMPRESA TESTE LTDA"
    assert dados[receita.CAMPO_SITUACAO] == "ATIVA"
    assert dados["_auto"] == ["razao_social"]


def test_B_consulta_falha_pergunta_a_razao_social(manager, sessao):
    sessao["get_session"].return_value = _make_session("AGUARDA_cnpj")
    resp = manager.process(PHONE, CNPJ_VALIDO)
    assert resp == RAZAO["pergunta"]
    estado, dados = sessao["update_session"].call_args[0][1:3]
    assert estado == "AGUARDA_razao_social" and "razao_social" not in dados


def test_B_cnpj_baixado_e_aceito_e_marcado(manager, sessao, sem_consulta_receita):
    sem_consulta_receita.return_value = _resposta_api(
        json={**EMPRESA_ATIVA, "descricao_situacao_cadastral": "BAIXADA"})
    sessao["get_session"].return_value = _make_session("AGUARDA_cnpj")
    manager.process(PHONE, CNPJ_VALIDO)
    estado, dados = sessao["update_session"].call_args[0][1:3]
    assert estado == "AGUARDA_contato" and dados[receita.CAMPO_SITUACAO] == "BAIXADA"


def test_A_voltar_do_contato_pula_a_razao_preenchida(manager, sessao):
    sessao["get_session"].return_value = _make_session("AGUARDA_contato", {
        "cnpj": CNPJ_VALIDO, "razao_social": "EMPRESA TESTE LTDA",
        receita.CAMPO_SITUACAO: "ATIVA", "_auto": ["razao_social"]})
    resp = manager.process(PHONE, "VOLTAR")
    assert CNPJ_P["pergunta"] in resp
    estado, dados = sessao["update_session"].call_args[0][1:3]
    assert estado == "AGUARDA_cnpj" and dados == {}


def test_A_alterar_cnpj_troca_a_razao_preenchida(manager, sessao, sem_consulta_receita):
    sem_consulta_receita.return_value = _resposta_api(json={**EMPRESA_ATIVA, "razao_social": "OUTRA SA"})
    sessao["get_session"].return_value = _make_session("ALTERA_cnpj", {
        "cnpj": CNPJ_VALIDO, "razao_social": "EMPRESA TESTE LTDA", "_auto": ["razao_social"],
        "contato": "c@e.com", "servico": "Gás", "estados": "MG"})
    resp = manager.process(PHONE, CNPJ_VALIDO)
    assert "Resumo do cadastro" in resp and "OUTRA SA" in resp and "Pronto, atualizado." in resp


def test_A_razao_digitada_nao_e_sobrescrita(manager, sessao, sem_consulta_receita):
    """Na ordem antiga (Razão Social antes), o nome digitado pelo fornecedor fica."""
    sessao["get_perguntas"].return_value = SAMPLE_PERGUNTAS
    sem_consulta_receita.return_value = _resposta_api(json=EMPRESA_ATIVA)
    sessao["get_session"].return_value = _make_session("AGUARDA_cnpj", {"razao_social": "Minha Empresa"})
    resp = manager.process(PHONE, CNPJ_VALIDO)
    dados = sessao["update_session"].call_args[0][2]
    assert dados["razao_social"] == "Minha Empresa" and "Encontrei" not in resp


def test_A_controle_interno_nao_vai_para_o_cadastro(manager, sessao):
    dados = {"cnpj": CNPJ_VALIDO, "razao_social": "EMPRESA TESTE LTDA", "_auto": ["razao_social"],
             receita.CAMPO_SITUACAO: "ATIVA", "contato": "c@e.com", "servico": "Gás", "estados": "MG"}
    sessao["get_session"].return_value = _make_session("CONFIRMACAO", dados)
    manager.process(PHONE, "S")
    salvo = sessao["save_cadastro"].call_args[0][1]
    assert "_auto" not in salvo and salvo[receita.CAMPO_SITUACAO] == "ATIVA"
