"""
Testes A/B — validators.py
A = caminho válido (normaliza corretamente)
B = caminho inválido (retorna None / rejeita)
"""
import pytest
from validators import (
    normalizar_cnpj,
    normalizar_contato,
    normalizar_estados,
    normalizar_razao_social,
    normalizar_servico,
)

# ─────────────────────────────────────────────────────────────
#  RAZÃO SOCIAL
# ─────────────────────────────────────────────────────────────

class TestRazaoSocial:
    # A — inputs válidos
    def test_A_texto_simples(self):
        assert normalizar_razao_social("empresa exemplo ltda") == "EMPRESA EXEMPLO LTDA"

    def test_A_com_espacos_extras(self):
        assert normalizar_razao_social("  empresa   exemplo  ") == "EMPRESA EXEMPLO"

    def test_A_ja_maiusculo(self):
        assert normalizar_razao_social("EMPRESA EXEMPLO LTDA") == "EMPRESA EXEMPLO LTDA"

    def test_A_com_numeros(self):
        assert normalizar_razao_social("Empresa 123 Ltda") == "EMPRESA 123 LTDA"

    # B — inputs inválidos
    def test_B_vazio(self):
        assert normalizar_razao_social("") is None

    def test_B_apenas_espacos(self):
        assert normalizar_razao_social("   ") is None

    def test_B_none_simulado(self):
        assert normalizar_razao_social("") is None


# ─────────────────────────────────────────────────────────────
#  CNPJ
# ─────────────────────────────────────────────────────────────

class TestCNPJ:
    # CNPJ real com dígitos verificadores válidos
    CNPJ_OK_RAW = "11222333000181"
    CNPJ_OK_FMT = "11.222.333/0001-81"

    # A — aceita e normaliza
    def test_A_sem_pontuacao(self):
        assert normalizar_cnpj(self.CNPJ_OK_RAW) == self.CNPJ_OK_FMT

    def test_A_com_pontuacao_completa(self):
        assert normalizar_cnpj("11.222.333/0001-81") == self.CNPJ_OK_FMT

    def test_A_com_espacos(self):
        assert normalizar_cnpj("11 222 333 0001 81") == self.CNPJ_OK_FMT

    def test_A_mistura_pontuacao(self):
        assert normalizar_cnpj("11.222.333000181") == self.CNPJ_OK_FMT

    # B — rejeita entradas inválidas
    def test_B_menos_de_14_digitos(self):
        assert normalizar_cnpj("1234567890") is None

    def test_B_mais_de_14_digitos(self):
        assert normalizar_cnpj("112223330001810000") is None

    def test_B_todos_zeros(self):
        assert normalizar_cnpj("00000000000000") is None

    def test_B_todos_uns(self):
        assert normalizar_cnpj("11111111111111") is None

    def test_B_digito_verificador_errado(self):
        assert normalizar_cnpj("11222333000199") is None

    def test_B_letras_no_meio(self):
        # Após extrair dígitos, comprimento errado
        assert normalizar_cnpj("11.ABC.333/0001-81") is None


# ─────────────────────────────────────────────────────────────
#  CONTATO
# ─────────────────────────────────────────────────────────────

