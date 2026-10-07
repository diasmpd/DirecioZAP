from datetime import datetime, timezone, timedelta
import unicodedata

from supabase_session import (
    create_session,
    delete_session,
    get_perguntas,
    get_session,
    save_cadastro,
    update_session,
)
from validators import normalizar_cnpj, normalizar_contato, normalizar_estados

MAX_TENTATIVAS = 3

MSGS = {
    "SAUDACAO": "Olá! Seja bem-vindo(a) ao cadastro de fornecedores da Direcional.",
    "SUCESSO": "Cadastro realizado com sucesso! Caso a obra precise de algum serviço, eles entram em contato com você.",
    "REINICIO": "Sem problemas, vamos recomeçar.",
    "ERRO_TECNICO": "Tivemos um problema técnico ao processar sua mensagem. Por favor, envie novamente em alguns minutos.",
    "ERRO_SALVAR": "Ocorreu um problema técnico ao salvar. Por favor, tente novamente mais tarde.",
    "MAX_TENTATIVAS": "Muitas tentativas inválidas. Envie uma mensagem para recomeçar.",
    "APENAS_TEXTO": "Por favor, responda apenas com texto.",
    "SEM_CONFIG": "Bot sem perguntas configuradas. Entre em contato com o administrador.",
    "CONFIRMACAO_INVALIDA": "Por favor, responda S para confirmar ou N para recomeçar.",
    "CANCELADO": "Tudo bem! Encerramos por aqui. Quando quiser retomar, é só enviar uma mensagem.",
    "AJUDA_GERAL": (
        "Posso te ajudar\n"
        "• Digite AJUDA para receber exemplos de resposta\n"
        "• Digite VOLTAR para corrigir a pergunta anterior\n"
        "• Digite RECOMEÇAR para iniciar do zero\n"
        "• Digite CANCELAR para encerrar"
    ),
}

# Comandos só valem quando a resposta inteira é o comando — assim uma resposta real
# como "Consultoria e ajuda técnica" não é confundida com um pedido de AJUDA.
_INTENT_AJUDA = {"AJUDA", "HELP", "DUVIDA", "DUVIDAS", "SOCORRO", "NAO ENTENDI"}
_INTENT_REINICIAR = {"RECOMECAR", "REINICIAR", "COMECAR DE NOVO", "INICIAR DE NOVO"}
_INTENT_CANCELAR = {"CANCELAR", "PARAR", "SAIR", "ENCERRAR", "DESISTIR"}
_INTENT_VOLTAR = {"VOLTAR", "VOLTA"}
_VERBOS_ALTERAR = {"ALTERAR", "MUDAR", "EDITAR", "CORRIGIR"}


def _texto_base(text: str) -> str:
    limpo = (text or "").strip()
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", limpo) if unicodedata.category(ch) != "Mn"
    )
    return " ".join(sem_acento.upper().split())


def _detectar_intencao(text: str) -> str | None:
    base = _texto_base(text)
    if not base:
        return None

    if base in _INTENT_VOLTAR:
        return "VOLTAR"
    if base.split()[0] in _VERBOS_ALTERAR:
        return "ALTERAR"
    if base in _INTENT_CANCELAR:
        return "CANCELAR"
    if base in _INTENT_REINICIAR:
        return "REINICIAR"
    if base in _INTENT_AJUDA:
        return "AJUDA"

    return None


def _mensagem_ajuda(tipo: str) -> str:
    tipo = (tipo or "texto").lower()
    if tipo == "cnpj":
        return "Exemplo de CNPJ válido: 11.222.333/0001-81"
    if tipo == "contato":
        return "Você pode enviar telefone (31) 99999-0000 ou e-mail contato@empresa.com"
    if tipo == "telefone":
        return "Exemplo de telefone: (31) 99999-0000"
    if tipo == "email":
        return "Exemplo de e-mail: contato@empresa.com"
    if tipo == "estados":
        return "Exemplo: MG, SP, RJ"
    return "Responda com um texto curto e direto."


_ALIASES_CAMPO = {
    "RAZAO": "razao_social",
    "SOCIAL": "razao_social",
    "NOME": "razao_social",
    "CNPJ": "cnpj",
    "CONTATO": "contato",
    "TELEFONE": "contato",
    "EMAIL": "contato",
    "E-MAIL": "contato",
    "SERVICO": "servico",
    "SERVICOS": "servico",
    "ESTADO": "estados",
    "ESTADOS": "estados",
    "UF": "estados",
}


