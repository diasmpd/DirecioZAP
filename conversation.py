from datetime import datetime, timezone, timedelta

from excel_writer import append_fornecedor
from supabase_session import (
    create_session,
    delete_session,
    get_session,
    update_session,
)
from validators import (
    normalizar_cnpj,
    normalizar_contato,
    normalizar_estados,
    normalizar_razao_social,
    normalizar_servico,
)

MAX_TENTATIVAS = 3

MSGS = {
    "SAUDACAO": (
        "Olá! 👋 Seja bem-vindo ao cadastro de fornecedores. "
        "Vou precisar de algumas informações. "
        "Qual é a Razão Social da sua empresa?"
    ),
    "AGUARDA_CNPJ": "Obrigado! Agora me informe o CNPJ da empresa (pode ser com ou sem pontuação):",
    "CNPJ_INVALIDO": "⚠️ CNPJ inválido. Por favor, informe um CNPJ com 14 dígitos válidos:",
    "AGUARDA_CONTATO": "Ótimo! Qual o contato principal? (telefone ou e-mail):",
    "CONTATO_INVALIDO": (
        "⚠️ Formato não reconhecido. "
        "Informe um telefone (ex: 31999990000) ou e-mail válido:"
    ),
    "AGUARDA_SERVICO": "Que tipo de serviço sua empresa oferece?",
    "AGUARDA_ESTADOS": (
        "Em quais estados vocês atuam? "
        "(Ex: MG, SP, RJ — pode listar todos separados por vírgula):"
    ),
    "ESTADO_INVALIDO": (
        "⚠️ Algumas siglas não reconhecidas. "
        "Use as siglas oficiais dos estados brasileiros (ex: MG, SP, RJ):"
    ),
    "SUCESSO": "✅ Cadastro realizado com sucesso! Entraremos em contato em breve. Obrigado!",
    "REINICIO": "Ok, vamos começar de novo. Qual é a Razão Social da sua empresa?",
    "ERRO_SALVAR": "⚠️ Ocorreu um problema técnico ao salvar seu cadastro. Por favor, tente novamente mais tarde.",
    "MAX_TENTATIVAS": "❌ Muitas tentativas inválidas. Por favor, inicie uma nova conversa para tentar novamente.",
    "APENAS_TEXTO": "Por favor, responda apenas com texto.",
    "RAZAO_SOCIAL_INVALIDA": "Por favor, informe a Razão Social da sua empresa:",
    "SERVICO_INVALIDO": "Por favor, informe o serviço oferecido (mínimo 3 caracteres):",
    "CONFIRMACAO_INVALIDA": "Por favor, responda S para confirmar ou N para recomeçar.",
}


def _confirmar_resumo(dados: dict) -> str:
    return (
        "📋 Resumo do cadastro:\n\n"
        f"• Razão Social: {dados.get('razao_social', '')}\n"
        f"• CNPJ: {dados.get('cnpj', '')}\n"
        f"• Contato: {dados.get('contato', '')}\n"
        f"• Serviço: {dados.get('servico', '')}\n"
        f"• Estados: {dados.get('estados', '')}\n\n"
        "As informações estão corretas? Responda S para confirmar ou N para recomeçar."
    )


