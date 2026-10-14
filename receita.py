"""Consulta do CNPJ na Receita Federal, por serviços públicos gratuitos e sem chave.

Serve para preencher a Razão Social sozinha e registrar a situação cadastral do CNPJ.
Tenta a ReceitaWS (rápida, mas limitada a 3 consultas por minuto) e, se ela falhar, a
BrasilAPI. Se nenhuma responder (sem internet, limite, CNPJ alfanumérico que elas ainda não
conhecem), devolve None: o bot segue perguntando a Razão Social como antes.
"""
import re

import requests

from log_setup import get_logger

log = get_logger("receita")

_TIMEOUT_S = 4

# Campo extra gravado no cadastro (não é pergunta): aparece no Excel e no e-mail de aviso.
CAMPO_SITUACAO = "situacao_cnpj"
LABEL_SITUACAO = "Situação na Receita"
NAO_ENCONTRADO = "NÃO ENCONTRADO NA RECEITA"

_http = requests.Session()


def _buscar(url: str) -> requests.Response | None:
    try:
        return _http.get(url, timeout=_TIMEOUT_S)
    except Exception as e:
        log.warning("Consulta do CNPJ falhou (%s): %s", url.split("/")[2], e)
        return None


def _json(resp: requests.Response) -> dict | None:
    try:
        dados = resp.json()
    except ValueError:
        return None
    return dados if isinstance(dados, dict) else None


def _info(razao, situacao, municipio, uf) -> dict | None:
    razao = (razao or "").strip()
    if not razao:
        return None
    return {
        "razao_social": razao,
        "situacao": (situacao or "").strip().upper(),
        "municipio": (municipio or "").strip().title(),
        "uf": (uf or "").strip().upper(),
    }


def _receitaws(digitos: str) -> dict | None:
    resp = _buscar(f"https://receitaws.com.br/v1/cnpj/{digitos}")
    if resp is None:
        return None
    dados = _json(resp)
    if not resp.ok or not dados:
        log.warning("ReceitaWS recusou a consulta: HTTP %s", resp.status_code)
        return None
    if dados.get("status") == "ERROR":
        mensagem = (dados.get("message") or "").lower()
        if "rejeitado" in mensagem or "encontrado" in mensagem:
            return {"situacao": NAO_ENCONTRADO}
        return None
    return _info(dados.get("nome"), dados.get("situacao"), dados.get("municipio"), dados.get("uf"))


def _brasilapi(digitos: str) -> dict | None:
    resp = _buscar(f"https://brasilapi.com.br/api/cnpj/v1/{digitos}")
    if resp is None:
        return None
    if resp.status_code == 404:
        return {"situacao": NAO_ENCONTRADO}
    dados = _json(resp)
    if not resp.ok or not dados:
        log.warning("BrasilAPI recusou a consulta: HTTP %s", resp.status_code)
        return None
    return _info(dados.get("razao_social"), dados.get("descricao_situacao_cadastral"),
                 dados.get("municipio"), dados.get("uf"))


def consultar_cnpj(cnpj: str) -> dict | None:
    """{"razao_social", "situacao", "municipio", "uf"} — ou {"situacao": NAO_ENCONTRADO}
    se a Receita não conhece o número — ou None se não deu para consultar."""
    digitos = re.sub(r"[^0-9A-Za-z]", "", cnpj or "")
    for fonte in (_receitaws, _brasilapi):
        info = fonte(digitos)
        if info is not None:
            return info
    return None
