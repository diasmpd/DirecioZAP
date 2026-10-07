from datetime import datetime, timedelta, timezone
from io import BytesIO

from openpyxl import Workbook

# Brasília não tem horário de verão desde 2019 — offset fixo evita depender do tzdata no Windows.
_FUSO_BRASILIA = timezone(timedelta(hours=-3))


def _formatar_data(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_FUSO_BRASILIA).strftime("%Y-%m-%d %H:%M:%S")


def gerar_excel(cadastros: list[dict], perguntas: list[dict]) -> bytes:
    """Gera a planilha a partir dos cadastros do Supabase (fonte única da verdade).

    As colunas seguem a ordem atual das perguntas. Perguntas inativas só entram se algum
    cadastro tiver o campo, e campos que não existem mais nas perguntas vão para o fim —
    assim nenhum dado histórico some da planilha quando o formulário muda.
    """
    campos_com_dados = {k for c in cadastros for k in (c.get("dados") or {})}

    colunas: list[tuple[str, str]] = []  # (campo, cabeçalho)
    vistos = set()
    for p in sorted(perguntas, key=lambda p: p.get("ordem", 0)):
        campo = p["campo"]
        if campo in vistos:
            continue
        if p.get("ativo", True) or campo in campos_com_dados:
            colunas.append((campo, p.get("label") or campo))
            vistos.add(campo)
    for campo in sorted(campos_com_dados - vistos):
        colunas.append((campo, campo))

    wb = Workbook()
    ws = wb.active
    ws.title = "Cadastros"
    ws.append(["Telefone"] + [cab for _, cab in colunas] + ["Data Cadastro (Brasília)"])

    for c in sorted(cadastros, key=lambda c: c.get("criado_em") or ""):
        dados = c.get("dados") or {}
        ws.append(
            [c.get("phone", "")]
            + [dados.get(campo, "") for campo, _ in colunas]
            + [_formatar_data(c.get("criado_em"))]
        )

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
