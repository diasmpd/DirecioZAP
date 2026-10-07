import re

UFS_VALIDAS = {
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
}

TERMOS_NACIONAL = {"NACIONAL", "TODO O BRASIL", "BRASIL", "TODOS", "TODO BRASIL"}


def normalizar_razao_social(raw: str) -> str | None:
    if not raw or not raw.strip():
        return None
    return re.sub(r"\s+", " ", raw.strip()).upper()


# CNPJ alfanumérico (IN RFB 2.229/2024, emitido desde jul/2026): as 12 primeiras posições
# podem ter letras A-Z; os 2 dígitos verificadores continuam numéricos. No cálculo do DV,
# cada caractere vale ord(c) - 48 (dígitos mantêm o valor; A=17, B=18, ...). Os CNPJs
# numéricos antigos são um caso particular, então a mesma regra valida os dois formatos.
_CNPJ_FORMATO = re.compile(r"^[A-Z0-9]{12}[0-9]{2}$")


def _calcular_digito_cnpj(base: str, pesos: list[int]) -> int:
    soma = sum((ord(base[i]) - 48) * pesos[i] for i in range(len(pesos)))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _validar_cnpj(cnpj: str) -> bool:
    if not _CNPJ_FORMATO.match(cnpj):
        return False
    if len(set(cnpj)) == 1:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if _calcular_digito_cnpj(cnpj, pesos1) != int(cnpj[12]):
        return False
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if _calcular_digito_cnpj(cnpj, pesos2) != int(cnpj[13]):
        return False
    return True


def normalizar_cnpj(raw: str) -> str | None:
    texto = (raw or "").upper().strip()
    texto = re.sub(r"^CNPJ\s*:?", "", texto)  # "CNPJ: 11.222..." — prefixo comum na resposta
    cnpj = re.sub(r"[^A-Z0-9]", "", texto)
    if not _validar_cnpj(cnpj):
        return None
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def normalizar_contato(raw: str) -> str | None:
    raw = raw.strip()

    email_pattern = r"^[\w.+-]+@([\w-]+\.)+[a-z]{2,}$"
    if re.match(email_pattern, raw, re.IGNORECASE):
        return raw.lower()

    digits = re.sub(r"\D", "", raw)
    # +55 (código do país) e 0 (prefixo de longa distância) não fazem parte do número.
    # Só removemos quando sobram dígitos demais — "55 9xxxx-xxxx" com 11 dígitos é DDD 55 (RS).
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]
    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"

    return None


def normalizar_servico(raw: str) -> str | None:
    if not raw or len(raw.strip()) < 3:
        return None
    return raw.strip().title()


def normalizar_estados(raw: str) -> list[str] | None:
    raw_upper = raw.upper().strip()

    if raw_upper in TERMOS_NACIONAL:
        return ["NACIONAL"]

    tokens = re.split(r"[,;/.\-\s]+", raw_upper)
    # "MG e SP": o "E" é conector, não sigla (não existe UF "E").
    tokens = [t.strip() for t in tokens if t.strip() and t.strip() != "E"]

    if not tokens:
        return None

    invalidos = [t for t in tokens if t not in UFS_VALIDAS]
    if invalidos:
        return None

    return sorted(set(tokens))
