"""Portal do Fornecedor (SISFOR) — cadastro do fornecedor lá a partir do cadastro do bot.

O formulário do Portal (/Fornecedor/Cadastrar) pede Nome/Empresa, CNPJ, E-mail, Telefone,
Estado, Cidade, Segmentos e Produtos (até 5 categorias). O bot já tem quase tudo; o e-mail é
pedido depois da confirmação do cadastro, numa mensagem só, e pode ser pulado.

O envio roda no PC (avisos_pc.py), não no webhook: é um efeito externo que não dá para
desfazer daqui, e fica junto com os avisos por e-mail, num lugar só. Regras (out/2026):
- só vai sozinho se todos os serviços têm categoria de confiança "alta" no mapa
  (data/portal_mapa_servicos.csv), dá no máximo 5 categorias e a Receita trouxe UF e cidade;
- qualquer outra coisa fica "revisar" com o motivo, para o Manager (aba Portal) aprovar;
- antes de enviar, o CNPJ é conferido no Portal: se já existe, nada é enviado.
Cada cadastro guarda o status, o motivo/resposta e o que foi enviado (auditoria).
"""
import csv
import re
import unicodedata
from pathlib import Path

URL = "https://fornecedor.direcional.com.br/"

# Campo extra gravado no cadastro (não é pergunta): aparece no Excel e no e-mail de aviso.
CAMPO_EMAIL = "email_portal"
LABEL_EMAIL = "E-mail (Portal)"

_EMAIL = re.compile(r"^[\w.+-]+@([\w-]+\.)+[a-z]{2,}$", re.IGNORECASE)

MAPA_CSV = Path(__file__).resolve().parent / "data" / "portal_mapa_servicos.csv"
MAX_CATEGORIAS = 5
SEGMENTOS = {"SERVICOS": "1", "LOCACOES": "2", "MATERIAIS": "3"}
# "Como soube do SISFOR?": 6 = Outros, com o texto abaixo — identifica no SISFOR o que veio do bot.
SOUBE_OUTROS = "6"
ORIGEM = "WhatsApp DirecioZAP"

# Status gravados em cadastros.portal_status (NULL = ainda não processado).
ENVIADO = "enviado"
JA_CADASTRADO = "ja_cadastrado"
REVISAR = "revisar"
ERRO = "erro"
DESCARTADO = "descartado"


def normalizar_email(texto: str) -> str | None:
    """O e-mail em minúsculas, ou None. Aceita o e-mail no meio de uma frase curta
    ("é o compras@empresa.com.br")."""
    for palavra in (texto or "").replace(",", " ").replace(";", " ").split():
        palavra = palavra.strip(".:()<>*\"'")
        if _EMAIL.match(palavra):
            return palavra.lower()
    return None


def _base(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.upper().split())


# ── Mapa serviço do bot → segmento/categorias do Portal ──────────

def carregar_mapa(caminho: Path = MAPA_CSV) -> dict[str, dict]:
    """{serviço normalizado: {segmento, codigos, confianca}}. O CSV é editado no Excel
    (separador ";"), por isso aceita BOM e linhas com colunas vazias."""
    mapa = {}
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            servico = (linha.get("servico_bot") or "").strip()
            if not servico:
                continue
            mapa[_base(servico)] = {
                "segmento": SEGMENTOS.get(_base(linha.get("segmento", "")), ""),
                "codigos": re.findall(r"\d+", linha.get("codigos_categoria") or ""),
                "confianca": _base(linha.get("confianca", "")).lower(),
            }
    return mapa


# ── Montagem do envio ─────────────────────────────────────────

def formatar_cnpj(cnpj: str) -> str | None:
    """Máscara do Portal (00.000.000/0000-00). None se não forem 14 dígitos — o Portal ainda
    não aceita o CNPJ alfanumérico."""
    d = re.sub(r"\D", "", cnpj or "")
    if len(d) != 14 or re.search(r"[A-Za-z]", cnpj or ""):
        return None
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def formatar_telefone(phone: str) -> str | None:
    """WhatsApp gravado (55 + DDD + número) na máscara do Portal: (31) 99999-9999."""
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return None


def _servicos(dados: dict) -> list[str]:
    return [s.strip() for s in (dados.get("servico") or "").split(";") if s.strip()]


