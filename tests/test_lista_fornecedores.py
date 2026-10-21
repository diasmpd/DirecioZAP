"""
Testes A/B — inclusão no LISTA_FORNECEDORES.xlsm (lista_fornecedores.py), sem Excel: a
planilha é falsa
A = entra sozinho / dado no formato da lista
B = fica para revisão, já está na lista ou a planilha está em uso
"""
import pytest

import lista_fornecedores as lf
import opcoes

PHONE = "5515997263903"
DADOS_OK = {
    "cnpj": "03.098.277/0001-58",
    "razao_social": "Geraltest Controle Tecnologico Ltda",
    "contato": "(15) 99726-3903",
    "servico": "Ensaios de Fundação; Consultoria de Fundação; Controle Tecnológico Concreto",
    "estados": "MG, SP, DF/GO",
    "situacao_cnpj": "ATIVA",
    "uf_receita": "SP",
    "cidade_receita": "Sorocaba",
    "email_portal": "comercial@geraltest.com.br",
}

# Nomes como estão na aba Legenda (com espaço sobrando e o erro de digitação "Subsestação").
LEGENDA_PLANILHA = [
    ("5.1", "Controle Tecnológico Concreto"),
    ("7.3", "Consultoria de Fundação"),
    ("7.4", "Ensaios de Fundação"),
    ("10.4", "Subsestação Definitiva / Entrada de Energia Definitiva"),
    ("10.10", "Reservatório - Instalações Hidráulicas"),
    ("13.1", "Assentamento Cerâmico "),
]
LEGENDA = {lf._base(nome): cod for cod, nome in LEGENDA_PLANILHA}


def _cadastro(id_="c1", phone=PHONE, **extra):
    return {"id": id_, "phone": phone, "dados": {**DADOS_OK, **extra},
            "criado_em": "2026-10-22T01:30:00+00:00"}


class FakeDB:
    def __init__(self, pendentes):
        self.pendentes = pendentes
        self.marcados = {}

    def preparar_lista(self):
        pass

    def get_cadastros_lista_pendentes(self, espera_min=60):
        return [c for c in self.pendentes if c["id"] not in self.marcados]

    def marcar_lista(self, id_, status, detalhe, envio):
        self.marcados[id_] = (status, detalhe, envio)


class FakePlanilha:
    """Tabela em memória: {linha: (cnpj, prospectado)}; registra inserções e salvamentos."""
    ocupada = False

    def __init__(self, linhas=None):
        self.linhas = dict(linhas or {})
        self.inseridas = []
        self.salvou = False

    def __call__(self, caminho):
        return self

    def __enter__(self):
        if self.ocupada:
            raise lf.PlanilhaOcupada("aberta por alguém")
        return self

    def __exit__(self, *_):
        pass

    def legenda(self):
        return dict(LEGENDA)

    def linhas_por_cnpj(self):
        indice = {}
        for n, (cnpj, prosp) in self.linhas.items():
            indice.setdefault(lf.digitos(cnpj).zfill(14), []).append((n, prosp))
        return indice

    def inserir(self, linha):
        n = max(self.linhas or {1: None}) + 1
        self.linhas[n] = (linha[lf.COL_CNPJ], linha[lf.COL_PROSPECTADO])
        self.inseridas.append(linha)
        return n

    def salvar(self):
        self.salvou = True
        return "backup"


# ── Montagem da linha ─────────────────────────────────────────

def test_A_linha_no_formato_da_lista():
    linha, motivos = lf.montar_linha(PHONE, DADOS_OK, "2026-10-22T01:30:00+00:00", LEGENDA)
    assert motivos == []
    assert linha == {
        "Qualificado": "Qualificado",
        "Avaliação Interna": 1,
        "Data de cadastro": "2026-10-21",  # 01:30 UTC = 22:30 do dia 21 em Brasília
        "UF (Corrigido)": "SP",
        "Local De Atuação": "MG, SP, DF, GO",
        "Empresa - Razão Social (Corrigido)": "GERALTEST CONTROLE TECNOLOGICO LTDA",
        "Cpf/Cnpj (Corrigido)": "03098277000158",  # só dígitos, com o zero: Tipo calcula "CNPJ"
        "Cnpj Correto?": "Correto",
        "Legenda": "5.1|7.3|7.4",  # na ordem da Legenda, não na do cadastro
        "Celular Final": "(15) 99726-3903",
        "Fixo": "",
        "Email": "comercial@geraltest.com.br",
        "Fornecedor prospectado": "Sim",
    }
    assert set(linha) <= set(lf.COLUNAS) - {"Tipo"}


