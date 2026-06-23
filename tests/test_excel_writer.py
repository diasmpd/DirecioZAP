"""
Testes A/B — excel_writer.py
A = comportamento esperado (arquivo criado/atualizado corretamente)
B = edge cases (múltiplos appends, concorrência)
"""
import os
import threading
import pytest
import openpyxl

from excel_writer import append_fornecedor, CABECALHO

DADOS_BASE = {
    "razao_social": "EMPRESA TESTE LTDA",
    "cnpj": "11.222.333/0001-81",
    "contato": "(31) 99999-0000",
    "servico": "Consultoria Em Ti",
    "estados": "MG, SP",
}


def _ler_planilha(path: str):
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    return [row for row in ws.iter_rows(values_only=True)]


# ─────────────────────────────────────────────────────────────
#  A — COMPORTAMENTO ESPERADO
# ─────────────────────────────────────────────────────────────

class TestExcelWriter:
    def test_A_cria_arquivo_com_cabecalho(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(DADOS_BASE)
        assert os.path.exists(path)
        rows = _ler_planilha(path)
        assert list(rows[0]) == CABECALHO

    def test_A_primeira_linha_de_dados(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(DADOS_BASE)
        rows = _ler_planilha(path)
        assert rows[1][0] == "EMPRESA TESTE LTDA"
        assert rows[1][1] == "11.222.333/0001-81"
        assert rows[1][2] == "(31) 99999-0000"
        assert rows[1][3] == "Consultoria Em Ti"
        assert rows[1][4] == "MG, SP"

    def test_A_data_cadastro_preenchida(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(DADOS_BASE)
        rows = _ler_planilha(path)
        assert rows[1][5] is not None
        assert len(str(rows[1][5])) > 0

    def test_A_multiplos_cadastros_sem_duplicar_cabecalho(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor(DADOS_BASE)
        append_fornecedor({**DADOS_BASE, "razao_social": "SEGUNDA EMPRESA"})
        rows = _ler_planilha(path)
        # 1 cabeçalho + 2 dados = 3 linhas
        assert len(rows) == 3
        assert rows[0] == tuple(CABECALHO)
        assert rows[1][0] == "EMPRESA TESTE LTDA"
        assert rows[2][0] == "SEGUNDA EMPRESA"

    # ─────────────────────────────────────────────────────────────
    #  B — EDGE CASES
    # ─────────────────────────────────────────────────────────────

    def test_B_campos_faltando_nao_quebra(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)
        append_fornecedor({})  # todos os campos ausentes
        rows = _ler_planilha(path)
        assert len(rows) == 2  # cabeçalho + linha vazia

    def test_B_arquivo_existente_preservado(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)

        # Cria arquivo com 1 entrada
        append_fornecedor(DADOS_BASE)

        # Reinicia o módulo e adiciona outra entrada
        append_fornecedor({**DADOS_BASE, "razao_social": "SEGUNDA EMPRESA"})
        rows = _ler_planilha(path)
        assert rows[1][0] == "EMPRESA TESTE LTDA"

    def test_B_concorrencia_thread_safe(self, tmp_path, monkeypatch):
        path = str(tmp_path / "test.xlsx")
        monkeypatch.setattr("excel_writer.settings.EXCEL_PATH", path)

        errors = []

        def worker(n):
            try:
                append_fornecedor({**DADOS_BASE, "razao_social": f"EMPRESA {n}"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Erros em threads: {errors}"
        rows = _ler_planilha(path)
        # 1 cabeçalho + 10 dados
        assert len(rows) == 11
