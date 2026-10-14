"""Escolha das regionais em etapas, com a lista tocável do WhatsApp.

O fornecedor toca numa regional por vez (ou "Todas") e depois em Concluir, ou digita as
siglas de uma vez, como antes.

O andamento fica nos dados da sessão, em chaves com "_" que não vão para o cadastro:
  _etapa   "mais" (já escolheu algo)
  _parcial lista do que já foi escolhido
"""
import re

from opcoes import (
    ESTADOS_ATENDIDOS,
    _base,
    explicar_invalidos,
    menu,
    normalizar_estados_atendidos,
)
from resposta import Resposta

TIPOS = {"estados_atendidos"}

CONCLUIR = "CONCLUIR"
_ITEM_CONCLUIR = (CONCLUIR, "✓ Concluir")

# Respostas que encerram a escolha quando já há algo selecionado.
_FIM = {
    "CONCLUIR", "CONCLUIDO", "CONCLUIDA", "PRONTO", "FIM", "OK", "N", "NAO", "NAO OBRIGADO",
    "SO", "SO ISSO", "SO ESSE", "SO ESSES", "SO ESSA", "SO ESSAS", "FINALIZAR", "TERMINEI",
    "ACABEI", "SEGUIR", "CONTINUAR", "PROXIMO", "PROXIMA",
}


def limpar(dados: dict) -> None:
    dados.pop("_etapa", None)
    dados.pop("_parcial", None)


def _limpo(texto: str) -> str:
    return re.sub(r"[^A-Z0-9 ]", " ", _base(texto)).strip()


def _quer_concluir(texto: str) -> bool:
    return " ".join(_limpo(texto).split()) in _FIM


def _em_ordem(itens: list[str], opcoes: list[str]) -> list[str]:
    escolhidos = set(itens)
    return [o for o in opcoes if o in escolhidos]


# ── Regionais ──────────────────────────────────────────────────

def _prompt_regionais(pergunta: dict, parcial: list[str]) -> Resposta:
    if not parcial:
        return Resposta(
            f"{pergunta['pergunta']}\n"
            "Toque em *Escolher* ou digite as siglas, separadas por vírgula (ex: MG, SP). "
            "Se atende todas, digite TODAS.\n\n"
            f"{menu(ESTADOS_ATENDIDOS)}",
            lista=[(uf, uf) for uf in ESTADOS_ATENDIDOS] + [("TODAS", "Todas as regionais")],
        )
    faltam = [uf for uf in ESTADOS_ATENDIDOS if uf not in parcial]
    return Resposta(
        f"Regionais escolhidas até agora: {', '.join(parcial)}.\n\n"
        "Toque em *Concluir* se terminou, ou escolha outra regional "
        f"(digite CONCLUIR ou a sigla: {', '.join(faltam)}).",
        lista=[_ITEM_CONCLUIR] + [(uf, uf) for uf in faltam],
        lista_botao="Concluir ou mais",
    )


def _responder_regionais(texto: str, dados: dict, pergunta: dict):
    parcial = dados.get("_parcial") or []

    if parcial and _quer_concluir(texto):
        return "pronto", ", ".join(parcial)

    valor = normalizar_estados_atendidos(texto)
    if valor is None:
        detalhe = explicar_invalidos(texto, ESTADOS_ATENDIDOS) or "• nenhuma regional informada"
        return "invalido", (
            f"Não consegui entender:\n{detalhe}\n\n"
            f"{_prompt_regionais(pergunta, parcial)}"
        )

    escolhidos = valor.split(", ")
    todas = _em_ordem(parcial + escolhidos, ESTADOS_ATENDIDOS)
    # Quem digita várias de uma vez já respondeu tudo; quem toca uma por vez pode querer mais.
    if len(todas) == len(ESTADOS_ATENDIDOS) or (not parcial and len(escolhidos) > 1):
        return "pronto", ", ".join(todas)
    dados["_parcial"] = todas
    dados["_etapa"] = "mais"
    return "continua", _prompt_regionais(pergunta, todas)


# ── Interface usada pelo conversation.py ───────────────────────

def prompt(pergunta: dict, dados: dict | None = None) -> Resposta:
    """A mensagem da etapa atual da pergunta (a pergunta em si, se ainda não começou)."""
    return _prompt_regionais(pergunta, (dados or {}).get("_parcial") or [])


def responder(pergunta: dict, texto: str, dados: dict):
    """("pronto", valor final) | ("continua", próxima mensagem) | ("invalido", mensagem de erro).
    Atualiza o andamento em `dados`."""
    return _responder_regionais(texto, dados, pergunta)
