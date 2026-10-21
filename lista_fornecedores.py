"""LISTA_FORNECEDORES.xlsm — inclusão dos fornecedores do bot na lista da área de Suprimentos.

Cada cadastro novo vira uma linha da tabela "Tabela1" (aba Detalhado), no mesmo formato das
linhas digitadas à mão: Qualificado, avaliação 1, data do cadastro, UF da sede (Receita),
regionais, razão social, CNPJ só com dígitos (assim a coluna Tipo calcula "CNPJ"), serviços
como códigos da aba Legenda ("13.1|14.2"), telefones, e-mail e prospectado = Sim.

Regras (out/2026):
- se o CNPJ já está na lista com "Fornecedor prospectado" = Sim, nada é gravado;
  se está só como Não, entra uma linha nova com Sim (as linhas existentes não são alteradas);
- só entra sozinho se a Receita disse ATIVA, há UF da sede e todos os serviços têm código
  na Legenda; qualquer outra coisa fica "revisar", para o Manager (aba Lista) aprovar;
- espera o e-mail do Portal (pedido depois da confirmação) ou 1 h, para a linha sair completa.

A gravação é feita pelo próprio Excel (COM), não pelo openpyxl: o arquivo tem macros, conexões
e a tabela formatada, que o openpyxl regravaria do zero. Se o arquivo está aberto por alguém,
nada é feito e tenta-se de novo na próxima execução. Antes de salvar, uma cópia vai para Base\\.
Cada cadastro guarda o status, o motivo e a linha gravada (auditoria).
"""
import re
import shutil
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import portal
from log_setup import get_logger

log = get_logger("lista_fornecedores")

CAMINHO_PADRAO = r"T:\SUPRIMENTOS\SuprimentosCorporativo\ControleSuprimentos\BI\FORNECEDORES\LISTA_FORNECEDORES.xlsm"
ABA = "Detalhado"
TABELA = "Tabela1"
ABA_LEGENDA = "Legenda"
BACKUPS_MANTIDOS = 30

# Cabeçalhos da Tabela1, na ordem. Conferidos a cada abertura: se alguém mudar a tabela, nada
# é gravado em coluna errada.
COLUNAS = [
    "Qualificado", "Avaliação Interna", "Data de cadastro", "UF (Corrigido)", "Local De Atuação",
    "Empresa - Razão Social (Corrigido)", "Tipo", "Cpf/Cnpj (Corrigido)", "Cnpj Correto?",
    "Legenda", "Celular Final", "Fixo", "Email", "Contratos No Uau", "Contratos Concluídos",
    "Fornecedor prospectado",
]
COL_CNPJ = "Cpf/Cnpj (Corrigido)"
COL_LEGENDA = "Legenda"
COL_PROSPECTADO = "Fornecedor prospectado"
# Coluna calculada da tabela: o Excel preenche sozinho.
_CALCULADAS = {"Tipo"}
# Texto que o Excel converteria em número ("10.10" -> 10,1; CNPJ perde o zero à esquerda).
COLUNAS_TEXTO = {COL_CNPJ, COL_LEGENDA, "Celular Final", "Fixo"}

# Status gravados em cadastros.lista_status (NULL = ainda não processado).
INSERIDO = "inserido"
JA_PROSPECTADO = "ja_prospectado"
REVISAR = "revisar"
ERRO = "erro"
DESCARTADO = "descartado"
ANTERIOR = "anterior"  # já existia quando a inclusão automática começou

# Nomes do bot (opcoes.SERVICOS) que a aba Legenda escreve diferente.
_APELIDOS = {
    "SUBESTACAO DEFINITIVA / ENTRADA DE ENERGIA DEFINITIVA":
        "SUBSESTACAO DEFINITIVA / ENTRADA DE ENERGIA DEFINITIVA",
}

_FUSO_BRASILIA = timezone(timedelta(hours=-3))


class PlanilhaOcupada(Exception):
    """O arquivo está aberto por alguém: tenta de novo na próxima execução."""


def _base(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.upper().split())


def digitos(cnpj) -> str:
    return re.sub(r"\D", "", str(cnpj or ""))


def caminho_lista(valor: str | None = None) -> str:
    return (valor or "").strip() or CAMINHO_PADRAO


# ── Montagem da linha ─────────────────────────────────────────

def servicos(dados: dict) -> list[str]:
    return [s.strip() for s in (dados.get("servico") or "").split(";") if s.strip()]


