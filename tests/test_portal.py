"""
Testes A/B — envio ao Portal do Fornecedor (portal.py), sem rede: o cliente HTTP é falso
A = vai sozinho / dado no formato do Portal
B = fica para revisão, já está no Portal ou o Portal recusa
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import portal
from opcoes import SERVICOS

PHONE = "5519999990000"
DADOS_OK = {
    "cnpj": "54.817.683/0001-01",
    "razao_social": "EMPRESA TESTE LTDA",
    "servico": "Alvenaria / Muro de Divisa",
    "estados": "SP",
    "situacao_cnpj": "ATIVA",
    "uf_receita": "SP",
    "cidade_receita": "Hortolandia",
    "email_portal": "compras@teste.com.br",
}


@pytest.fixture(scope="module")
def mapa():
    return portal.carregar_mapa()


def _cadastro(**extra):
    return {"id": "c1", "phone": PHONE, "dados": {**DADOS_OK, **extra}, "criado_em": "2026-10-16T13:02:00+00:00"}


class FakeDB:
    def __init__(self, pendentes):
        self.pendentes = pendentes
        self.marcados = {}

    def get_cadastros_portal_pendentes(self):
        return [c for c in self.pendentes if c["id"] not in self.marcados]

    def marcar_portal(self, id_, status, detalhe, envio):
        self.marcados[id_] = (status, detalhe, envio)


def _cliente(novo=True, enviar=None):
    c = MagicMock()
    c.validar.return_value = (novo, 0, "CPF ou CNPJ validado!" if novo else "Já existe um fornecedor cadastrado")
    c.enviar.side_effect = enviar or (lambda campos, tipo: "Cadastro realizado")
    return c


# ── Mapa ──────────────────────────────────────────────────────

def test_A_mapa_cobre_todos_os_servicos_do_bot(mapa):
    assert set(mapa) == {portal._base(s) for s in SERVICOS}


def test_A_mapa_so_usa_codigos_que_existem_no_portal(mapa):
    caminho = Path(portal.__file__).parent / "data" / "portal_categorias.json"
    codigos = {c["cod"] for c in json.load(open(caminho, encoding="utf-8"))}
    usados = {c for item in mapa.values() for c in item["codigos"]}
    assert usados <= codigos
    assert all(item["segmento"] in ("1", "2", "3") for item in mapa.values())


# ── Formatos ──────────────────────────────────────────────────

def test_A_formatos_do_portal():
    assert portal.formatar_cnpj("54817683000101") == "54.817.683/0001-01"
    assert portal.formatar_telefone("5531999990000") == "(31) 99999-0000"
    assert portal.formatar_telefone("553133330000") == "(31) 3333-0000"


def test_B_cnpj_alfanumerico_nao_vai_para_o_portal():
    assert portal.formatar_cnpj("12.ABC.345/01DE-35") is None


# ── Montagem ──────────────────────────────────────────────────

def test_A_cadastro_completo_vai_sozinho(mapa):
    campos, motivos = portal.montar_envio(PHONE, DADOS_OK, "2026-10-16T13:02", mapa)
    assert motivos == []
    assert campos["CodigosCategoria"] == ["212"] and campos["CodigosSegmento"] == ["1"]
    assert campos["Identificador"] == "54.817.683/0001-01"
    assert campos["Telefone"] == "(19) 99999-0000"
    assert campos["CodigosSoubeSisfor"] == "6" and campos["Outro"] == "WhatsApp DirecioZAP"
    assert "2026-10-16" in campos["Mensagem"] and "Alvenaria" in campos["Mensagem"]
    assert portal.problemas_para_envio(campos) == []


def test_A_servico_em_minusculas_de_cadastro_antigo_casa_com_o_mapa(mapa):
    _, motivos = portal.montar_envio(PHONE, {**DADOS_OK, "servico": "assentamento cerâmico"}, "", mapa)
    assert motivos == []


def test_A_locacao_e_servico_somam_segmentos_sem_repetir(mapa):
    campos, _ = portal.montar_envio(PHONE, {**DADOS_OK, "servico": "Grua; Elevador Cremalheira; Gesso Liso"}, "", mapa)
    assert campos["CodigosSegmento"] == ["2", "1"]
    assert campos["CodigosCategoria"] == ["232", "217"]


@pytest.mark.parametrize("extra, trecho", [
    ({"servico": "SLQA"}, "sem categoria"),
    ({"servico": "Instalação Elétrica Interna"}, "confiança baixa"),
    ({"uf_receita": ""}, "UF/cidade"),
    ({"situacao_cnpj": "BAIXADA"}, "BAIXADA"),
    ({"email_portal": ""}, "e-mail"),
])
def test_B_motivos_de_revisao(mapa, extra, trecho):
    _, motivos = portal.montar_envio(PHONE, {**DADOS_OK, **extra}, "", mapa)
    assert any(trecho in m for m in motivos), motivos


def test_B_mais_de_5_categorias_fica_para_revisao(mapa):
    servicos = "; ".join(["Grua", "Munck", "Guindaste", "Gesso Liso", "Gás", "Paisagismo"])
    campos, motivos = portal.montar_envio(PHONE, {**DADOS_OK, "servico": servicos}, "", mapa)
    assert len(campos["CodigosCategoria"]) == 6
    assert any("até 5" in m for m in motivos)
    assert portal.problemas_para_envio(campos)


# ── Processamento ─────────────────────────────────────────────

def test_A_auto_envia_e_guarda_o_que_foi_enviado(mapa):
    db, cli = FakeDB([_cadastro()]), _cliente()
    res = portal.processar_pendentes(db, "auto", cli, mapa)
    assert [r["status"] for r in res] == ["enviado"]
    status, detalhe, envio = db.marcados["c1"]
    assert status == "enviado" and detalhe == "Cadastro realizado"
    assert envio["CodigosCategoria"] == ["212"]
    cli.validar.assert_called_once_with("54.817.683/0001-01")


def test_B_ja_cadastrado_nao_envia(mapa):
    db, cli = FakeDB([_cadastro()]), _cliente(novo=False)
    portal.processar_pendentes(db, "auto", cli, mapa)
    assert db.marcados["c1"][0] == "ja_cadastrado"
    cli.enviar.assert_not_called()


def test_B_revisao_nao_envia_mas_confere_se_ja_existe(mapa):
    db, cli = FakeDB([_cadastro(servico="SLQA")]), _cliente()
    portal.processar_pendentes(db, "auto", cli, mapa)
    assert db.marcados["c1"][0] == "revisar"
    cli.validar.assert_called_once()
    cli.enviar.assert_not_called()


def test_B_modo_revisar_segura_ate_o_cadastro_perfeito(mapa):
    db, cli = FakeDB([_cadastro()]), _cliente()
    portal.processar_pendentes(db, "revisar", cli, mapa)
    assert db.marcados["c1"][0] == "revisar"
    cli.enviar.assert_not_called()


@pytest.mark.parametrize("modo", ["", None, "desligado"])
def test_B_desligado_nao_toca_em_nada(mapa, modo):
    db, cli = FakeDB([_cadastro()]), _cliente()
    assert portal.processar_pendentes(db, modo, cli, mapa) == []
    assert db.marcados == {}
    cli.validar.assert_not_called()


def test_B_portal_recusa_grava_erro(mapa):
    def recusa(campos, tipo):
        raise portal.PortalErro("HTTP 400: E-mail já utilizado")
    db = FakeDB([_cadastro()])
    portal.processar_pendentes(db, "auto", _cliente(enviar=recusa), mapa)
    status, detalhe, envio = db.marcados["c1"]
    assert status == "erro" and "E-mail já utilizado" in detalhe and envio


def test_B_portal_fora_do_ar_na_conferencia_nao_grava_nada(mapa):
    db, cli = FakeDB([_cadastro()]), _cliente()
    cli.validar.side_effect = ConnectionError("sem rede")
    with pytest.raises(ConnectionError):
        portal.processar_pendentes(db, "auto", cli, mapa)
    assert db.marcados == {}  # tenta de novo na próxima execução


# ── Cliente HTTP (sessão falsa) ───────────────────────────────

def _resp(status=200, json_=None, text=""):
    r = MagicMock()
    r.status_code, r.ok, r.text, r.url = status, 200 <= status < 300, text, "https://x/Fornecedor/Cadastrar"
    r.raise_for_status.side_effect = None if r.ok else RuntimeError(status)
    if json_ is None:
        r.json.side_effect = ValueError
    else:
        r.json.return_value = json_
    return r


def test_A_cliente_envia_multipart_com_token_e_listas(mapa):
    http = MagicMock()
    http.headers = {}
    http.get.return_value = _resp(text='<input name="__RequestVerificationToken" type="hidden" value="TOK" />')
    http.post.return_value = _resp(json_="Fornecedor cadastrado com sucesso!")
    campos, _ = portal.montar_envio(PHONE, {**DADOS_OK, "servico": "Grua; Gesso Liso"}, "", mapa)
    assert portal.PortalCliente(session=http).enviar(campos) == "Fornecedor cadastrado com sucesso!"
    partes = http.post.call_args.kwargs["files"]
    assert ("__RequestVerificationToken", (None, "TOK")) in partes
    assert [v for n, (_, v) in partes if n == "CodigosCategoria"] == ["232", "217"]
    assert http.get.call_args.kwargs["params"]["identificador"] == "54.817.683/0001-01"


def test_B_cliente_sem_token_levanta_erro(mapa):
    http = MagicMock()
    http.headers = {}
    http.get.return_value = _resp(text="<html>manutenção</html>")
    campos, _ = portal.montar_envio(PHONE, DADOS_OK, "", mapa)
    with pytest.raises(portal.PortalErro):
        portal.PortalCliente(session=http).enviar(campos)
    http.post.assert_not_called()