def _campo_por_alteracao(text: str, perguntas: list[dict]) -> str | None:
    """Identifica o campo em 'ALTERAR <campo>'. Só retorna campos que existem nas perguntas."""
    palavras = _texto_base(text).split()[1:]
    if not palavras:
        return None
    resto = " ".join(palavras)

    for p in perguntas:
        campo_base = _texto_base(p.get("campo", "")).replace("_", " ")
        label_base = _texto_base(p.get("label", ""))
        if resto in {campo_base, label_base}:
            return p["campo"]

    campos_existentes = {p["campo"] for p in perguntas}
    for palavra in palavras:
        campo = _ALIASES_CAMPO.get(palavra)
        if campo in campos_existentes:
            return campo
    return None


def _validar(text: str, tipo: str):
    tipo = (tipo or "texto").lower()
    if tipo == "cnpj":
        return normalizar_cnpj(text)
    if tipo == "email":
        c = normalizar_contato(text)
        return c if c and "@" in c else None
    if tipo == "telefone":
        c = normalizar_contato(text)
        return c if c and "@" not in c else None
    if tipo == "contato":
        return normalizar_contato(text)
    if tipo == "estados":
        result = normalizar_estados(text)
        return ", ".join(result) if result else None
    # tipo "texto" — qualquer string não-vazia
    return text.strip() if text.strip() else None


def _gerar_resumo(dados: dict, perguntas: list[dict]) -> str:
    linhas = ["Resumo do cadastro:\n"]
    for p in perguntas:
        label = p.get("label") or p["campo"]
        linhas.append(f"• {label}: {dados.get(p['campo'], '')}")
    linhas.append(
        "\nAs informações estão corretas? Responda S para confirmar ou N para recomeçar."
        "\nSe preferir, você também pode digitar: ALTERAR CNPJ, ALTERAR CONTATO, ALTERAR SERVIÇO..."
    )
    return "\n".join(linhas)


