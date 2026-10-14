from datetime import datetime, timezone, timedelta
import re
import unicodedata

from db import (
    create_session,
    delete_session,
    get_perguntas,
    get_session,
    save_cadastro,
    update_session,
)
import receita
import selecao
from log_setup import get_logger, mascarar
from opcoes import ESTADOS_ATENDIDOS
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
    "SUCESSO": (
        "Cadastro realizado com sucesso! Os responsáveis pela contratação entrarão em contato com você.\n\n"
        "Cadastre-se também no Portal do Fornecedor para ter acesso às cotações: "
        "https://fornecedor.direcional.com.br/"
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
        return ("Escolha uma categoria (toque em Ver categorias ou digite o número dela) e responda "
                "com os números dos serviços (ex: 1, 3). Também vale digitar o nome do serviço "
                "(ex: gás, pintura). Quando terminar, digite CONCLUIR.")
    if tipo == "estados_atendidos":
        return (f"Toque em Escolher ou digite as siglas, separadas por vírgula (ex: MG, SP). "
                f"Atendemos: {', '.join(ESTADOS_ATENDIDOS)}. Para todas, digite TODAS.")
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


_RESUMO_TITULO = "Resumo do cadastro:"
_BOTOES_CONFIRMACAO = [("SIM", "Confirmar"), ("NAO", "Recomeçar"), ("ALTERAR", "Alterar um dado")]


def _pergunta(p: dict, dados: dict | None = None) -> str:
    """O texto da pergunta — para serviços e regionais, a etapa atual da escolha (selecao.py)."""
    if (p.get("tipo") or "").lower() in selecao.TIPOS:
        return selecao.prompt(p, dados)
    return p["pergunta"]


def _com(prefixo: str, p: dict, dados: dict | None = None) -> Resposta:
    return prefixar(prefixo, _pergunta(p, dados))


def _proxima(perguntas: list[dict], dados: dict) -> dict | None:
    """A primeira pergunta ainda sem resposta — pula as preenchidas pela consulta do CNPJ."""
    return next((p for p in perguntas if p["campo"] not in dados), None)


def _aplicar_receita(cnpj: str, dados: dict, perguntas: list[dict]) -> str:
    """Consulta o CNPJ e preenche a Razão Social (se ainda não foi digitada) e a situação na
    Receita. Devolve o aviso para o fornecedor, ou "" se não houve o que mostrar."""
    auto = [c for c in dados.get("_auto") or [] if c != "razao_social"]
    if "razao_social" in (dados.get("_auto") or []):
        dados.pop("razao_social", None)  # veio do CNPJ anterior: não vale para o novo
    dados.pop(receita.CAMPO_SITUACAO, None)

    info = receita.consultar_cnpj(cnpj)
    aviso = ""
    if info:
        dados[receita.CAMPO_SITUACAO] = info["situacao"]
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

    def lembrete(self, phone: str, aviso: str) -> str:
        """Para mensagens que o bot não lê (áudio, foto...): o aviso + a pergunta em que o
        fornecedor está, sem mudar nada na conversa. Sem conversa aberta, começa uma."""
        perguntas = get_perguntas()
        if not perguntas:
            return aviso
        session = get_session(phone)
        if session is None or _sessao_expirada(session) or session["state"] == "SAUDACAO":
            return prefixar(aviso, self.process(phone, ""))

        state = session["state"]
        dados = dict(session.get("dados") or {})
        if state.startswith(("AGUARDA_", "ALTERA_")):
            campo = state.split("_", 1)[1]
            pergunta_cfg = next((p for p in perguntas if p["campo"] == campo), None)
            if pergunta_cfg:
                return _com(aviso, pergunta_cfg, dados)
        if state == "CONFIRMACAO":
            return Resposta(f"{aviso}\n\n{_gerar_resumo(dados, perguntas)}", botoes=_BOTOES_CONFIRMACAO)
        return aviso

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
            em_etapas = tipo.lower() in selecao.TIPOS

            if pergunta_cfg is None:
                delete_session(phone)
                create_session(phone)
                update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
                return _com(MSGS["SAUDACAO"], primeira)

            if intencao == "AJUDA":
                return _com(_mensagem_ajuda(tipo), pergunta_cfg, dados)

            if intencao == "VOLTAR" and em_etapas:
                # Dentro de uma categoria de serviços, VOLTAR volta para as categorias.
                de_volta = selecao.voltar(pergunta_cfg, dados)
                if de_volta is not None:
                    update_session(phone, state, dados, tentativas)
                    return de_volta

            if intencao == "VOLTAR" and alterando:
                selecao.limpar(dados)
                tentativas.pop(campo, None)
                update_session(phone, "CONFIRMACAO", dados, tentativas)
                return f"Ok, mantivemos o valor anterior.\n\n{_gerar_resumo(dados, perguntas)}"

            if intencao == "VOLTAR":
                idx = next(i for i, p in enumerate(perguntas) if p["campo"] == campo)
                if idx == 0:
                    return _com("Você está na primeira pergunta.", pergunta_cfg, dados)

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
                    dados.pop(receita.CAMPO_SITUACAO, None)
                _marcar_auto(dados, [c for c in auto if c in dados])
                selecao.limpar(dados)

                update_session(phone, f"AGUARDA_{destino['campo']}", dados, tentativas)
                return _com("Sem problemas, vamos corrigir juntos.", destino)

            erro = None
            if em_etapas:
                resultado, conteudo = selecao.responder(pergunta_cfg, text, dados)
                if resultado == "continua":
                    tentativas.pop(campo, None)
                    update_session(phone, state, dados, tentativas)
                    return conteudo
                valor = conteudo if resultado == "pronto" else None
                erro = conteudo if resultado == "invalido" else None
            else:
                valor = _validar(text, tipo)

            if valor is None:
                n = tentativas.get(campo, 0) + 1
                tentativas[campo] = n
                if n >= MAX_TENTATIVAS and alterando:
                    selecao.limpar(dados)
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
                if erro:
                    return erro
                erro = pergunta_cfg.get("msg_erro") or pergunta_cfg["pergunta"]
                return f"{erro}\n\nDica: {_mensagem_ajuda(tipo)}"

            selecao.limpar(dados)
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
                    selecao.limpar(dados)
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
                    save_cadastro(telefone, _para_salvar(dados))
                except Exception:
                    log.exception("Erro ao salvar cadastro de %s", mascarar(phone))
                    return MSGS["ERRO_SALVAR"]
                # O cadastro já está salvo: uma falha daqui em diante não pode levar o
                # fornecedor a confirmar de novo (o que duplicaria o registro).
                try:
                    delete_session(phone)
                except Exception:
                    log.exception("Cadastro salvo, mas falhou ao encerrar sessão de %s", mascarar(phone))
                return MSGS["SUCESSO"]
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

        # fallback — estado desconhecido
        delete_session(phone)
        create_session(phone)
        update_session(phone, f"AGUARDA_{primeira['campo']}", {}, {})
        return _com(MSGS["SAUDACAO"], primeira)