def _sessao_expirada(session: dict) -> bool:
    atualizado = session.get("atualizado_em", "")
    if not atualizado:
        return True
    try:
        ts = datetime.fromisoformat(atualizado.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - ts > timedelta(hours=24)
    except ValueError:
        return True


def _incrementar_tentativa(tentativas: dict, campo: str) -> int:
    tentativas[campo] = tentativas.get(campo, 0) + 1
    return tentativas[campo]


class ConversationManager:

    def process(self, phone: str, text: str) -> str:
        session = get_session(phone)

        if session is None or _sessao_expirada(session):
            if session:
                delete_session(phone)
            session = create_session(phone)

        state: str = session["state"]
        dados: dict = dict(session.get("dados") or {})
        tentativas: dict = dict(session.get("tentativas") or {})

        return self._handle(phone, text, state, dados, tentativas)

    def _handle(
        self,
        phone: str,
        text: str,
        state: str,
        dados: dict,
        tentativas: dict,
    ) -> str:

        if state == "SAUDACAO":
            update_session(phone, "AGUARDA_RAZAO_SOCIAL", dados, tentativas)
            return MSGS["SAUDACAO"]

        if state == "AGUARDA_RAZAO_SOCIAL":
            razao = normalizar_razao_social(text)
            if not razao:
                return MSGS["RAZAO_SOCIAL_INVALIDA"]
            dados["razao_social"] = razao
            update_session(phone, "AGUARDA_CNPJ", dados, tentativas)
            return MSGS["AGUARDA_CNPJ"]

        if state == "AGUARDA_CNPJ":
            cnpj = normalizar_cnpj(text)
            if not cnpj:
                n = _incrementar_tentativa(tentativas, "cnpj")
                if n >= MAX_TENTATIVAS:
                    delete_session(phone)
                    return MSGS["MAX_TENTATIVAS"]
                update_session(phone, "AGUARDA_CNPJ", dados, tentativas)
                return MSGS["CNPJ_INVALIDO"]
            tentativas.pop("cnpj", None)
            dados["cnpj"] = cnpj
            update_session(phone, "AGUARDA_CONTATO", dados, tentativas)
            return MSGS["AGUARDA_CONTATO"]

        if state == "AGUARDA_CONTATO":
            contato = normalizar_contato(text)
            if not contato:
                n = _incrementar_tentativa(tentativas, "contato")
                if n >= MAX_TENTATIVAS:
                    delete_session(phone)
                    return MSGS["MAX_TENTATIVAS"]
                update_session(phone, "AGUARDA_CONTATO", dados, tentativas)
                return MSGS["CONTATO_INVALIDO"]
            tentativas.pop("contato", None)
            dados["contato"] = contato
            update_session(phone, "AGUARDA_SERVICO", dados, tentativas)
            return MSGS["AGUARDA_SERVICO"]

        if state == "AGUARDA_SERVICO":
            servico = normalizar_servico(text)
            if not servico:
                return MSGS["SERVICO_INVALIDO"]
            dados["servico"] = servico
            update_session(phone, "AGUARDA_ESTADOS", dados, tentativas)
            return MSGS["AGUARDA_ESTADOS"]

        if state == "AGUARDA_ESTADOS":
            estados = normalizar_estados(text)
            if estados is None:
                n = _incrementar_tentativa(tentativas, "estados")
                if n >= MAX_TENTATIVAS:
                    delete_session(phone)
                    return MSGS["MAX_TENTATIVAS"]
                update_session(phone, "AGUARDA_ESTADOS", dados, tentativas)
                return MSGS["ESTADO_INVALIDO"]
            tentativas.pop("estados", None)
            dados["estados"] = ", ".join(estados)
            update_session(phone, "CONFIRMACAO", dados, tentativas)
            return _confirmar_resumo(dados)

        if state == "CONFIRMACAO":
            resp = text.strip().upper()
            if resp in {"S", "SIM", "YES", "Y"}:
                try:
                    append_fornecedor(dados)
                    delete_session(phone)
                    return MSGS["SUCESSO"]
                except Exception as exc:
                    print(f"[conversation] Erro ao salvar Excel: {exc}")
                    return MSGS["ERRO_SALVAR"]
            if resp in {"N", "NAO", "NÃO", "NO"}:
                delete_session(phone)
                create_session(phone)
                update_session(phone, "AGUARDA_RAZAO_SOCIAL", {}, {})
                return MSGS["REINICIO"]
            return f"{MSGS['CONFIRMACAO_INVALIDA']}\n\n{_confirmar_resumo(dados)}"

        # Fallback — estado desconhecido: reinicia sessão
        delete_session(phone)
        create_session(phone)
        update_session(phone, "AGUARDA_RAZAO_SOCIAL", {}, {})
        return MSGS["SAUDACAO"]
