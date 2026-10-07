"""
Testes A/B — excel_writer.py (planilha gerada a partir dos cadastros do Supabase)
A = comportamento esperado
B = edge cases (formulário alterado, dados faltando, datas)
"""
import io

import openpyxl

from excel_writer import gerar_excel
from tests.conftest import SAMPLE_PERGUNTAS, PHONE

DADOS_BASE = {
    "razao_social": "EMPRESA TESTE LTDA",
    "cnpj": "11.222.333/0001-81",
    "contato": "(31) 99999-0000",
    "servico": "Consultoria Em Ti",
    "estados": "MG, SP",
}

CABECALHO_ESPERADO = (
    "Telefone", "Razão Social", "CNPJ", "Contato", "Serviço", "Estados", "Data Cadastro (Brasília)"
)


def _cadastro(dados=None, criado_em="2026-10-07T15:00:00+00:00", phone=PHONE):
    return {"phone": phone, "dados": dados if dados is not None else dict(DADOS_BASE), "criado_em": criado_em}


def _ler(conteudo: bytes):
    wb = openpyxl.load_workbook(io.BytesIO(conteudo))
    return [row for row in wb.active.iter_rows(values_only=True)]


class TestGerarExcel:

    # ── A — COMPORTAMENTO ESPERADO ─────────────────────────────

    def test_A_cabecalho_segue_perguntas(self):
        rows = _ler(gerar_excel([_cadastro()], SAMPLE_PERGUNTAS))
        assert rows[0] == CABECALHO_ESPERADO

    def test_A_linha_com_dados(self):
        rows = _ler(gerar_excel([_cadastro()], SAMPLE_PERGUNTAS))
        assert rows[1][:6] == (PHONE, "EMPRESA TESTE LTDA", "11.222.333/0001-81",
                               "(31) 99999-0000", "Consultoria Em Ti", "MG, SP")

    def test_A_data_convertida_para_brasilia(self):
        rows = _ler(gerar_excel([_cadastro(criado_em="2026-10-07T15:00:00+00:00")], SAMPLE_PERGUNTAS))
        assert rows[1][6] == "2026-10-07 12:00:00"

    def test_A_ordenado_por_data_de_cadastro(self):
        cadastros = [
            _cadastro({**DADOS_BASE, "razao_social": "SEGUNDA"}, criado_em="2026-10-07T16:00:00+00:00"),
            _cadastro({**DADOS_BASE, "razao_social": "PRIMEIRA"}, criado_em="2026-10-07T15:00:00+00:00"),
        ]
        rows = _ler(gerar_excel(cadastros, SAMPLE_PERGUNTAS))
        assert [r[1] for r in rows[1:]] == ["PRIMEIRA", "SEGUNDA"]

    def test_A_ordem_das_colunas_segue_campo_ordem(self):
        invertidas = list(reversed(SAMPLE_PERGUNTAS))
        rows = _ler(gerar_excel([_cadastro()], invertidas))
        assert rows[0] == CABECALHO_ESPERADO

    # ── B — FORMULÁRIO ALTERADO / EDGE CASES ───────────────────

    def test_B_pergunta_nova_nao_desalinha_cadastros_antigos(self):
        perguntas = SAMPLE_PERGUNTAS + [{
            "id": 6, "ordem": 6, "campo": "site", "label": "Site",
            "pergunta": "Site?", "tipo": "texto", "msg_erro": None, "ativo": True,
        }]
        cadastros = [_cadastro(), _cadastro({**DADOS_BASE, "site": "empresa.com"})]
        rows = _ler(gerar_excel(cadastros, perguntas))
        assert rows[0][6] == "Site"
        assert rows[1][6] in ("", None)
        assert rows[2][6] == "empresa.com"
        assert rows[1][1] == rows[2][1] == "EMPRESA TESTE LTDA"

    def test_B_campo_removido_das_perguntas_continua_na_planilha(self):
        perguntas = [p for p in SAMPLE_PERGUNTAS if p["campo"] != "servico"]
        rows = _ler(gerar_excel([_cadastro()], perguntas))
        assert "servico" in rows[0]
        assert "Consultoria Em Ti" in rows[1]

    def test_B_pergunta_inativa_com_dados_mantem_label(self):
        perguntas = [dict(p, ativo=False) if p["campo"] == "servico" else p for p in SAMPLE_PERGUNTAS]
        rows = _ler(gerar_excel([_cadastro()], perguntas))
        assert "Serviço" in rows[0]

    def test_B_pergunta_inativa_sem_dados_omitida(self):
        perguntas = SAMPLE_PERGUNTAS + [{
            "id": 7, "ordem": 7, "campo": "antiga", "label": "Antiga",
            "pergunta": "?", "tipo": "texto", "msg_erro": None, "ativo": False,
        }]
        rows = _ler(gerar_excel([_cadastro()], perguntas))
        assert "Antiga" not in rows[0]

    def test_B_campos_faltando_nao_quebra(self):
        rows = _ler(gerar_excel([_cadastro({})], SAMPLE_PERGUNTAS))
        assert len(rows) == 2

    def test_B_data_ausente_ou_invalida(self):
        rows = _ler(gerar_excel([_cadastro(criado_em=None), _cadastro(criado_em="ontem")], SAMPLE_PERGUNTAS))
        assert {rows[1][6], rows[2][6]} <= {None, "", "ontem"}
