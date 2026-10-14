"""
Testes — notificacao.py (aviso por e-mail via Outlook; o envio real é bloqueado no conftest)
"""
from unittest.mock import MagicMock

import notificacao
from tests.conftest import SAMPLE_PERGUNTAS


def test_A_destinatarios_aceita_virgula_e_ponto_e_virgula():
    assert notificacao.destinatarios(" a@x.com; b@x.com ,c@x.com,") == ["a@x.com", "b@x.com", "c@x.com"]
    assert notificacao.destinatarios(None) == []


def test_A_email_usa_labels_e_escapa_html():
    assunto, corpo = notificacao.montar_email(
        "5531995971053",
        {"razao_social": "ACME <script>", "cnpj": "11.222.333/0001-81"},
        SAMPLE_PERGUNTAS,
    )
    assert "ACME <script>" in assunto  # assunto é texto puro
    assert "Razão Social" in corpo and "CNPJ" in corpo
    assert "<script>" not in corpo and "ACME &lt;script&gt;" in corpo
    assert "+5531995971053" in corpo


class FakeDB:
    def __init__(self, pendentes):
        self.pendentes = pendentes
        self.marcados = []

    def get_cadastros_sem_aviso(self):
        return [c for c in self.pendentes if c["id"] not in self.marcados]

    def get_todas_perguntas(self):
        return SAMPLE_PERGUNTAS

    def marcar_notificado(self, id_):
        self.marcados.append(id_)


PENDENTES = [
    {"id": "a", "phone": "5531995971053", "dados": {"razao_social": "ACME"}, "criado_em": "2026-10-14T13:00:00+00:00"},
    {"id": "b", "phone": "5531988887777", "dados": {"razao_social": "BETA"}, "criado_em": "2026-10-14T13:05:00+00:00"},
]


def test_A_envia_e_marca_cada_pendente():
    db, enviar = FakeDB(PENDENTES), MagicMock()
    assert notificacao.enviar_pendentes(db, ["a@x.com"], enviar) == (2, 0)
    assert db.marcados == ["a", "b"]
    assert "ACME" in enviar.call_args_list[0].args[1]
    assert "14/10/2026 10:00" in enviar.call_args_list[0].args[2]  # horário do cadastro, em Brasília


def test_B_outlook_falha_para_e_deixa_pendente():
    db = FakeDB(PENDENTES)
    enviar = MagicMock(side_effect=[None, RuntimeError("Outlook fechado")])
    assert notificacao.enviar_pendentes(db, ["a@x.com"], enviar) == (1, 1)
    assert db.marcados == ["a"]  # "b" sai na próxima execução


def test_B_sem_destinatario_nao_envia_nem_marca():
    db, enviar = FakeDB(PENDENTES), MagicMock()
    assert notificacao.enviar_pendentes(db, [], enviar) == (0, 0)
    enviar.assert_not_called()
    assert db.marcados == []