def montar_envio(phone: str, dados: dict, criado_em: str, mapa: dict) -> tuple[dict, list[str]]:
    """(campos do formulário, motivos para revisão). Sem motivos = pode ir sozinho.
    Os campos saem montados mesmo com motivos, para o Manager mostrar e aprovar."""
    motivos = []
    segmentos, categorias = [], []
    for servico in _servicos(dados):
        item = mapa.get(_base(servico))
        if not item or not item["codigos"]:
            motivos.append(f"Serviço sem categoria no mapa: {servico}")
            continue
        if item["confianca"] != "alta":
            motivos.append(f"Categoria de confiança {item['confianca'] or 'não informada'}: {servico}")
        for lista, valores in ((segmentos, [item["segmento"]]), (categorias, item["codigos"])):
            lista.extend(v for v in valores if v and v not in lista)
    if not categorias and not motivos:
        motivos.append("Nenhum serviço no cadastro")
    if len(categorias) > MAX_CATEGORIAS:
        motivos.append(f"{len(categorias)} categorias; o Portal aceita até {MAX_CATEGORIAS} — escolha quais")

    cnpj = formatar_cnpj(dados.get("cnpj", ""))
    if not cnpj:
        motivos.append(f"CNPJ fora do formato do Portal: {dados.get('cnpj', '')}")
    telefone = formatar_telefone(phone)
    if not telefone:
        motivos.append(f"Telefone fora do formato do Portal: {phone}")
    situacao = dados.get("situacao_cnpj")
    if situacao and _base(situacao) != "ATIVA":
        motivos.append(f"CNPJ com situação {situacao} na Receita")
    uf = (dados.get("uf_receita") or "").strip().upper()
    cidade = re.sub(r"\d", "", dados.get("cidade_receita") or "").strip()
    if not uf or not cidade:
        motivos.append("Sem UF/cidade da Receita")
    email = normalizar_email(dados.get(CAMPO_EMAIL, ""))
    if not email:
        motivos.append("Sem e-mail para o Portal")

    data = (criado_em or "")[:10]
    mensagem = (
        f"Cadastro recebido pelo {ORIGEM} em {data}. "
        f"Serviços: {'; '.join(_servicos(dados))}. Regionais: {dados.get('estados', '')}."
    )
    campos = {
        "Nome": (dados.get("razao_social") or "").strip()[:150],
        "Identificador": cnpj or dados.get("cnpj", ""),
        "Email": email or "",
        "Telefone": telefone or "",
        "Estado": uf,
        "Cidade": cidade,
        "CodigosSegmento": segmentos,
        "CodigosCategoria": categorias,
        "Mensagem": mensagem,
        "CodigosSoubeSisfor": SOUBE_OUTROS,
        "Outro": ORIGEM,
    }
    return campos, motivos


def problemas_para_envio(campos: dict) -> list[str]:
    """O mínimo para o Portal aceitar — vale também para um envio aprovado no Manager."""
    falta = [n for n in ("Nome", "Identificador", "Email", "Telefone", "Estado", "Cidade") if not campos.get(n)]
    problemas = [f"Campo vazio: {', '.join(falta)}"] if falta else []
    if not formatar_cnpj(campos.get("Identificador", "")):
        problemas.append("CNPJ fora do formato do Portal")
    if not campos.get("CodigosSegmento"):
        problemas.append("Nenhum segmento")
    n = len(campos.get("CodigosCategoria") or [])
    if not 1 <= n <= MAX_CATEGORIAS:
        problemas.append(f"O Portal pede de 1 a {MAX_CATEGORIAS} categorias (há {n})")
    return problemas


# ── Cliente HTTP do Portal ────────────────────────────────────

class PortalErro(Exception):
    """O Portal recusou ou não respondeu como esperado."""