def test_A_telefones_whatsapp_contato_e_fixo():
    assert lf._telefones("5531999990000", "(31) 98888-7777") == ("(31) 99999-0000|(31) 98888-7777", "")
    assert lf._telefones("5531999990000", "(31) 3333-4444") == ("(31) 99999-0000", "(31) 3333-4444")
    assert lf._telefones("5531999990000", "compras@x.com.br") == ("(31) 99999-0000", "")


def test_A_email_do_contato_quando_nao_deu_o_do_portal():
    dados = {**DADOS_OK, "contato": "obras@empresa.com.br"}
    del dados["email_portal"]
    linha, _ = lf.montar_linha(PHONE, dados, "", LEGENDA)
    assert linha["Email"] == "obras@empresa.com.br"


def test_A_nomes_da_legenda_com_espaco_e_erro_de_digitacao():
    dados = {**DADOS_OK, "servico": "Assentamento Cerâmico; Subestação Definitiva / Entrada de Energia Definitiva"}
    assert lf.codigos_legenda(dados, LEGENDA) == (["10.4", "13.1"], [])


def test_A_codigo_10_10_continua_texto():
    dados = {**DADOS_OK, "servico": "Reservatório - Instalações Hidráulicas"}
    linha, _ = lf.montar_linha(PHONE, dados, "", LEGENDA)
    assert linha["Legenda"] == "10.10"
    assert "Legenda" in lf.COLUNAS_TEXTO and lf.COL_CNPJ in lf.COLUNAS_TEXTO


def test_A_apelidos_so_para_servicos_do_bot():
    bases = {lf._base(s) for s in opcoes.SERVICOS}
    assert set(lf._APELIDOS) <= bases


@pytest.mark.parametrize("extra, motivo", [
    ({"servico": "Gás"}, "Serviço sem código na Legenda: Gás"),
    ({"situacao_cnpj": "BAIXADA"}, "CNPJ com situação BAIXADA na Receita"),
    ({"situacao_cnpj": None}, "CNPJ não consultado na Receita"),
    ({"uf_receita": ""}, "Sem UF da sede (Receita)"),
    ({"cnpj": "12.ABC.345/01DE-35"}, "CNPJ fora do formato da lista"),
])
def test_B_motivos_de_revisao(extra, motivo):
    _, motivos = lf.montar_linha(PHONE, {**DADOS_OK, **extra}, "", LEGENDA)
    assert any(m.startswith(motivo) for m in motivos)


def test_B_cnpj_correto_quando_nao_ativo():
    assert lf._cnpj_correto("ATIVA") == "Correto"
    assert lf._cnpj_correto("BAIXADA") == "N/A"
    assert lf._cnpj_correto(None) == "Erro na consulta"


# ── Processamento ─────────────────────────────────────────────

def test_A_auto_insere_salva_e_marca():
    db, pl = FakeDB([_cadastro()]), FakePlanilha({16722: ("1", "Não")})
    res = lf.processar_pendentes(db, "auto", planilha=pl)
    assert [r["status"] for r in res] == [lf.INSERIDO]
    assert pl.salvou and len(pl.inseridas) == 1
    status, detalhe, envio = db.marcados["c1"]
    assert (status, detalhe) == (lf.INSERIDO, "Linha 16723")
    assert envio["_linha"] == 16723 and envio["Legenda"] == "5.1|7.3|7.4"


