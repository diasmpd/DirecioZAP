"""Listas fechadas de respostas: serviços contratados e regionais (UFs) atendidas.

Fonte: listas da área de Suprimentos (out/2026). Os serviços ficam em ordem alfabética e o
fornecedor responde com os números do menu ("3, 15, 22", "3 a 5") ou com o nome/parte do
nome ("gás, pintura"). Um termo que bate com mais de um serviço é recusado como ambíguo, para
não cadastrar o fornecedor num serviço que ele não escolheu.
"""
import re
import unicodedata


def _base(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.upper().split())


_SERVICOS_ORIGINAIS = [
    "Fechamento de terreno em tapume",
    "Refeição Operacional (Café / Lanche / Almoço / Jantar)",
    "Vistoria Cautelar",
    "Exames médicos / Medições Ambientais",
    "Perfuração de Poço Artesiano",
    "Energia Provisória",
    "Monitoramento Eletrônico",
    "Agente de Portaria / Vigia",
    "Acompanhamento Topográfico",
    "Elevador Cremalheira",
    "Grua",
    "Manipulador Telescópico",
    "Munck",
    "Retroescavadeira / Escavadeira",
    "Guindaste",
    "Equipamentos Leves/Pequenos",
    "Limpeza do terreno / Supressão",
    "Demolição",
    "Terraplanagem",
    "Concreto Usinado",
    "Lançamento / Adensamento / Acabamento de Concreto",
    "Controle Tecnológico Concreto",
    "Controle Tecnológico de Solos",
    "Contenção",
    "Fundação Profunda Mecanizada",
    "Fundação Profunda Manual",
    "Consultoria de Fundação",
    "Ensaios de Fundação",
    "Fundação Superficial",
    "ESTRUTURA CONVENCIONAL - Forma / Armação / Lançamento",
    "PAREDE DE CONCRETO - Armação / Lançamento / Instalações",
    "Drenagem",
    "Redes de Água / Esgoto",
    "Rede Elétrica / Iluminação pública / Subestação definitiva",
    "Subestação Definitiva / Entrada de Energia Definitiva",
    "Pavimentação Asfáltica / Intertravado / Meio-fio / Calçadas",
    "ETE",
    "ETA",
    "Reservatório - Fornecimento e Montagem",
    "Reservatório - Consultoria",
    "Reservatório - Instalações Hidráulicas",
    "Engradamento e telhamento, incluindo rufo e calhas",
    "Impermeabilização",
    "Assentamento Cerâmico",
    "Gesso (Forro, bloco e Drywall)",
    "Gesso Liso",
    "Instalação de Piso Laminado / Vinílico",
    "Pintura (Interna / Externa / Limpeza)",
    "Alvenaria / Muro de Divisa",
    "Interfonia / CFTV / Automação",
    "Gás",
    "Redes de Incêndio / SDAI - Alarme e Detecção",
    "Sistema de Pressurização / Exaustão",
    "Instalação Elétrica Interna",
    "Instalação Hidráulica Interna",
    "Esquadrias de alumínio",
    "Esquadrias Especiais (Guarda-corpo / Brise / Pele de vidro / Fora do Padrão)",
    "Esquadrias de madeira (Porta Pronta)",
    "Serralheria Interna",
    "Serralheria Externa",
    "Fechamento de Shaft (madeira)",
    "Paisagismo",
    "Sinalização",
    "Quadras e Equip. de Lazer",
    "Elevadores",
    "Plataformas PNE (ATÉ 4M)",
    "Consultoria de Elevador Definitivo – Suprimentos",
    "SLQA",
    "Tela Fachadeira",
    "Estrutura Pré-moldada",
]

SERVICOS = sorted(_SERVICOS_ORIGINAIS, key=_base)