class PortalCliente:
    """Reproduz o que o navegador faz: confere o CNPJ, abre o formulário (cookie + token
    antifalsificação) e envia como multipart, igual ao FormData da página."""

    def __init__(self, base_url: str = URL, timeout: int = 30, session=None):
        import requests
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.http = session or requests.Session()
        self.http.headers["User-Agent"] = "DirecioZAP (Direcional Suprimentos)"

    def validar(self, cnpj: str) -> tuple[bool, int, str]:
        """(é novo?, tipo, mensagem do Portal). Só consulta — não grava nada."""
        r = self.http.post(f"{self.base}/Fornecedor/ValidarNovoFornecedor",
                           data={"cpf": cnpj}, timeout=self.timeout)
        r.raise_for_status()
        j = r.json()
        return j.get("codigo") == 0, int(j.get("tipo") or 0), str(j.get("retorno") or "")

    def enviar(self, campos: dict, tipo: int = 0) -> str:
        """Envia o cadastro; devolve a mensagem de sucesso do Portal ou levanta PortalErro."""
        url_form = f"{self.base}/Fornecedor/Cadastrar"
        r = self.http.get(url_form, params={"identificador": campos["Identificador"], "tipo": tipo},
                          timeout=self.timeout)
        r.raise_for_status()
        m = re.search(r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"', r.text)
        if not m:
            raise PortalErro("Formulário do Portal sem o token de segurança (a página mudou?)")
        partes = []
        for nome, valor in campos.items():
            for v in valor if isinstance(valor, list) else [valor]:
                partes.append((nome, (None, str(v))))
        partes.append(("__RequestVerificationToken", (None, m.group(1))))
        r = self.http.post(f"{self.base}/Fornecedor/EnviarFornecedor", files=partes,
                           headers={"X-Requested-With": "XMLHttpRequest", "Referer": r.url},
                           timeout=self.timeout)
        texto = _texto_resposta(r)
        if not r.ok:
            raise PortalErro(f"HTTP {r.status_code}: {texto}")
        return texto


def _texto_resposta(r) -> str:
    try:
        j = r.json()
        return j if isinstance(j, str) else str(j)
    except ValueError:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text or "")).strip()[:500]


# ── Processamento (chamado pelo avisos_pc.py e pelo Manager) ───

def enviar_um(db, cadastro: dict, campos: dict, cliente: PortalCliente) -> tuple[str, str]:
    """Confere o CNPJ e envia. Grava e devolve (status, detalhe). Erros de rede na
    conferência sobem sem gravar nada (tenta de novo na próxima vez)."""
    novo, tipo, retorno = cliente.validar(campos["Identificador"])
    if not novo:
        db.marcar_portal(cadastro["id"], JA_CADASTRADO, retorno, None)
        return JA_CADASTRADO, retorno
    try:
        resposta = cliente.enviar(campos, tipo)
    except Exception as ex:
        # Pode ter sido gravado mesmo assim (ex: tempo esgotado): um humano confere.
        db.marcar_portal(cadastro["id"], ERRO, str(ex)[:1000], campos)
        return ERRO, str(ex)
    db.marcar_portal(cadastro["id"], ENVIADO, resposta[:1000], campos)
    return ENVIADO, resposta


def processar_pendentes(db, modo: str, cliente: PortalCliente | None = None,
                        mapa: dict | None = None) -> list[dict]:
    """Cadastros com e-mail do Portal e ainda sem status. modo "auto": envia os que não têm
    motivo de revisão; "revisar": todos ficam para o Manager; outro valor: não faz nada.
    Devolve [{cadastro, status, detalhe}] do que foi processado."""
    modo = (modo or "").strip().lower()
    if modo not in ("auto", "revisar"):
        return []
    pendentes = db.get_cadastros_portal_pendentes()
    if not pendentes:
        return []
    mapa = mapa if mapa is not None else carregar_mapa()
    cliente = cliente or PortalCliente()
    resultados = []
    for c in pendentes:
        campos, motivos = montar_envio(c["phone"], c.get("dados") or {}, c.get("criado_em", ""), mapa)
        if modo == "revisar" and not motivos:
            motivos = ["Envio automático desligado (PORTAL_ENVIO=revisar)"]
        if motivos:
            # Mesmo para revisar, se o CNPJ já está no Portal não há o que aprovar.
            if formatar_cnpj((c.get("dados") or {}).get("cnpj", "")):
                novo, _, retorno = cliente.validar(campos["Identificador"])
                if not novo:
                    db.marcar_portal(c["id"], JA_CADASTRADO, retorno, None)
                    resultados.append({"cadastro": c, "status": JA_CADASTRADO, "detalhe": retorno})
                    continue
            detalhe = "; ".join(motivos)
            db.marcar_portal(c["id"], REVISAR, detalhe, campos)
            resultados.append({"cadastro": c, "status": REVISAR, "detalhe": detalhe})
            continue
        status, detalhe = enviar_um(db, c, campos, cliente)
        resultados.append({"cadastro": c, "status": status, "detalhe": detalhe})
    return resultados