def codigos_legenda(dados: dict, legenda: dict[str, str]) -> tuple[list[str], list[str]]:
    """(códigos na ordem da Legenda, serviços sem código). legenda = {nome normalizado: código}."""
    ordem = {cod: i for i, cod in enumerate(legenda.values())}
    codigos, faltando = [], []
    for s in servicos(dados):
        cod = legenda.get(_base(s)) or legenda.get(_APELIDOS.get(_base(s), ""))
        if cod:
            if cod not in codigos:
                codigos.append(cod)
        else:
            faltando.append(s)
    return sorted(codigos, key=lambda c: ordem.get(c, len(ordem))), faltando


def _regionais(estados: str) -> str:
    """"MG, DF/GO" -> "MG, DF, GO" (a lista usa UFs soltas)."""
    ufs = []
    for parte in re.split(r"[,;/\s]+", estados or ""):
        parte = parte.strip().upper()
        if parte and parte not in ufs:
            ufs.append(parte)
    return ", ".join(ufs)


def _telefones(phone: str, contato: str) -> tuple[str, str]:
    """(celulares, fixos) no formato da lista, vários separados por "|". O WhatsApp é celular;
    o Contato entra também se for outro número."""
    celulares, fixos = [], []
    for numero in (phone, contato):
        tel = portal.formatar_telefone(numero) if not portal.normalizar_email(numero) else None
        if not tel:
            continue
        destino = celulares if len(digitos(tel)) == 11 else fixos
        if tel not in destino:
            destino.append(tel)
    return "|".join(celulares), "|".join(fixos)