# Categorias para o fornecedor não precisar rolar os 70 serviços: no máximo 9 (a lista
# interativa do WhatsApp tem 10 linhas e uma é o "Concluir") e nome com até 24 caracteres.
_CATEGORIAS_ORIGINAIS = [
    ("Apoio à obra", [
        "Fechamento de terreno em tapume",
        "Refeição Operacional (Café / Lanche / Almoço / Jantar)",
        "Vistoria Cautelar",
        "Exames médicos / Medições Ambientais",
        "Perfuração de Poço Artesiano",
        "Energia Provisória",
        "Monitoramento Eletrônico",
        "Agente de Portaria / Vigia",
        "Acompanhamento Topográfico",
        "Tela Fachadeira",
    ]),
    ("Equipamentos", [
        "Elevador Cremalheira",
        "Grua",
        "Manipulador Telescópico",
        "Munck",
        "Retroescavadeira / Escavadeira",
        "Guindaste",
        "Equipamentos Leves/Pequenos",
    ]),
    ("Terraplenagem e fundação", [
        "Limpeza do terreno / Supressão",
        "Demolição",
        "Terraplanagem",
        "Controle Tecnológico de Solos",
        "Contenção",
        "Fundação Profunda Mecanizada",
        "Fundação Profunda Manual",
        "Consultoria de Fundação",
        "Ensaios de Fundação",
        "Fundação Superficial",
    ]),
    ("Concreto e estrutura", [
        "Concreto Usinado",
        "Lançamento / Adensamento / Acabamento de Concreto",
        "Controle Tecnológico Concreto",
        "ESTRUTURA CONVENCIONAL - Forma / Armação / Lançamento",
        "PAREDE DE CONCRETO - Armação / Lançamento / Instalações",
        "Estrutura Pré-moldada",
        "Alvenaria / Muro de Divisa",
    ]),
    ("Infraestrutura", [
        "Drenagem",
        "Redes de Água / Esgoto",
        "Rede Elétrica / Iluminação pública / Subestação definitiva",
        "Subestação Definitiva / Entrada de Energia Definitiva",
        "Pavimentação Asfáltica / Intertravado / Meio-fio / Calçadas",
        "ETE",
        "ETA",
        "Reservatório - Fornecimento e Montagem",
        "Reservatório - Consultoria",
        "Reservatório - Instalações Hidráulicas",
    ]),
    ("Cobertura e acabamento", [
        "Engradamento e telhamento, incluindo rufo e calhas",
        "Impermeabilização",
        "Assentamento Cerâmico",
        "Gesso (Forro, bloco e Drywall)",
        "Gesso Liso",
        "Instalação de Piso Laminado / Vinílico",
        "Pintura (Interna / Externa / Limpeza)",
    ]),
    ("Instalações", [
        "Interfonia / CFTV / Automação",
        "Gás",
        "Redes de Incêndio / SDAI - Alarme e Detecção",
        "Sistema de Pressurização / Exaustão",
        "Instalação Elétrica Interna",
        "Instalação Hidráulica Interna",
    ]),
    ("Esquadrias e serralheria", [
        "Esquadrias de alumínio",
        "Esquadrias Especiais (Guarda-corpo / Brise / Pele de vidro / Fora do Padrão)",
        "Esquadrias de madeira (Porta Pronta)",
        "Serralheria Interna",
        "Serralheria Externa",
        "Fechamento de Shaft (madeira)",
    ]),
    ("Elevador e áreas comuns", [
        "Elevadores",
        "Plataformas PNE (ATÉ 4M)",
        "Consultoria de Elevador Definitivo – Suprimentos",
        "Paisagismo",
        "Sinalização",
        "Quadras e Equip. de Lazer",
        "SLQA",
    ]),
]

CATEGORIAS = [(nome, sorted(itens, key=_base)) for nome, itens in _CATEGORIAS_ORIGINAIS]

ESTADOS_ATENDIDOS = ["MG", "SP", "RJ", "BA", "PE", "DF/GO", "CE", "AM"]

_TODOS = {"TODOS", "TODAS", "TODOS OS ESTADOS", "NACIONAL", "BRASIL", "TODO O BRASIL"}


def menu(opcoes: list[str]) -> str:
    return "\n".join(f"{i}. {o}" for i, o in enumerate(opcoes, 1))


