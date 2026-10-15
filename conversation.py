from datetime import datetime, timezone, timedelta
import re
import unicodedata

from db import (
    completar_cadastro,
    create_session,
    delete_session,
    get_perguntas,
    get_session,
    save_cadastro,
    update_session,
)
import portal
import receita
from log_setup import get_logger, mascarar
from opcoes import (
    ESTADOS_ATENDIDOS,
    SERVICOS,
    explicar_invalidos,
    menu,
    normalizar_estados_atendidos,
    normalizar_servicos,
)
from resposta import Resposta, prefixar
from validators import (
    normalizar_cnpj,
    normalizar_contato,
    normalizar_estados,
    normalizar_whatsapp_br,
)

log = get_logger("conversation")

MAX_TENTATIVAS = 3

MSGS = {
    "SAUDACAO": "Olá! Seja bem-vindo(a) ao cadastro de fornecedores da Direcional.",
    "SUCESSO": "Cadastro realizado com sucesso! Os responsáveis pela contratação entrarão em contato com você.",
    "PEDE_EMAIL_PORTAL": (
        "Para receber as cotações, sua empresa também precisa estar no Portal do Fornecedor. "
        "Qual e-mail devemos usar no Portal?"
    ),
    "EMAIL_PORTAL_OK": "Obrigado! Vamos usar *{email}* no seu cadastro do Portal do Fornecedor, onde ficam as cotações.",
    "EMAIL_PORTAL_INVALIDO": "Não reconheci um e-mail. Envie no formato compras@suaempresa.com.br, ou toque em *Agora não*.",
    "LINK_PORTAL": (
        "Tudo bem! Quando quiser, cadastre-se no Portal do Fornecedor para ter acesso às cotações: "
        f"{portal.URL}"
    ),
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

# Confirmação do resumo: decide pela primeira palavra, ignorando pontuação e acento,
# para aceitar "Sim!", "s.", "Sim, confirmo" e "Não." — antes só "S"/"SIM" exatos passavam.
_CONFIRMA_SIM = {"S", "SIM", "YES", "Y", "OK", "CONFIRMO", "CONFIRMAR", "CONFIRMADO", "CORRETO", "CERTO", "ISSO"}
_CONFIRMA_NAO = {"N", "NAO", "NO"}


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


def _resposta_confirmacao(text: str) -> str | None:
    """'SIM', 'NAO' ou None. Uma resposta com sim e não ao mesmo tempo é ambígua."""
    palavras = re.sub(r"[^A-Z0-9 ]", " ", _texto_base(text)).split()
    if not palavras:
        return None
    if palavras[0] in _CONFIRMA_SIM and not _CONFIRMA_NAO & set(palavras):
        return "SIM"
    if palavras[0] in _CONFIRMA_NAO and not _CONFIRMA_SIM & set(palavras):
        return "NAO"
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
    if tipo == "servicos":
        return ("Envie os números da lista, separados por vírgula (ex: 3, 15, 22) ou uma faixa "
                "(ex: 3 a 5). Também vale o nome do serviço (ex: gás, pintura).")
    if tipo == "estados_atendidos":
        return f"Envie os números ou as siglas, separados por vírgula (ex: MG, SP). Atendemos: {', '.join(ESTADOS_ATENDIDOS)}."
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


# Tipos de pergunta com lista fechada de respostas: o menu numerado vai junto da pergunta.
_MENUS = {"servicos": SERVICOS, "estados_atendidos": ESTADOS_ATENDIDOS}

_RESUMO_TITULO = "Resumo do cadastro:"
_BOTOES_CONFIRMACAO = [("SIM", "Confirmar"), ("NAO", "Recomeçar"), ("ALTERAR", "Alterar um dado")]


def _pergunta(p: dict) -> str:
    opcoes = _MENUS.get((p.get("tipo") or "").lower())
    if not opcoes:
        return p["pergunta"]
    instrucao = ("Responda com os números, separados por vírgula (ex: 3, 15, 22)."
                 if len(opcoes) > 10 else "Responda com os números ou as siglas (ex: 1, 3).")
    # A instrução vem antes do menu: a lista de serviços é longa e o exemplo ficaria escondido no fim.
    return f"{p['pergunta']}\n{instrucao}\n\n{menu(opcoes)}"


def _com(prefixo: str, p: dict) -> Resposta:
    return prefixar(prefixo, _pergunta(p))


def _proxima(perguntas: list[dict], dados: dict) -> dict | None:
    """A primeira pergunta ainda sem resposta — pula as preenchidas pela consulta do CNPJ."""
    return next((p for p in perguntas if p["campo"] not in dados), None)


def _aplicar_receita(cnpj: str, dados: dict, perguntas: list[dict]) -> str:
    """Consulta o CNPJ e preenche a Razão Social (se ainda não foi digitada) e a situação na
    Receita. Devolve o aviso para o fornecedor, ou "" se não houve o que mostrar."""
    auto = [c for c in dados.get("_auto") or [] if c != "razao_social"]
    if "razao_social" in (dados.get("_auto") or []):
        dados.pop("razao_social", None)  # veio do CNPJ anterior: não vale para o novo
    for campo in receita.LABELS:
        dados.pop(campo, None)

    info = receita.consultar_cnpj(cnpj)
    aviso = ""
    if info:
        dados[receita.CAMPO_SITUACAO] = info["situacao"]
        if info.get("municipio"):
            dados[receita.CAMPO_CIDADE] = info["municipio"]
        if info.get("uf"):
            dados[receita.CAMPO_UF] = info["uf"]
        pede_razao = any(p["campo"] == "razao_social" for p in perguntas)
        if info.get("razao_social") and pede_razao and "razao_social" not in dados:
            dados["razao_social"] = info["razao_social"]
            auto.append("razao_social")
            local = "/".join(x for x in (info.get("municipio"), info.get("uf")) if x)
            aviso = (f"Encontrei na Receita Federal: *{info['razao_social']}*"
                     + (f" ({local})" if local else "") + ".\n"
                     "Se não for a sua empresa, dá para corrigir no resumo, no final.")

    _marcar_auto(dados, auto)
    return aviso


def _marcar_auto(dados: dict, auto: list[str]) -> None:
    """Guarda quais campos foram preenchidos pela consulta do CNPJ (não foram perguntados)."""
    if auto:
        dados["_auto"] = auto
    else:
        dados.pop("_auto", None)


def _para_salvar(dados: dict) -> dict:
    """Tira o controle interno da sessão (chaves com "_") antes de gravar o cadastro."""
    return {k: v for k, v in dados.items() if not k.startswith("_")}


def _validar(text: str, tipo: str):
    tipo = (tipo or "texto").lower()
    if tipo == "servicos":
        return normalizar_servicos(text)
    if tipo == "estados_atendidos":
        return normalizar_estados_atendidos(text)
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
    linhas = [f"{_RESUMO_TITULO}\n"]
    for p in perguntas:
        label = p.get("label") or p["campo"]
        linhas.append(f"• {label}: {dados.get(p['campo'], '')}")
    linhas.append(
        "\nAs informações estão corretas? Toque em um dos botões abaixo"
        " (ou responda S para confirmar, N para recomeçar, ou ALTERAR + campo, ex: ALTERAR CNPJ)."
    )
    return "\n".join(linhas)


# ── E-mail do Portal (depois da confirmação; o cadastro já está salvo) ──

ESTADO_EMAIL_PORTAL = "EMAIL_PORTAL"
_BOTAO_USAR = ("USAR", "Usar este e-mail")
_BOTAO_PULAR = ("PULAR", "Agora não")
_PULAR = {"PULAR", "AGORA NAO", "NAO", "N", "DEPOIS", "NAO TENHO", "SEM EMAIL", "SEM E MAIL"}


def _pedir_email_portal(dados: dict) -> Resposta:
    """Mensagem de sucesso + pedido do e-mail; oferece o e-mail do Contato com um toque."""
    sugestao = dados.get("_sugestao_email")
    if sugestao:
        return Resposta(
            f"{MSGS['SUCESSO']}\n\n{MSGS['PEDE_EMAIL_PORTAL']}\n"
            f"Pode ser o *{sugestao}*? Toque em *Usar este e-mail* ou envie outro.",
            botoes=[_BOTAO_USAR, _BOTAO_PULAR],
        )
    return Resposta(
        f"{MSGS['SUCESSO']}\n\n{MSGS['PEDE_EMAIL_PORTAL']}\n(ex: compras@suaempresa.com.br)",
        botoes=[_BOTAO_PULAR],
    )


def _responder_email_portal(phone: str, text: str, dados: dict, tentativas: dict):
    base = " ".join(re.sub(r"[^A-Z0-9 ]", " ", _texto_base(text)).split())
    sugestao = dados.get("_sugestao_email")

    if base in _PULAR:
        delete_session(phone)
        return MSGS["LINK_PORTAL"]

    email = portal.normalizar_email(text)
    if email is None and sugestao and (base == "USAR" or base.startswith("USAR ")
                                       or _resposta_confirmacao(text) == "SIM"):
        email = sugestao

    if email is None:
        n = tentativas.get(ESTADO_EMAIL_PORTAL, 0) + 1
        if n >= MAX_TENTATIVAS:
            delete_session(phone)
            return MSGS["LINK_PORTAL"]
        tentativas[ESTADO_EMAIL_PORTAL] = n
        update_session(phone, ESTADO_EMAIL_PORTAL, dados, tentativas)
        botoes = [_BOTAO_USAR, _BOTAO_PULAR] if sugestao else [_BOTAO_PULAR]
        return Resposta(MSGS["EMAIL_PORTAL_INVALIDO"], botoes=botoes)

    try:
        completar_cadastro(dados["_cadastro_id"], {portal.CAMPO_EMAIL: email})
    except Exception:
        log.exception("Erro ao gravar o e-mail do Portal de %s", mascarar(phone))
        return MSGS["ERRO_TECNICO"]
    try:
        delete_session(phone)
    except Exception:
        log.exception("E-mail do Portal salvo, mas falhou ao encerrar sessão de %s", mascarar(phone))
    return MSGS["EMAIL_PORTAL_OK"].format(email=email)


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

        resposta = self._handle(phone, text, state, dados, tentativas, perguntas)
        # Toda resposta que traz o resumo pede confirmação: vai com os botões.
        if _RESUMO_TITULO in resposta and not getattr(resposta, "botoes", None):
            resposta = Resposta(resposta, botoes=_BOTOES_CONFIRMACAO)
        return resposta

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
            return _com(MSGS["REINICIO"], primeira)

        if intencao == "AJUDA" and state == "SAUDACAO":
            update_session(phone, f"AGUARDA_{primeira['campo']}", dados, tentativas)
            return _com(MSGS["AJUDA_GERAL"], primeira)

        if state == "SAUDACAO":
            update_session(phone, f"AGUARDA_{primeira['campo']}", dados, tentativas)
            return _com(f"{MSGS['SAUDACAO']}\nVou te guiar rapidinho no cadastro.", primeira)

        if state.startswith(("AGUARDA_", "ALTERA_")):
            # ALTERA_<campo>: correção de um único campo pedida no resumo; ao responder,
            # volta direto para a confirmação sem mexer nos demais campos.
            alterando = state.startswith("ALTERA_")
            campo = state.split("_", 1)[1]
            pergunta_cfg = next((p for p in perguntas if p["campo"] == campo), None)
            tipo = (pergunta_cfg or {}).get("tipo") or "texto"

            if pergunta_cfg is None:
                delete_session(phone)
                create_session(phone)
                update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
                return _com(MSGS["SAUDACAO"], primeira)

            if intencao == "AJUDA":
                return _com(_mensagem_ajuda(tipo), pergunta_cfg)

            if intencao == "VOLTAR" and alterando:
                tentativas.pop(campo, None)
                update_session(phone, "CONFIRMACAO", dados, tentativas)
                return f"Ok, mantivemos o valor anterior.\n\n{_gerar_resumo(dados, perguntas)}"

            if intencao == "VOLTAR":
                idx = next(i for i, p in enumerate(perguntas) if p["campo"] == campo)
                if idx == 0:
                    return _com("Você está na primeira pergunta.", pergunta_cfg)

                # Volta para a pergunta anterior que o fornecedor respondeu — a Razão Social
                # preenchida pelo CNPJ não foi perguntada, então volta direto para o CNPJ.
                auto = dados.get("_auto") or []
                j = idx - 1
                while j > 0 and perguntas[j]["campo"] in auto:
                    j -= 1
                destino = perguntas[j]
                for p in perguntas[j:]:
                    dados.pop(p["campo"], None)
                    tentativas.pop(p["campo"], None)
                if "cnpj" not in dados:
                    for extra in receita.LABELS:
                        dados.pop(extra, None)
                _marcar_auto(dados, [c for c in auto if c in dados])

                update_session(phone, f"AGUARDA_{destino['campo']}", dados, tentativas)
                return _com("Sem problemas, vamos corrigir juntos.", destino)

            valor = _validar(text, tipo)

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
                opcoes = _MENUS.get(tipo.lower())
                if opcoes:
                    detalhe = explicar_invalidos(text, opcoes)
                    return (f"Não consegui entender:\n{detalhe}\n\n"
                            f"Dica: {_mensagem_ajuda(tipo)}")
                erro = pergunta_cfg.get("msg_erro") or pergunta_cfg["pergunta"]
                return f"{erro}\n\nDica: {_mensagem_ajuda(tipo)}"

            tentativas.pop(campo, None)
            dados[campo] = valor
            # Digitado pelo fornecedor: deixa de ser um valor preenchido pelo CNPJ.
            _marcar_auto(dados, [c for c in dados.get("_auto") or [] if c != campo])

            aviso = _aplicar_receita(valor, dados, perguntas) if tipo.lower() == "cnpj" else ""

            proxima = _proxima(perguntas, dados)
            if proxima is not None:
                # Inclui a correção do CNPJ que não achou a empresa: a Razão Social é perguntada.
                update_session(phone, f"AGUARDA_{proxima['campo']}", dados, tentativas)
                return _com(aviso, proxima)

            update_session(phone, "CONFIRMACAO", dados, tentativas)
            if alterando:
                aviso = f"{aviso}\n\nPronto, atualizado." if aviso else "Pronto, atualizado."
            return prefixar(aviso, _gerar_resumo(dados, perguntas))

        if state == "CONFIRMACAO":
            resp = _resposta_confirmacao(text)

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
                    return _com(
                        "Perfeito, vamos ajustar só esse ponto.\n"
                        f"{label} atual: {dados.get(campo_alvo, '')}\n"
                        "(Digite VOLTAR para manter o valor atual.)",
                        pergunta_alvo,
                    )

                # "Alterar um dado" (botão) ou "ALTERAR" sem campo: lista dos campos para tocar.
                so_o_verbo = len(_texto_base(text).split()) == 1
                return Resposta(
                    ("Qual informação você quer alterar?\n" if so_o_verbo
                     else "Não identifiquei qual campo você quer alterar.\n")
                    + "Toque em \"Escolher\" ou digite, por exemplo: ALTERAR CNPJ.",
                    lista=[(f"ALTERAR {p.get('label') or p['campo']}", (p.get("label") or p["campo"])[:24])
                           for p in perguntas[:10]],
                )

            if resp == "SIM":
                try:
                    telefone = normalizar_whatsapp_br(phone)
                    cadastro_id = save_cadastro(telefone, _para_salvar(dados))
                except Exception:
                    log.exception("Erro ao salvar cadastro de %s", mascarar(phone))
                    return MSGS["ERRO_SALVAR"]
                # O cadastro já está salvo: uma falha daqui em diante não pode levar o
                # fornecedor a confirmar de novo (o que duplicaria o registro).
                # A sessão segue só para pedir o e-mail do Portal.
                pos = {"_cadastro_id": str(cadastro_id)}
                sugestao = portal.normalizar_email(dados.get("contato", ""))
                if sugestao:
                    pos["_sugestao_email"] = sugestao
                try:
                    update_session(phone, ESTADO_EMAIL_PORTAL, pos, {})
                except Exception:
                    log.exception("Cadastro salvo, mas falhou ao pedir o e-mail do Portal de %s", mascarar(phone))
                    try:
                        delete_session(phone)
                    except Exception:
                        log.exception("Cadastro salvo, mas falhou ao encerrar sessão de %s", mascarar(phone))
                    return f"{MSGS['SUCESSO']}\n\n{MSGS['LINK_PORTAL']}"
                return _pedir_email_portal(pos)
            if resp == "NAO":
                delete_session(phone)
                create_session(phone)
                update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
                return _com(MSGS["REINICIO"], primeira)
            return (
                f"{MSGS['CONFIRMACAO_INVALIDA']}\n"
                "Você também pode digitar ALTERAR + campo (ex: ALTERAR CNPJ).\n\n"
                f"{_gerar_resumo(dados, perguntas)}"
            )

        if state == ESTADO_EMAIL_PORTAL:
            return _responder_email_portal(phone, text, dados, tentativas)

        # fallback — estado desconhecido
        delete_session(phone)
        create_session(phone)
        update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
        return _com(MSGS["SAUDACAO"], primeira)