def _data_cadastro(criado_em: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat((criado_em or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_FUSO_BRASILIA).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _cnpj_correto(situacao: str | None) -> str:
    if _base(situacao) == "ATIVA":
        return "Correto"
    return "N/A" if situacao else "Erro na consulta"


def montar_linha(phone: str, dados: dict, criado_em: str, legenda: dict[str, str],
                 codigos: list[str] | None = None) -> tuple[dict, list[str]]:
    """(valores por coluna, motivos para revisão). Sem motivos = pode entrar sozinho.
    codigos substitui os códigos calculados (aprovação no Manager)."""
    motivos = []
    if codigos is None:
        codigos, faltando = codigos_legenda(dados, legenda)
        motivos += [f"Serviço sem código na Legenda: {s}" for s in faltando]
    if not codigos and not motivos:
        motivos.append("Nenhum serviço no cadastro")

    cnpj = digitos(dados.get("cnpj"))
    if len(cnpj) != 14 or re.search(r"[A-Za-z]", dados.get("cnpj") or ""):
        motivos.append(f"CNPJ fora do formato da lista: {dados.get('cnpj', '')}")
    situacao = dados.get("situacao_cnpj")
    if _base(situacao) != "ATIVA":
        motivos.append(f"CNPJ com situação {situacao} na Receita" if situacao
                       else "CNPJ não consultado na Receita")
    uf = (dados.get("uf_receita") or "").strip().upper()
    if not uf:
        motivos.append("Sem UF da sede (Receita)")
    razao = " ".join((dados.get("razao_social") or "").upper().split())
    if not razao:
        motivos.append("Sem razão social")
    data = _data_cadastro(criado_em)
    celular, fixo = _telefones(phone, dados.get("contato", ""))
    email = (portal.normalizar_email(dados.get(portal.CAMPO_EMAIL, ""))
             or portal.normalizar_email(dados.get("contato", "")) or "")

    linha = {
        "Qualificado": "Qualificado",
        "Avaliação Interna": 1,
        "Data de cadastro": data.strftime("%Y-%m-%d") if data else "",
        "UF (Corrigido)": uf,
        "Local De Atuação": _regionais(dados.get("estados", "")),
        "Empresa - Razão Social (Corrigido)": razao,
        COL_CNPJ: cnpj,
        "Cnpj Correto?": _cnpj_correto(situacao),
        COL_LEGENDA: "|".join(codigos),
        "Celular Final": celular,
        "Fixo": fixo,
        "Email": email,
        COL_PROSPECTADO: "Sim",
    }
    return linha, motivos


# ── Planilha (Excel via COM) ──────────────────────────────────

def _arquivo_de_bloqueio(caminho: str) -> Path:
    p = Path(caminho)
    return p.with_name("~$" + p.name)


def fazer_backup(caminho: str, mantidos: int = BACKUPS_MANTIDOS) -> Path:
    """Copia o arquivo (como está no disco, antes de salvar) para Base\\ e apaga os mais antigos."""
    origem = Path(caminho)
    pasta = origem.parent / "Base"
    pasta.mkdir(exist_ok=True)
    destino = pasta / f"{origem.stem}_{datetime.now():%Y%m%d_%H%M%S}{origem.suffix}"
    shutil.copy2(origem, destino)
    antigos = sorted(pasta.glob(f"{origem.stem}_*{origem.suffix}"))
    for velho in antigos[:-mantidos]:
        try:
            velho.unlink()
        except OSError:
            log.warning("Não consegui apagar o backup antigo %s", velho)
    return destino


class PlanilhaExcel:
    """Abre o arquivo numa instância do Excel só nossa (invisível, macros desligadas, sem
    atualizar vínculos) e fecha sem salvar se algo der errado antes de salvar()."""

    def __init__(self, caminho: str):
        self.caminho = caminho
        self._xl = self._wb = self._lo = None

    def __enter__(self):
        if _arquivo_de_bloqueio(self.caminho).exists():
            raise PlanilhaOcupada(f"{Path(self.caminho).name} está aberto no Excel por alguém")
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            self._xl = win32com.client.DispatchEx("Excel.Application")
            self._xl.Visible = False
            self._xl.DisplayAlerts = False
            self._xl.AutomationSecurity = 3  # msoAutomationSecurityForceDisable: não roda macros
            self._wb = self._xl.Workbooks.Open(self.caminho, 0, False)  # UpdateLinks=0, ReadOnly=False
            if self._wb.ReadOnly:
                raise PlanilhaOcupada(f"{Path(self.caminho).name} abriu só para leitura (em uso por alguém)")
            self._lo = self._wb.Worksheets(ABA).ListObjects(TABELA)
            cabecalhos = [str(v or "").strip() for v in self._lo.HeaderRowRange.Value[0]]
            if cabecalhos != COLUNAS:
                raise RuntimeError(f"As colunas da {TABELA} mudaram; nada foi gravado. Agora: {cabecalhos}")
        except BaseException:
            self._fechar()
            raise
        return self

    def __exit__(self, *_):
        self._fechar()

    def _fechar(self):
        import pythoncom
        try:
            if self._wb is not None:
                self._wb.Close(False)
        finally:
            self._wb = self._lo = None
            if self._xl is not None:
                self._xl.Quit()
                self._xl = None
            pythoncom.CoUninitialize()

    def legenda(self) -> dict[str, str]:
        """{nome do serviço normalizado: código}, na ordem da aba Legenda (colunas B e C)."""
        ws = self._wb.Worksheets(ABA_LEGENDA)
        valores = ws.Range("B1", ws.Cells(ws.UsedRange.Row + ws.UsedRange.Rows.Count, 3)).Value
        legenda = {}
        for cod, nome in valores:
            cod = str(cod or "").strip()
            if re.fullmatch(r"\d+\.\d+", cod) and nome:
                legenda[_base(nome)] = cod
        return legenda

    def _corpo(self) -> list[tuple]:
        corpo = self._lo.DataBodyRange
        return list(corpo.Value) if corpo is not None else []

    def linhas_por_cnpj(self) -> dict[str, list[tuple[int, str]]]:
        """{CNPJ só dígitos: [(linha da planilha, prospectado)]}."""
        i_cnpj, i_prosp = COLUNAS.index(COL_CNPJ), COLUNAS.index(COL_PROSPECTADO)
        primeira = self._lo.HeaderRowRange.Row + 1
        indice = {}
        for n, valores in enumerate(self._corpo()):
            cnpj = digitos(valores[i_cnpj])
            if cnpj:
                indice.setdefault(cnpj.zfill(14), []).append((primeira + n, str(valores[i_prosp] or "").strip()))
        return indice

    def inserir(self, linha: dict) -> int:
        """Grava na primeira linha vazia do fim da tabela (ou numa nova) e devolve o número dela."""
        corpo = self._corpo()
        vazias = 0
        for valores in reversed(corpo):
            if any(str(v or "").strip() for c, v in zip(COLUNAS, valores) if c not in _CALCULADAS):
                break
            vazias += 1
        if vazias:
            n_tabela = len(corpo) - vazias + 1  # índice 1-based na tabela
        else:
            self._lo.ListRows.Add()
            n_tabela = len(corpo) + 1
        linha_excel = self._lo.ListRows(n_tabela).Range
        for i, coluna in enumerate(COLUNAS, start=1):
            if coluna in _CALCULADAS or coluna not in linha:
                continue
            celula = linha_excel.Cells(1, i)
            valor = linha[coluna]
            if coluna in COLUNAS_TEXTO:
                celula.NumberFormat = "@"
            if coluna == "Data de cadastro" and valor:
                valor = datetime.strptime(valor, "%Y-%m-%d")
            celula.Value = valor if valor != "" else None
        return linha_excel.Row

    def salvar(self) -> Path:
        backup = fazer_backup(self.caminho)
        self._wb.Save()
        return backup


# ── Processamento (chamado pelo avisos_pc.py e pelo Manager) ───

def _prospectado(indice: dict, cnpj: str) -> int | None:
    """Linha da planilha onde o CNPJ já está como prospectado = Sim, ou None."""
    for linha, prosp in indice.get(cnpj.zfill(14), []) if cnpj else []:
        if _base(prosp) == "SIM":
            return linha
    return None


def processar_pendentes(db, modo: str, caminho: str | None = None, planilha=PlanilhaExcel,
                        espera_min: int = 60) -> list[dict]:
    """Cadastros prontos e ainda sem status. modo "auto": grava os que não têm motivo de
    revisão; "revisar": todos ficam para o Manager; outro valor: não faz nada.
    Devolve [{cadastro, status, detalhe}] do que foi processado. Se a planilha está em uso,
    devolve [] sem marcar nada."""
    modo = (modo or "").strip().lower()
    if modo not in ("auto", "revisar"):
        return []
    db.preparar_lista()
    pendentes = db.get_cadastros_lista_pendentes(espera_min)
    if not pendentes:
        return []
    caminho = caminho_lista(caminho)
    resultados = []
    try:
        with planilha(caminho) as pl:
            legenda, indice = pl.legenda(), pl.linhas_por_cnpj()
            for c in pendentes:
                dados = c.get("dados") or {}
                linha, motivos = montar_linha(c["phone"], dados, c.get("criado_em", ""), legenda)
                cnpj = digitos(dados.get("cnpj"))
                ja = _prospectado(indice, cnpj)
                if ja:
                    resultados.append({"cadastro": c, "status": JA_PROSPECTADO, "envio": None,
                                       "detalhe": f"CNPJ já na lista como prospectado (linha {ja})"})
                    continue
                if modo == "revisar" and not motivos:
                    motivos = ["Inclusão automática desligada (LISTA_ENVIO=revisar)"]
                if motivos:
                    resultados.append({"cadastro": c, "status": REVISAR, "envio": linha,
                                       "detalhe": "; ".join(motivos)})
                    continue
                n = pl.inserir(linha)
                indice.setdefault(cnpj.zfill(14), []).append((n, "Sim"))
                resultados.append({"cadastro": c, "status": INSERIDO, "envio": {**linha, "_linha": n},
                                   "detalhe": f"Linha {n}"})
            if any(r["status"] == INSERIDO for r in resultados):
                backup = pl.salvar()
                log.info("Lista salva; cópia anterior em %s", backup)
    except PlanilhaOcupada as ex:
        log.info("Lista não atualizada agora: %s. Tento de novo na próxima execução.", ex)
        return []
    # Só depois de salvar: se o banco falhar aqui, na próxima vez o CNPJ já está na lista
    # como prospectado e o cadastro sai como "ja_prospectado", sem linha repetida.
    for r in resultados:
        db.marcar_lista(r["cadastro"]["id"], r["status"], r["detalhe"][:1000], r.pop("envio"))
    return resultados


def inserir_aprovado(db, cadastro: dict, codigos: list[str], caminho: str | None = None,
                     planilha=PlanilhaExcel) -> tuple[str, str]:
    """Aprovação no Manager: grava com os códigos escolhidos, mesmo com motivos de revisão.
    Levanta ValueError (nada gravado) se algum código não existe na Legenda;
    PlanilhaOcupada se o arquivo está em uso."""
    dados = cadastro.get("dados") or {}
    with planilha(caminho_lista(caminho)) as pl:
        legenda = pl.legenda()
        desconhecidos = [c for c in codigos if c not in set(legenda.values())]
        if desconhecidos:
            raise ValueError(f"Código(s) que a Legenda não tem: {', '.join(desconhecidos)}")
        if not codigos:
            raise ValueError("Informe ao menos um código da Legenda")
        cnpj = digitos(dados.get("cnpj"))
        ja = _prospectado(pl.linhas_por_cnpj(), cnpj)
        if ja:
            detalhe = f"CNPJ já na lista como prospectado (linha {ja})"
            db.marcar_lista(cadastro["id"], JA_PROSPECTADO, detalhe, None)
            return JA_PROSPECTADO, detalhe
        linha, _ = montar_linha(cadastro["phone"], dados, cadastro.get("criado_em", ""), legenda, codigos)
        n = pl.inserir(linha)
        pl.salvar()
    detalhe = f"Linha {n} (aprovado no Manager)"
    db.marcar_lista(cadastro["id"], INSERIDO, detalhe, {**linha, "_linha": n})
    return INSERIDO, detalhe
