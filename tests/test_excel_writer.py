"""
Testes A/B — excel_writer.py (colunas dinâmicas via perguntas)
A = comportamento esperado
B = edge cases (múltiplos appends, concorrência)
"""
import os
import threading
import pytest
import openpyxl

from excel_writer import append_fornecedor
from tests.conftest import SAMPLE_PERGUNTAS, PHONE

DADOS_BASE = {
    "razao_social": "EMPRESA TESTE LTDA",
    "cnpj": "11.222.333/0001-81",
    "contato": "(31) 99999-0000",
    "servico": "Consultoria Em Ti",
    "estados": "MG, SP",
}

CABECALHO_ESPERADO = (
    "Telefone", "Razão Social", "CNPJ", "Contato", "Serviço", "Estados", "Data Cadastro"
)


def _ler_planilha(path: str):
    wb = openpyxl.load_workbook(path)
    return [row for row in wb.active.iter_rows(values_only=True)]


class TestExcelWriter:

    # ── A — COMPORTAMENTO ESPERADO ─────────────────────────────

    def test_A_cria_arquivo_com_cabecalho(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(PHONE, DADOS_BASE, SAMPLE_PERGUNTAS)
        rows = _ler_planilha(path)
        assert rows[0] == CABECALHO_ESPERADO

    def test_A_primeira_linha_com_telefone(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(PHONE, DADOS_BASE, SAMPLE_PERGUNTAS)
        rows = _ler_planilha(path)
        assert rows[1][0] == PHONE
        assert rows[1][1] == "EMPRESA TESTE LTDA"
        assert rows[1][2] == "11.222.333/0001-81"
        assert rows[1][3] == "(31) 99999-0000"
        assert rows[1][4] == "Consultoria Em Ti"
        assert rows[1][5] == "MG, SP"

    def test_A_data_cadastro_preenchida(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(PHONE, DADOS_BASE, SAMPLE_PERGUNTAS)
        rows = _ler_planilha(path)
        assert rows[1][6] is not None

    def test_A_multiplos_sem_duplicar_cabecalho(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(PHONE, DADOS_BASE, SAMPLE_PERGUNTAS)
        append_fornecedor(PHONE, {**DADOS_BASE, "razao_social": "SEGUNDA EMPRESA"}, SAMPLE_PERGUNTAS)
        rows = _ler_planilha(path)
        assert len(rows) == 3
        assert rows[0] == CABECALHO_ESPERADO
        assert rows[1][1] == "EMPRESA TESTE LTDA"
        assert rows[2][1] == "SEGUNDA EMPRESA"

    # ── B — EDGE CASES ─────────────────────────────────────────

    def test_B_campos_faltando_nao_quebra(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(PHONE, {}, SAMPLE_PERGUNTAS)
        rows = _ler_planilha(path)
        assert len(rows) == 2

    def test_B_arquivo_existente_preservado(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(PHONE, DADOS_BASE, SAMPLE_PERGUNTAS)
        append_fornecedor(PHONE, {**DADOS_BASE, "razao_social": "SEGUNDA"}, SAMPLE_PERGUNTAS)
        rows = _ler_planilha(path)
        assert rows[1][1] == "EMPRESA TESTE LTDA"

    def test_B_concorrencia_thread_safe(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        errors = []

        def worker(n):
            try:
                append_fornecedor(PHONE, {**DADOS_BASE, "razao_social": f"EMPRESA {n}"}, SAMPLE_PERGUNTAS)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        rows = _ler_planilha(path)
        assert len(rows) == 11
