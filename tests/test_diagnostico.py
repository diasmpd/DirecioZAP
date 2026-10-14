"""
Testes — diagnostico.py (respostas da Meta simuladas; nenhuma chamada real)
"""
from unittest.mock import MagicMock

import pytest

import diagnostico
from diagnostico import AVISO, ERRO, OK

CFG = {"META_TOKEN": "t", "META_WABA_ID": "w1", "META_APP_SECRET": "s",
       "NGROK_DOMAIN": "abc.ngrok-free.dev", "WHATSAPP_PROVIDER": "Meta"}


@pytest.fixture
def graph(monkeypatch):
    respostas = {}
    def fake_get(url, **params):
        for trecho, resp in respostas.items():
            if trecho in url:
                return resp
        return 404, {}
    monkeypatch.setattr(diagnostico, "_get", fake_get)
    return respostas


def test_B_app_nao_vinculado_oferece_correcao(graph):
    graph["w1/subscribed_apps"] = (200, {"data": [{"whatsapp_business_api_data": {"id": "outro", "name": "X"}}]})
    c = diagnostico.checar_vinculo(CFG, "app1")
    assert c.status == ERRO and c.correcao == "vincular_app"


def test_A_app_vinculado(graph):
    graph["w1/subscribed_apps"] = (200, {"data": [{"whatsapp_business_api_data": {"id": "app1"}}]})
    assert diagnostico.checar_vinculo(CFG, "app1").status == OK


def test_B_sem_waba_id_e_aviso_nao_erro(graph):
    assert diagnostico.checar_vinculo({**CFG, "META_WABA_ID": ""}, "app1").status == AVISO


def test_B_token_revogado(graph):
    graph["debug_token"] = (200, {"data": {"is_valid": False, "error": {"message": "Session invalidated"}}})
    c, app_id = diagnostico.checar_token(CFG)
    assert c.status == ERRO and "Session invalidated" in c.detalhe and app_id is None


def test_B_token_que_expira_e_aviso(graph):
    graph["debug_token"] = (200, {"data": {"is_valid": True, "app_id": "app1", "expires_at": 123, "type": "USER",
        "granular_scopes": [{"scope": "whatsapp_business_messaging"}, {"scope": "whatsapp_business_management"}]}})
    c, app_id = diagnostico.checar_token(CFG)
    assert c.status == AVISO and app_id == "app1"


def test_B_webhook_sem_messages_e_url_errada(graph):
    graph["app1/subscriptions"] = (200, {"data": [{"object": "whatsapp_business_account", "active": True,
        "callback_url": "https://velho.ngrok-free.app/webhook", "fields": [{"name": "account_update"}]}]})
    c = diagnostico.checar_webhook(CFG, "app1")
    assert c.status == ERRO and "messages" in c.detalhe and "velho" in c.detalhe


def test_A_webhook_ok(graph):
    graph["app1/subscriptions"] = (200, {"data": [{"object": "whatsapp_business_account", "active": True,
        "callback_url": "https://abc.ngrok-free.dev/webhook", "fields": [{"name": "messages"}]}]})
    assert diagnostico.checar_webhook(CFG, "app1").status == OK


def test_B_numero_desconectado(graph):
    graph["/p1"] = (200, {"status": "PENDING", "display_phone_number": "+55"})
    assert diagnostico.checar_numero({**CFG, "META_PHONE_NUMBER_ID": "p1"}).status == ERRO


def test_A_vincular_app_faz_post(monkeypatch):
    post = MagicMock(return_value=MagicMock(ok=True, content=b"1", json=lambda: {"success": True}))
    monkeypatch.setattr(diagnostico.requests, "post", post)
    assert "vinculado" in diagnostico.vincular_app(CFG)
    assert post.call_args.args[0].endswith("/w1/subscribed_apps")