def test_A_cnpj_na_lista_so_como_nao_entra_com_sim():
    pl = FakePlanilha({500: ("03098277000158", "Não")})
    db = FakeDB([_cadastro()])
    lf.processar_pendentes(db, "auto", planilha=pl)
    assert db.marcados["c1"][0] == lf.INSERIDO
    assert pl.linhas[500] == ("03098277000158", "Não")  # linha existente intacta


def test_B_cnpj_ja_prospectado_nao_grava():
    pl = FakePlanilha({500: ("03.098.277/0001-58", "Sim")})
    db = FakeDB([_cadastro()])
    res = lf.processar_pendentes(db, "auto", planilha=pl)
    assert res[0]["status"] == lf.JA_PROSPECTADO
    assert db.marcados["c1"][:2] == (lf.JA_PROSPECTADO, "CNPJ já na lista como prospectado (linha 500)")
    assert not pl.inseridas and not pl.salvou


def test_B_mesmo_cnpj_duas_vezes_no_lote_entra_uma():
    db, pl = FakeDB([_cadastro("c1"), _cadastro("c2")]), FakePlanilha()
    lf.processar_pendentes(db, "auto", planilha=pl)
    assert db.marcados["c1"][0] == lf.INSERIDO
    assert db.marcados["c2"][0] == lf.JA_PROSPECTADO
    assert len(pl.inseridas) == 1


def test_B_revisar_guarda_a_linha_e_nao_salva():
    db, pl = FakeDB([_cadastro(servico="Gás")]), FakePlanilha()
    lf.processar_pendentes(db, "auto", planilha=pl)
    status, detalhe, envio = db.marcados["c1"]
    assert status == lf.REVISAR and "Gás" in detalhe
    assert envio["Empresa - Razão Social (Corrigido)"] == "GERALTEST CONTROLE TECNOLOGICO LTDA"
    assert not pl.salvou


def test_B_modo_revisar_segura_ate_os_completos():
    db, pl = FakeDB([_cadastro()]), FakePlanilha()
    lf.processar_pendentes(db, "revisar", planilha=pl)
    assert db.marcados["c1"][0] == lf.REVISAR and not pl.inseridas


def test_B_desligado_nao_faz_nada():
    db = FakeDB([_cadastro()])
    assert lf.processar_pendentes(db, "", planilha=FakePlanilha()) == []
    assert db.marcados == {}


def test_B_planilha_em_uso_nao_marca_nada():
    pl = FakePlanilha()
    pl.ocupada = True
    db = FakeDB([_cadastro()])
    assert lf.processar_pendentes(db, "auto", planilha=pl) == []
    assert db.marcados == {}


def test_B_erro_ao_salvar_nao_marca_nada():
    pl = FakePlanilha()
    pl.salvar = lambda: (_ for _ in ()).throw(OSError("rede caiu"))
    db = FakeDB([_cadastro()])
    with pytest.raises(OSError):
        lf.processar_pendentes(db, "auto", planilha=pl)
    assert db.marcados == {}


# ── Aprovação no Manager ──────────────────────────────────────

def test_A_aprovado_com_codigos_escolhidos():
    db, pl = FakeDB([]), FakePlanilha()
    status, _ = lf.inserir_aprovado(db, _cadastro(servico="Gás", uf_receita=""), ["13.1"], planilha=pl)
    assert status == lf.INSERIDO and pl.salvou
    assert pl.inseridas[0]["Legenda"] == "13.1"


def test_B_aprovado_com_codigo_inexistente_nao_grava():
    db, pl = FakeDB([]), FakePlanilha()
    with pytest.raises(ValueError, match="99.9"):
        lf.inserir_aprovado(db, _cadastro(), ["13.1", "99.9"], planilha=pl)
    assert not pl.inseridas and db.marcados == {}


def test_B_aprovado_mas_ja_prospectado():
    db, pl = FakeDB([]), FakePlanilha({7: ("03098277000158", "Sim")})
    status, _ = lf.inserir_aprovado(db, _cadastro(), ["13.1"], planilha=pl)
    assert status == lf.JA_PROSPECTADO and not pl.inseridas
