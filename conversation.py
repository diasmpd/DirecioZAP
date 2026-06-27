from datetime import datetime, timezone, timedelta

from excel_writer import append_fornecedor
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
    "SAUDACAO": "Olá! 👋 Seja bem-vindo!",
    "SUCESSO": "✅ Cadastro realizado com sucesso! Entraremos em contato em breve. Obrigado!",
    "REINICIO": "Ok, vamos recomeçar.",
    "ERRO_SALVAR": "⚠️ Ocorreu um problema técnico ao salvar. Por favor, tente novamente mais tarde.",
    "MAX_TENTATIVAS": "❌ Muitas tentativas inválidas. Envie uma mensagem para recomeçar.",
    "APENAS_TEXTO": "Por favor, responda apenas com texto.",
    "SEM_CONFIG": "⚠️ Bot sem perguntas configuradas. Contate o administrador.",
    "CONFIRMACAO_INVALIDA": "Por favor, responda S para confirmar ou N para recomeçar.",
}


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
    linhas = ["📋 Resumo do cadastro:\n"]
    for p in perguntas:
        label = p.get("label") or p["campo"]
        linhas.append(f"• {label}: {dados.get(p['campo'], '')}")
    linhas.append("\nAs informações estão corretas? Responda S para confirmar ou N para recomeçar.")
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

        if state == "SAUDACAO":
            update_session(phone, f"AGUARDA_{primeira['campo']}", dados, tentativas)
            return f"{MSGS['SAUDACAO']}\n\n{primeira['pergunta']}"

        if state.startswith("AGUARDA_"):
            campo = state[len("AGUARDA_"):]
            pergunta_cfg = next((p for p in perguntas if p["campo"] == campo), None)

            if pergunta_cfg is None:
                delete_session(phone)
                create_session(phone)
                update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
                return f"{MSGS['SAUDACAO']}\n\n{primeira['pergunta']}"

            valor = _validar(text, pergunta_cfg["tipo"])
            if valor is None:
                n = tentativas.get(campo, 0) + 1
                tentativas[campo] = n
                if n >= MAX_TENTATIVAS:
                    delete_session(phone)
                    return MSGS["MAX_TENTATIVAS"]
                update_session(phone, state, dados, tentativas)
                return pergunta_cfg.get("msg_erro") or pergunta_cfg["pergunta"]

            tentativas.pop(campo, None)
            dados[campo] = valor

            idx = next(i for i, p in enumerate(perguntas) if p["campo"] == campo)
            if idx + 1 < len(perguntas):
                proxima = perguntas[idx + 1]
                update_session(phone, f"AGUARDA_{proxima['campo']}", dados, tentativas)
                return proxima["pergunta"]

            update_session(phone, "CONFIRMACAO", dados, tentativas)
            return _gerar_resumo(dados, perguntas)

        if state == "CONFIRMACAO":
            resp = text.strip().upper()
            if resp in {"S", "SIM", "YES", "Y"}:
                try:
                    save_cadastro(phone, dados)
                    append_fornecedor(phone, dados, perguntas)
                    delete_session(phone)
                    return MSGS["SUCESSO"]
                except Exception as exc:
                    print(f"[conversation] Erro ao salvar: {exc}")
                    return MSGS["ERRO_SALVAR"]
            if resp in {"N", "NAO", "NÃO", "NO"}:
                delete_session(phone)
                create_session(phone)
                update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
                return f"{MSGS['REINICIO']}\n\n{primeira['pergunta']}"
            return f"{MSGS['CONFIRMACAO_INVALIDA']}\n\n{_gerar_resumo(dados, perguntas)}"

        # fallback — estado desconhecido
        delete_session(phone)
        create_session(phone)
        update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
        return f"{MSGS['SAUDACAO']}\n\n{primeira['pergunta']}"
