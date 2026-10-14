"""Diagnóstico de ponta a ponta: por que o bot não responde?

Roda, em ordem, as checagens que resolveram os problemas reais da implantação: banco,
token da Meta, número, vínculo conta WhatsApp → app (sem ele a Meta não entrega nada,
mesmo com o webhook certo), webhook do app, bot local e túnel público. Tudo é leitura,
exceto `vincular_app`, que só roda quando o usuário clica em "Corrigir".
"""
from dataclasses import dataclass

import requests

OK, AVISO, ERRO = "ok", "aviso", "erro"


@dataclass
class Checagem:
    nome: str
    status: str
    detalhe: str
    correcao: str | None = None  # chave de uma correção automática disponível


def _graph(cfg: dict) -> str:
    return f"https://graph.facebook.com/{cfg.get('META_API_VERSION') or 'v23.0'}"


def _get(url: str, **params) -> tuple[int, dict]:
    r = requests.get(url, params=params, timeout=15)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def _erro_meta(body: dict) -> str:
    e = body.get("error") or {}
    return f"{e.get('message', 'erro desconhecido')} (código {e.get('code', '?')})"


def checar_banco(cfg: dict) -> Checagem:
    url = cfg.get("DATABASE_URL", "").strip()
    if not url:
        return Checagem("Banco de dados", ERRO, "DATABASE_URL não configurado.")
    try:
        from db import Database
        n = len(Database(url).get_perguntas())
    except Exception as ex:
        return Checagem("Banco de dados", ERRO, f"Sem conexão com o Neon: {ex}")
    if n == 0:
        return Checagem("Banco de dados", ERRO,
                        "Conectado, mas não há perguntas ativas — o bot responde 'sem perguntas configuradas'.")
    return Checagem("Banco de dados", OK, f"Conectado. {n} pergunta(s) ativa(s).")


def checar_token(cfg: dict) -> tuple[Checagem, str | None]:
    """Retorna também o App ID dono do token, usado nas checagens seguintes."""
    token = cfg.get("META_TOKEN", "").strip()
    if not token:
        return Checagem("Token da Meta", ERRO, "META_TOKEN não configurado."), None
    code, body = _get(f"{_graph(cfg)}/debug_token", input_token=token, access_token=token)
    data = body.get("data") or {}
    if code != 200 or not data.get("is_valid"):
        motivo = (data.get("error") or {}).get("message") or _erro_meta(body)
        return Checagem("Token da Meta", ERRO, f"Token inválido ou revogado: {motivo}. Gere um novo."), None
    escopos = {s.get("scope") for s in data.get("granular_scopes", [])}
    faltando = {"whatsapp_business_messaging", "whatsapp_business_management"} - escopos
    if faltando:
        return Checagem("Token da Meta", ERRO,
                        f"Faltam permissões no token: {', '.join(sorted(faltando))}."), data.get("app_id")
    validade = "permanente" if not data.get("expires_at") else "EXPIRA — troque por um token de usuário do sistema"
    status = OK if not data.get("expires_at") else AVISO
    return Checagem("Token da Meta", status, f"Válido ({data.get('type', '?')}, {validade})."), data.get("app_id")


def checar_numero(cfg: dict) -> Checagem:
    pid = cfg.get("META_PHONE_NUMBER_ID", "").strip()
    if not pid:
        return Checagem("Número do WhatsApp", ERRO, "META_PHONE_NUMBER_ID não configurado.")
    code, body = _get(
        f"{_graph(cfg)}/{pid}",
        fields="display_phone_number,verified_name,status,quality_rating,messaging_limit_tier",
        access_token=cfg.get("META_TOKEN", ""),
    )
    if code != 200:
        return Checagem("Número do WhatsApp", ERRO, f"Não foi possível ler o número: {_erro_meta(body)}")
    resumo = (f"{body.get('display_phone_number')} \"{body.get('verified_name')}\" — "
              f"status {body.get('status')}, qualidade {body.get('quality_rating')}, "
              f"limite {body.get('messaging_limit_tier')}")
    if body.get("status") != "CONNECTED":
        return Checagem("Número do WhatsApp", ERRO, f"Número não está conectado: {resumo}")
    if body.get("quality_rating") not in (None, "GREEN", "UNKNOWN"):
        return Checagem("Número do WhatsApp", AVISO, f"Qualidade baixa — risco de bloqueio: {resumo}")
    return Checagem("Número do WhatsApp", OK, resumo)


def checar_vinculo(cfg: dict, app_id: str | None) -> Checagem:
    waba = cfg.get("META_WABA_ID", "").strip()
    if not waba:
        return Checagem("Conta WhatsApp → app", AVISO,
                        "META_WABA_ID não configurado — não dá para conferir o vínculo. "
                        "O ID está no WhatsApp Manager (Configurações da conta).")
    code, body = _get(f"{_graph(cfg)}/{waba}/subscribed_apps", access_token=cfg.get("META_TOKEN", ""))
    if code != 200:
        return Checagem("Conta WhatsApp → app", ERRO, f"Não foi possível ler: {_erro_meta(body)}")
    apps = [(a.get("whatsapp_business_api_data") or {}) for a in body.get("data", [])]
    if app_id and any(a.get("id") == app_id for a in apps):
        return Checagem("Conta WhatsApp → app", OK, "O app DirecioZAP recebe as mensagens desta conta.")
    nomes = ", ".join(a.get("name", "?") for a in apps) or "nenhum"
    return Checagem("Conta WhatsApp → app", ERRO,
                    f"O app não está vinculado à conta WhatsApp (vinculados: {nomes}). "
                    "Sem isso a Meta não entrega nenhuma mensagem ao bot.", correcao="vincular_app")


