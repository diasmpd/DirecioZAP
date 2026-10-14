"""Escolha de serviços e regionais em etapas, com as listas tocáveis do WhatsApp.

Serviços: o fornecedor escolhe uma categoria, responde com os números dos serviços dela e
depois toca em Concluir ou abre outra categoria. Também pode digitar o nome do serviço
direto (ex: "pintura, gás"). Regionais: toca numa regional por vez (ou "Todas") ou digita
as siglas de uma vez, como antes.

O andamento fica nos dados da sessão, em chaves com "_" que não vão para o cadastro:
  _etapa   "cat:<i>" (vendo os serviços da categoria i) ou "mais" (já escolheu algo)
  _parcial lista do que já foi escolhido
"""
import re

from opcoes import (
    CATEGORIAS,
    ESTADOS_ATENDIDOS,
    SERVICOS,
    _base,
    escolher,
    explicar_invalidos,
    menu,
    normalizar_estados_atendidos,
)
from resposta import Resposta, prefixar

TIPOS = {"servicos", "estados_atendidos"}

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


# ── Serviços ───────────────────────────────────────────────────

def _menu_categorias() -> str:
    return menu([nome for nome, _ in CATEGORIAS])


def _lista_categorias() -> list[tuple[str, str]]:
    return [(f"CATEGORIA {i}", nome) for i, (nome, _) in enumerate(CATEGORIAS, 1)]


def _prompt_servicos(pergunta: dict, parcial: list[str]) -> Resposta:
    if not parcial:
        return Resposta(
            f"{pergunta['pergunta']}\n"
            "Toque em *Ver categorias* (ou digite o número da categoria) para ver os serviços dela. "
            "Se preferir, digite direto o nome do serviço (ex: pintura, gás).\n\n"
            f"{_menu_categorias()}",
            lista=_lista_categorias(),
            lista_botao="Ver categorias",
        )
    return Resposta(
        f"Serviços escolhidos até agora: {'; '.join(parcial)}.\n\n"
        "Toque em *Concluir* se terminou, ou escolha outra categoria para incluir mais serviços "
        "(digite CONCLUIR ou o número da categoria).\n\n"
        f"{_menu_categorias()}",
        lista=[_ITEM_CONCLUIR] + _lista_categorias()[:9],
        lista_botao="Concluir ou mais",
    )


def _prompt_categoria(i: int) -> Resposta:
    nome, itens = CATEGORIAS[i]
    return Resposta(
        f"*{nome}*: responda com os números dos serviços que sua empresa faz (ex: 1, 3).\n\n"
        f"{menu(itens)}\n\n"
        "Digite VOLTAR para ver as outras categorias."
    )


def _categoria(texto: str) -> int | None:
    """Índice da categoria pedida: "3", "CATEGORIA 3" (id da lista) ou o nome dela."""
    limpo = _limpo(texto)
    m = re.fullmatch(r"(?:CATEGORIA\s*)?(\d+)", limpo)
    if m:
        n = int(m.group(1))
        return n - 1 if 1 <= n <= len(CATEGORIAS) else None
    bases = [_limpo(nome) for nome, _ in CATEGORIAS]
    if limpo in bases:
        return bases.index(limpo)
    return None


def _categoria_parcial(texto: str) -> int | None:
    """'fundação' -> a categoria cujo nome contém o termo, se for só uma."""
    limpo = _limpo(texto)
    if len(limpo) < 4:
        return None
    achadas = [i for i, (nome, _) in enumerate(CATEGORIAS) if limpo in _limpo(nome)]
    return achadas[0] if len(achadas) == 1 else None


def _adicionar_servicos(escolhidos: list[str], dados: dict):
    parcial = _em_ordem((dados.get("_parcial") or []) + escolhidos, SERVICOS)
    dados["_parcial"] = parcial
    dados["_etapa"] = "mais"
    return "continua", prefixar(f"Adicionado: {'; '.join(escolhidos)}.", _prompt_servicos({}, parcial))


def _responder_servicos(texto: str, dados: dict, pergunta: dict):
    etapa = dados.get("_etapa") or ""
    parcial = dados.get("_parcial") or []

    if etapa.startswith("cat:"):
        i = int(etapa[4:])
        _, itens = CATEGORIAS[i]
        escolhidos, invalidos = escolher(texto, itens)
        if escolhidos and not invalidos:
            return _adicionar_servicos(escolhidos, dados)
        detalhe = explicar_invalidos(texto, itens) if invalidos else "• nenhum serviço informado"
        return "invalido", f"Não consegui entender:\n{detalhe}\n\n{_prompt_categoria(i)}"

    if parcial and _quer_concluir(texto):
        return "pronto", "; ".join(parcial)

    i = _categoria(texto)
    if i is not None:
        dados["_etapa"] = f"cat:{i}"
        return "continua", _prompt_categoria(i)

    if re.search(r"\d", texto):
        # Sem uma categoria aberta, números são de categoria — e só uma por vez.
        return "invalido", (
            f"Escolha uma categoria por vez: digite o número dela (1 a {len(CATEGORIAS)}) "
            "ou toque em *Ver categorias*.\n\n"
            f"{_menu_categorias()}"
        )

    escolhidos, invalidos = escolher(texto, SERVICOS)
    if escolhidos and not invalidos:
        return _adicionar_servicos(escolhidos, dados)

    i = _categoria_parcial(texto)
    if i is not None:
        dados["_etapa"] = f"cat:{i}"
        return "continua", _prompt_categoria(i)

    if not parcial and _quer_concluir(texto):
        return "invalido", "Escolha pelo menos um serviço antes de concluir.\n\n" + _prompt_servicos(pergunta, [])
    return "invalido", (
        f"Não consegui entender:\n{explicar_invalidos(texto, SERVICOS, numerar=False)}\n\n"
        f"Escolha uma categoria para ver a lista completa (1 a {len(CATEGORIAS)}).\n\n"
        f"{_menu_categorias()}"
    )


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
    dados = dados or {}
    tipo = (pergunta.get("tipo") or "").lower()
    etapa = dados.get("_etapa") or ""
    parcial = dados.get("_parcial") or []
    if tipo == "servicos":
        if etapa.startswith("cat:"):
            return _prompt_categoria(int(etapa[4:]))
        return _prompt_servicos(pergunta, parcial)
    return _prompt_regionais(pergunta, parcial)


def responder(pergunta: dict, texto: str, dados: dict):
    """("pronto", valor final) | ("continua", próxima mensagem) | ("invalido", mensagem de erro).
    Atualiza o andamento em `dados`."""
    if (pergunta.get("tipo") or "").lower() == "servicos":
        return _responder_servicos(texto, dados, pergunta)
    return _responder_regionais(texto, dados, pergunta)


def voltar(pergunta: dict, dados: dict) -> Resposta | None:
    """VOLTAR dentro de uma categoria volta para as categorias; fora dela, None (o VOLTAR
    normal, para a pergunta anterior)."""
    if not (dados.get("_etapa") or "").startswith("cat:"):
        return None
    dados["_etapa"] = "mais" if dados.get("_parcial") else None
    if not dados["_etapa"]:
        dados.pop("_etapa")
    return prompt(pergunta, dados)