class TestContato:
    # A — aceita e normaliza
    def test_A_celular_11_digitos(self):
        assert normalizar_contato("31999990000") == "(31) 99999-0000"

    def test_A_celular_com_formatacao(self):
        assert normalizar_contato("(31) 99999-0000") == "(31) 99999-0000"

    def test_A_fixo_10_digitos(self):
        assert normalizar_contato("3133330000") == "(31) 3333-0000"

    def test_A_email_simples(self):
        assert normalizar_contato("contato@empresa.com") == "contato@empresa.com"

    def test_A_email_maiusculo_normaliza(self):
        assert normalizar_contato("CONTATO@EMPRESA.COM") == "contato@empresa.com"

    def test_A_email_com_ponto_no_nome(self):
        assert normalizar_contato("joao.silva@empresa.com.br") == "joao.silva@empresa.com.br"

    def test_A_email_com_plus(self):
        assert normalizar_contato("user+tag@domain.org") == "user+tag@domain.org"

    # B — rejeita entradas inválidas
    def test_B_telefone_9_digitos(self):
        assert normalizar_contato("999990000") is None

    def test_B_telefone_12_digitos(self):
        assert normalizar_contato("319999900001") is None

    def test_B_email_sem_arroba(self):
        assert normalizar_contato("contato_empresa.com") is None

    def test_B_email_sem_dominio(self):
        assert normalizar_contato("contato@") is None

    def test_B_texto_aleatorio(self):
        assert normalizar_contato("nao sou email nem telefone") is None

    def test_B_vazio(self):
        assert normalizar_contato("") is None


# ─────────────────────────────────────────────────────────────
#  SERVIÇO
# ─────────────────────────────────────────────────────────────

class TestServico:
    # A — aceita e normaliza
    def test_A_texto_simples(self):
        assert normalizar_servico("consultoria em ti") == "Consultoria Em Ti"

    def test_A_com_espacos_extras(self):
        assert normalizar_servico("  limpeza industrial  ") == "Limpeza Industrial"

    def test_A_palavra_unica(self):
        assert normalizar_servico("transporte") == "Transporte"

    # B — rejeita entradas inválidas
    def test_B_vazio(self):
        assert normalizar_servico("") is None

    def test_B_apenas_espacos(self):
        assert normalizar_servico("   ") is None

    def test_B_muito_curto(self):
        assert normalizar_servico("ti") is None

    def test_B_dois_chars(self):
        assert normalizar_servico("ab") is None


# ─────────────────────────────────────────────────────────────
#  ESTADOS
# ─────────────────────────────────────────────────────────────

class TestEstados:
    # A — aceita e normaliza
    def test_A_sigla_unica(self):
        assert normalizar_estados("MG") == ["MG"]

    def test_A_multiplas_virgula(self):
        assert normalizar_estados("MG, SP, RJ") == ["MG", "RJ", "SP"]

    def test_A_multiplas_sem_espaco(self):
        assert normalizar_estados("MG,SP,RJ") == ["MG", "RJ", "SP"]

    def test_A_separado_ponto_virgula(self):
        assert normalizar_estados("MG;SP;RJ") == ["MG", "RJ", "SP"]

    def test_A_separado_barra(self):
        assert normalizar_estados("MG/SP/RJ") == ["MG", "RJ", "SP"]

    def test_A_minusculo_normaliza(self):
        assert normalizar_estados("mg, sp") == ["MG", "SP"]

    def test_A_com_duplicatas(self):
        assert normalizar_estados("MG, SP, MG") == ["MG", "SP"]

    def test_A_ordenado_alfabeticamente(self):
        assert normalizar_estados("SP, MG, RJ") == ["MG", "RJ", "SP"]

    def test_A_nacional_variante1(self):
        assert normalizar_estados("Nacional") == ["NACIONAL"]

    def test_A_nacional_variante2(self):
        assert normalizar_estados("Todo o Brasil") == ["NACIONAL"]

    def test_A_nacional_variante3(self):
        assert normalizar_estados("Brasil") == ["NACIONAL"]

    def test_A_todos_os_estados(self):
        todos = "AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO"
        resultado = normalizar_estados(todos)
        assert len(resultado) == 27
        assert "MG" in resultado
        assert "SP" in resultado

    # B — rejeita entradas inválidas
    def test_B_sigla_inexistente(self):
        assert normalizar_estados("XX") is None

    def test_B_mistura_valido_invalido(self):
        assert normalizar_estados("MG, XX, SP") is None

    def test_B_nome_completo_estado(self):
        assert normalizar_estados("Minas Gerais") is None

    def test_B_vazio(self):
        assert normalizar_estados("") is None

    def test_B_apenas_espacos(self):
        assert normalizar_estados("   ") is None
