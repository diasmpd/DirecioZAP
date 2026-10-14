"""
Testes — notificacao.py (aviso por e-mail via Outlook; o envio real é bloqueado no conftest)
"""
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


def test_A_sem_destinatario_nao_envia(monkeypatch, bloquear_outlook):
    monkeypatch.setattr("config.settings.NOTIFY_EMAIL", "")
    assert notificacao.notificar_novo_cadastro("55", {}, SAMPLE_PERGUNTAS) is None
    bloquear_outlook.assert_not_called()


def test_A_com_destinatario_envia_em_thread(monkeypatch, bloquear_outlook):
    monkeypatch.setattr("config.settings.NOTIFY_EMAIL", "a@x.com")
    t = notificacao.notificar_novo_cadastro("5531995971053", {"razao_social": "ACME"}, SAMPLE_PERGUNTAS)
    t.join(5)
    para, assunto, _ = bloquear_outlook.call_args.args
    assert para == ["a@x.com"] and "ACME" in assunto


def test_B_falha_no_outlook_nao_propaga(monkeypatch, bloquear_outlook):
    monkeypatch.setattr("config.settings.NOTIFY_EMAIL", "a@x.com")
    bloquear_outlook.side_effect = RuntimeError("Outlook fechado")
    t = notificacao.notificar_novo_cadastro("55", {}, SAMPLE_PERGUNTAS)
    t.join(5)  # a exceção fica no log, não sobe
    assert not t.is_alive()
