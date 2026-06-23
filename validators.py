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


def _calcular_digito_cnpj(digits: str, pesos: list[int]) -> int:
    soma = sum(int(digits[i]) * pesos[i] for i in range(len(pesos)))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def _validar_cnpj_digitos(digits: str) -> bool:
    if len(digits) != 14:
        return False
    if len(set(digits)) == 1:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if _calcular_digito_cnpj(digits, pesos1) != int(digits[12]):
        return False
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if _calcular_digito_cnpj(digits, pesos2) != int(digits[13]):
        return False
    return True


def normalizar_cnpj(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if not _validar_cnpj_digitos(digits):
        return None
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def normalizar_contato(raw: str) -> str | None:
    raw = raw.strip()

    email_pattern = r"^[\w.+-]+@([\w-]+\.)+[a-z]{2,}$"
    if re.match(email_pattern, raw, re.IGNORECASE):
        return raw.lower()

    digits = re.sub(r"\D", "", raw)
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

    tokens = re.split(r"[,;/\s]+", raw_upper)
    tokens = [t.strip() for t in tokens if t.strip()]

    if not tokens:
        return None

    invalidos = [t for t in tokens if t not in UFS_VALIDAS]
    if invalidos:
        return None

    return sorted(set(tokens))