def _sessao_expirada(session: dict) -> bool:
    atualizado = session.get("atualizado_em", "")
    if not atualizado:
        return True
    try:
        ts = datetime.fromisoformat(atualizado.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - ts > timedelta(hours=24)
    except ValueError:
        return True


class ConversationManager:

    def process(self, phone: str, text: str) -> str:
        perguntas = get_perguntas()
        if not perguntas:
            return MSGS["SEM_CONFIG"]

        session = get_session(phone)
        if session is None or _sessao_expirada(session):
            if session:
                delete_session(phone)
            session = create_session(phone)

        state = session["state"]
        dados = dict(session.get("dados") or {})
        tentativas = dict(session.get("tentativas") or {})

        return self._handle(phone, text, state, dados, tentativas, perguntas)

    def _handle(self, phone, text, state, dados, tentativas, perguntas):
        primeira = perguntas[0]
        intencao = _detectar_intencao(text)

        if intencao == "CANCELAR":
            delete_session(phone)
            return MSGS["CANCELADO"]

        if intencao == "REINICIAR":
            delete_session(phone)
            create_session(phone)
            update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
            return f"{MSGS['REINICIO']}\n\n{primeira['pergunta']}"

        if intencao == "AJUDA" and state == "SAUDACAO":
            update_session(phone, f"AGUARDA_{primeira['campo']}", dados, tentativas)
            return f"{MSGS['AJUDA_GERAL']}\n\n{primeira['pergunta']}"

        if state == "SAUDACAO":
            update_session(phone, f"AGUARDA_{primeira['campo']}", dados, tentativas)
            return f"{MSGS['SAUDACAO']}\nVou te guiar rapidinho no cadastro.\n\n{primeira['pergunta']}"

        if state.startswith(("AGUARDA_", "ALTERA_")):
            # ALTERA_<campo>: correção de um único campo pedida no resumo; ao responder,
            # volta direto para a confirmação sem mexer nos demais campos.
            alterando = state.startswith("ALTERA_")
            campo = state.split("_", 1)[1]
            pergunta_cfg = next((p for p in perguntas if p["campo"] == campo), None)

            if pergunta_cfg is None:
                delete_session(phone)
                create_session(phone)
                update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
                return f"{MSGS['SAUDACAO']}\n\n{primeira['pergunta']}"

            if intencao == "AJUDA":
                return f"{_mensagem_ajuda(pergunta_cfg['tipo'])}\n\n{pergunta_cfg['pergunta']}"

            if intencao == "VOLTAR" and alterando:
                tentativas.pop(campo, None)
                update_session(phone, "CONFIRMACAO", dados, tentativas)
                return f"Ok, mantivemos o valor anterior.\n\n{_gerar_resumo(dados, perguntas)}"

            if intencao == "VOLTAR":
                idx = next(i for i, p in enumerate(perguntas) if p["campo"] == campo)
                if idx == 0:
                    return f"Você está na primeira pergunta.\n\n{pergunta_cfg['pergunta']}"

                destino = perguntas[idx - 1]
                limpar = [p["campo"] for p in perguntas[idx - 1:]]
                for c in limpar:
                    dados.pop(c, None)
                    tentativas.pop(c, None)

                update_session(phone, f"AGUARDA_{destino['campo']}", dados, tentativas)
                return f"Sem problemas, vamos corrigir juntos.\n\n{destino['pergunta']}"

            valor = _validar(text, pergunta_cfg["tipo"])
            if valor is None:
                n = tentativas.get(campo, 0) + 1
                tentativas[campo] = n
                if n >= MAX_TENTATIVAS and alterando:
                    tentativas.pop(campo, None)
                    update_session(phone, "CONFIRMACAO", dados, tentativas)
                    return (
                        "Muitas tentativas inválidas. Mantivemos o valor anterior.\n\n"
                        f"{_gerar_resumo(dados, perguntas)}"
                    )
                if n >= MAX_TENTATIVAS:
                    delete_session(phone)
                    return MSGS["MAX_TENTATIVAS"]
                update_session(phone, state, dados, tentativas)
                erro = pergunta_cfg.get("msg_erro") or pergunta_cfg["pergunta"]
                return f"{erro}\n\nDica: {_mensagem_ajuda(pergunta_cfg['tipo'])}"

            tentativas.pop(campo, None)
            dados[campo] = valor

            if alterando:
                update_session(phone, "CONFIRMACAO", dados, tentativas)
                return f"Pronto, atualizado.\n\n{_gerar_resumo(dados, perguntas)}"

            idx = next(i for i, p in enumerate(perguntas) if p["campo"] == campo)
            if idx + 1 < len(perguntas):
                proxima = perguntas[idx + 1]
                update_session(phone, f"AGUARDA_{proxima['campo']}", dados, tentativas)
                return proxima["pergunta"]

            update_session(phone, "CONFIRMACAO", dados, tentativas)
            return _gerar_resumo(dados, perguntas)

        if state == "CONFIRMACAO":
            resp = text.strip().upper()

            if intencao == "AJUDA":
                return (
                    "Você pode responder de três formas:\n"
                    "• S para confirmar\n"
                    "• N para recomeçar\n"
                    "• ALTERAR + nome do campo (ex: ALTERAR CNPJ)\n\n"
                    f"{_gerar_resumo(dados, perguntas)}"
                )

            if intencao == "ALTERAR":
                campo_alvo = _campo_por_alteracao(text, perguntas)
                if campo_alvo:
                    pergunta_alvo = next(p for p in perguntas if p["campo"] == campo_alvo)
                    tentativas.pop(campo_alvo, None)
                    update_session(phone, f"ALTERA_{campo_alvo}", dados, tentativas)
                    label = pergunta_alvo.get("label") or campo_alvo
                    return (
                        "Perfeito, vamos ajustar só esse ponto.\n"
                        f"{label} atual: {dados.get(campo_alvo, '')}\n"
                        "(Digite VOLTAR para manter o valor atual.)\n\n"
                        f"{pergunta_alvo['pergunta']}"
                    )

                return (
                    "Não identifiquei qual campo você quer alterar.\n"
                    "Tente algo como: ALTERAR CNPJ, ALTERAR CONTATO ou ALTERAR ESTADOS."
                )

            if resp in {"S", "SIM", "YES", "Y"}:
                try:
                    save_cadastro(phone, dados)
                except Exception as exc:
                    print(f"[conversation] Erro ao salvar cadastro de {phone}: {exc!r}")
                    return MSGS["ERRO_SALVAR"]
                # O cadastro já está salvo: uma falha daqui em diante não pode levar o
                # fornecedor a confirmar de novo (o que duplicaria o registro).
                try:
                    delete_session(phone)
                except Exception as exc:
                    print(f"[conversation] Cadastro salvo, mas falhou ao encerrar sessão de {phone}: {exc!r}")
                return MSGS["SUCESSO"]
            if resp in {"N", "NAO", "NÃO", "NO"}:
                delete_session(phone)
                create_session(phone)
                update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
                return f"{MSGS['REINICIO']}\n\n{primeira['pergunta']}"
            return (
                f"{MSGS['CONFIRMACAO_INVALIDA']}\n"
                "Você também pode digitar ALTERAR + campo (ex: ALTERAR CNPJ).\n\n"
                f"{_gerar_resumo(dados, perguntas)}"
            )

        # fallback — estado desconhecido
        delete_session(phone)
        create_session(phone)
        update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
        return f"{MSGS['SAUDACAO']}\n\n{primeira['pergunta']}"
