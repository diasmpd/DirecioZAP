"""Portal do Fornecedor (SISFOR) — o que o bot coleta para o cadastro do fornecedor lá.

O formulário do Portal (/Fornecedor/Cadastrar) pede Nome/Empresa, CNPJ, E-mail, Telefone,
Estado, Cidade, Segmentos e Produtos. O bot já tem quase tudo; o e-mail é pedido depois da
confirmação do cadastro, numa mensagem só, e pode ser pulado.
"""
import re

URL = "https://fornecedor.direcional.com.br/"

# Campo extra gravado no cadastro (não é pergunta): aparece no Excel e no e-mail de aviso.
CAMPO_EMAIL = "email_portal"
LABEL_EMAIL = "E-mail (Portal)"

_EMAIL = re.compile(r"^[\w.+-]+@([\w-]+\.)+[a-z]{2,}$", re.IGNORECASE)


def normalizar_email(texto: str) -> str | None:
    """O e-mail em minúsculas, ou None. Aceita o e-mail no meio de uma frase curta
    ("é o compras@empresa.com.br")."""
    for palavra in (texto or "").replace(",", " ").replace(";", " ").split():
        palavra = palavra.strip(".:()<>*\"'")
        if _EMAIL.match(palavra):
            return palavra.lower()
    return None
