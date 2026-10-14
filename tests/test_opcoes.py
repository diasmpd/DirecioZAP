"""
Testes — opcoes.py (menus de serviços e regionais)
"""
import pytest

import opcoes
from opcoes import ESTADOS_ATENDIDOS, SERVICOS, escolher, normalizar_estados_atendidos, normalizar_servicos


def test_A_servicos_em_ordem_alfabetica_sem_acento_e_sem_repetir():
    assert len(SERVICOS) == 70 == len(set(SERVICOS))
    assert [opcoes._base(s) for s in SERVICOS] == sorted(opcoes._base(s) for s in SERVICOS)


@pytest.mark.parametrize("entrada, esperado", [
    ("1", [SERVICOS[0]]),
    ("3, 15, 22", [SERVICOS[2], SERVICOS[14], SERVICOS[21]]),
    ("3 a 5", SERVICOS[2:5]),
    ("3-5", SERVICOS[2:5]),
    ("3 5", [SERVICOS[2], SERVICOS[4]]),
    ("gás, pintura", ["Gás", "Pintura (Interna / Externa / Limpeza)"]),
    ("GAS e Grua", ["Gás", "Grua"]),
    ("5, 5, 5", [SERVICOS[4]]),
])
def test_A_escolher_servicos(entrada, esperado):
    assert escolher(entrada, SERVICOS) == (esperado, [])


@pytest.mark.parametrize("entrada", ["", "0", "71", "999", "elevador", "fundação", "xyz"])
def test_B_servicos_invalidos_ou_ambiguos(entrada):
    assert normalizar_servicos(entrada) is None


def test_A_servicos_gravados_separados_por_ponto_e_virgula():
    assert normalizar_servicos("1, 2") == f"{SERVICOS[0]}; {SERVICOS[1]}"


def test_A_explica_termo_ambiguo_com_os_numeros():
    msg = opcoes.explicar_invalidos("elevador", SERVICOS)
    assert "mais de uma opção" in msg and "Elevadores" in msg and "Elevador Cremalheira" in msg


@pytest.mark.parametrize("entrada, esperado", [
    ("MG, SP", "MG, SP"),
    ("mg e sp", "MG, SP"),
    ("MG SP RJ", "MG, SP, RJ"),
    ("1, 6", "MG, DF/GO"),
    ("DF", "DF/GO"),
    ("go, df", "DF/GO"),
    ("SP, MG", "MG, SP"),  # sempre na ordem da lista
    ("todos", ", ".join(ESTADOS_ATENDIDOS)),
    ("Nacional", ", ".join(ESTADOS_ATENDIDOS)),
])
def test_A_estados_atendidos(entrada, esperado):
    assert normalizar_estados_atendidos(entrada) == esperado


@pytest.mark.parametrize("entrada", ["PR", "MG, PR", "9", "", "M"])
def test_B_estados_fora_da_lista(entrada):
    assert normalizar_estados_atendidos(entrada) is None