def _tokens(texto: str) -> list[str]:
    """Separa por vírgula, ponto e vírgula, quebra de linha e o conector "e"."""
    partes = re.split(r"[,;\n]+|\s+E\s+", _base(texto))
    return [p.strip(" .") for p in partes if p.strip(" .")]


def _numeros(token: str, total: int) -> list[int] | None:
    """'3' -> [3]; '3 5 7' -> [3, 5, 7]; '3-5' ou '3 A 5' -> [3, 4, 5]. None se não for numérico."""
    faixa = re.fullmatch(r"(\d+)\s*(?:-|A|ATE)\s*(\d+)", token)
    if faixa:
        a, b = int(faixa.group(1)), int(faixa.group(2))
        nums = list(range(min(a, b), max(a, b) + 1))
    elif re.fullmatch(r"\d+(\s+\d+)*", token):
        nums = [int(n) for n in token.split()]
    else:
        return None
    return nums if all(1 <= n <= total for n in nums) else []


def escolher(texto: str, opcoes: list[str]) -> tuple[list[str], list[str]]:
    """(escolhidos na ordem do menu, termos não reconhecidos)."""
    bases = [_base(o) for o in opcoes]
    escolhidos: set[int] = set()
    invalidos: list[str] = []
    for tok in _tokens(texto):
        nums = _numeros(tok, len(opcoes))
        if nums:
            escolhidos.update(n - 1 for n in nums)
            continue
        if nums == []:  # número fora da lista
            invalidos.append(tok)
            continue
        exatos = [i for i, b in enumerate(bases) if b == tok]
        parciais = exatos or [i for i, b in enumerate(bases) if tok in b]
        if len(parciais) == 1:
            escolhidos.add(parciais[0])
        else:
            invalidos.append(tok)  # nenhum ou mais de um serviço com esse termo
    return [opcoes[i] for i in sorted(escolhidos)], invalidos


def explicar_invalidos(texto: str, opcoes: list[str], numerar: bool = True) -> str:
    """Diz ao fornecedor o que não foi entendido — e, se o termo bate com vários itens,
    quais são, com o número de cada um (ou só o nome, quando o número não está à vista)."""
    _, invalidos = escolher(texto, opcoes)
    bases = [_base(o) for o in opcoes]
    linhas = []
    for tok in invalidos:
        candidatos = [i for i, b in enumerate(bases) if tok in b]
        if len(candidatos) > 1:
            opc = "\n".join(f"   {f'{i + 1}.' if numerar else '•'} {opcoes[i]}" for i in candidatos[:8])
            linhas.append(f'• "{tok.lower()}" combina com mais de uma opção:\n{opc}')
        else:
            linhas.append(f'• "{tok.lower()}" não está na lista')
    return "\n".join(linhas)


def normalizar_servicos(texto: str) -> str | None:
    escolhidos, invalidos = escolher(texto, SERVICOS)
    if invalidos or not escolhidos:
        return None
    return "; ".join(escolhidos)


def normalizar_estados_atendidos(texto: str) -> str | None:
    if _base(texto).strip(" .!") in _TODOS:
        return ", ".join(ESTADOS_ATENDIDOS)
    # "DF" ou "GO" sozinhos valem pela regional DF/GO; siglas são aceitas além dos números.
    trocado = re.sub(r"\s+E\s+", ", ", _base(texto))  # "MG e SP"
    trocado = re.sub(r"\b(DF|GO)\b", "DF/GO", trocado)
    trocado = re.sub(r"DF/GO(\s*[/,E ]\s*DF/GO)+", "DF/GO", trocado)
    # Siglas separadas só por espaço ("MG SP") viram lista.
    if re.fullmatch(r"[A-Z/]+(\s+[A-Z/]+)+", trocado.strip()):
        trocado = ", ".join(trocado.split())
    escolhidos, invalidos = escolher(trocado, ESTADOS_ATENDIDOS)
    if invalidos or not escolhidos:
        return None
    return ", ".join(escolhidos)