def checar_webhook(cfg: dict, app_id: str | None) -> Checagem:
    secret = cfg.get("META_APP_SECRET", "").strip()
    if not app_id or not secret:
        return Checagem("Webhook do app", ERRO if not secret else AVISO,
                        "META_APP_SECRET não configurado — o bot rejeita todos os webhooks." if not secret
                        else "Sem App ID (token inválido), não dá para conferir o webhook.")
    code, body = _get(f"{_graph(cfg)}/{app_id}/subscriptions", access_token=f"{app_id}|{secret}")
    if code != 200:
        return Checagem("Webhook do app", ERRO,
                        f"Não foi possível ler (App Secret errado?): {_erro_meta(body)}")
    sub = next((s for s in body.get("data", []) if s.get("object") == "whatsapp_business_account"), None)
    if not sub:
        return Checagem("Webhook do app", ERRO, "Nenhum webhook do WhatsApp configurado no app.")
    campos = {f.get("name") for f in sub.get("fields", [])}
    dominio = cfg.get("NGROK_DOMAIN", "").strip()
    esperado = f"https://{dominio}/webhook" if dominio else None
    problemas = []
    if "messages" not in campos:
        problemas.append("campo 'messages' não assinado")
    if not sub.get("active"):
        problemas.append("webhook inativo")
    if esperado and sub.get("callback_url") != esperado:
        problemas.append(f"URL é {sub.get('callback_url')}, esperado {esperado}")
    if problemas:
        return Checagem("Webhook do app", ERRO, "; ".join(problemas) + ".")
    return Checagem("Webhook do app", OK, f"{sub.get('callback_url')} com 'messages' assinado.")


def checar_bot_local() -> Checagem:
    try:
        r = requests.get("http://127.0.0.1:3000/", timeout=5)
        if r.ok:
            return Checagem("Bot local", OK, "Respondendo na porta 3000.")
        return Checagem("Bot local", ERRO, f"Porta 3000 respondeu HTTP {r.status_code}.")
    except requests.RequestException:
        return Checagem("Bot local", ERRO, "Bot parado — clique em 'Iniciar Bot' ou confira a tarefa agendada.")


def checar_tunel(cfg: dict) -> Checagem:
    dominio = cfg.get("NGROK_DOMAIN", "").strip()
    if not dominio:
        return Checagem("Túnel público (ngrok)", AVISO,
                        "Sem domínio estático: a URL muda a cada reinício e o webhook da Meta quebra.")
    try:
        r = requests.get(f"https://{dominio}/", timeout=10, headers={"ngrok-skip-browser-warning": "1"})
    except requests.RequestException as ex:
        return Checagem("Túnel público (ngrok)", ERRO, f"{dominio} inacessível: {ex}")
    if r.ok and r.headers.get("content-type", "").startswith("application/json"):
        return Checagem("Túnel público (ngrok)", OK, f"https://{dominio} chega ao bot.")
    return Checagem("Túnel público (ngrok)", ERRO,
                    f"https://{dominio} respondeu HTTP {r.status_code} — ngrok parado ou em outro PC.")


def checar_outlook(cfg: dict) -> Checagem | None:
    if not cfg.get("NOTIFY_EMAIL", "").strip():
        return None
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            win32com.client.Dispatch("Outlook.Application")
        finally:
            pythoncom.CoUninitialize()
    except Exception as ex:
        return Checagem("Aviso por e-mail (Outlook)", ERRO, f"Outlook indisponível: {ex}")
    return Checagem("Aviso por e-mail (Outlook)", OK, f"Outlook disponível; avisos para {cfg['NOTIFY_EMAIL']}.")


def executar(cfg: dict) -> list[Checagem]:
    resultados = [checar_banco(cfg)]
    if (cfg.get("WHATSAPP_PROVIDER") or "").lower() == "meta":
        token, app_id = checar_token(cfg)
        resultados += [token, checar_numero(cfg), checar_vinculo(cfg, app_id), checar_webhook(cfg, app_id)]
    else:
        resultados.append(Checagem("Provedor", AVISO, "Provedor Twilio: checagens da Meta puladas."))
    resultados += [checar_bot_local(), checar_tunel(cfg)]
    outlook = checar_outlook(cfg)
    if outlook:
        resultados.append(outlook)
    return resultados


def vincular_app(cfg: dict) -> str:
    """Correção para 'Conta WhatsApp → app': assina o app na conta (POST subscribed_apps)."""
    r = requests.post(f"{_graph(cfg)}/{cfg['META_WABA_ID'].strip()}/subscribed_apps",
                      params={"access_token": cfg.get("META_TOKEN", "")}, timeout=15)
    body = r.json() if r.content else {}
    if r.ok and body.get("success"):
        return "App vinculado à conta WhatsApp."
    raise RuntimeError(_erro_meta(body))


CORRECOES = {"vincular_app": vincular_app}
