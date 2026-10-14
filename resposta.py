class Resposta(str):
    """Texto da resposta + elementos interativos opcionais do WhatsApp.

    É um str para o resto do código (e os testes) continuar tratando a resposta como texto;
    quem envia (whatsapp.py) usa `botoes` (até 3, título até 20 caracteres) ou `lista`
    (até 10 itens) quando o provedor suporta, e cai no texto puro quando não.
    O id de um botão/item volta no webhook como se o fornecedor tivesse digitado aquele texto.
    """

    def __new__(cls, texto: str, botoes=None, lista=None, lista_botao: str = "Escolher"):
        obj = super().__new__(cls, texto)
        obj.botoes = botoes or []          # [(id, título)]
        obj.lista = lista or []            # [(id, título)]
        obj.lista_botao = lista_botao
        return obj


def prefixar(prefixo: str, resposta: str) -> "Resposta":
    """Põe um texto antes da resposta sem perder os botões/lista dela."""
    if not prefixo:
        return resposta if isinstance(resposta, Resposta) else Resposta(resposta)
    return Resposta(
        f"{prefixo}\n\n{resposta}",
        botoes=getattr(resposta, "botoes", None),
        lista=getattr(resposta, "lista", None),
        lista_botao=getattr(resposta, "lista_botao", "Escolher"),
    )
