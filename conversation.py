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
    MAX_SERVICOS,
    SERVICOS,
    escolher,
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

# Contato da equipe para quem precisa falar com uma pessoa, e página para quem não é fornecedor.
CONTATO_EQUIPE = "(31) 99758-1137"
# Cartão de contato (Meta) enviado junto das mensagens que oferecem a equipe. O wa_id é o número
# como o WhatsApp o registrou — esta conta é de antes do 9º dígito, por isso sem o 9.
CARTAO_EQUIPE = {
    "name": {"formatted_name": "Mateus - Suprimentos Direcional", "first_name": "Mateus",
             "last_name": "Suprimentos Direcional"},
    "org": {"company": "Direcional Engenharia", "department": "Suprimentos"},
    "phones": [{"phone": "+55 31 99758-1137", "type": "WORK", "wa_id": "553197581137"}],
}
URL_CONTATO_DIRECIONAL = "https://www.direcional.com.br/contato-direcional/"

# Mensagem de "oi"/"tudo bem?" que chega logo depois da resposta do bot (o fornecedor escreveu
# em várias mensagens seguidas) é ignorada em silêncio, em vez de contar como resposta errada.
JANELA_RAJADA_S = 60

ESTADO_CONCLUIDO = "CONCLUIDO"
BOTAO_NAO_FORNECEDOR = ("NAO_FORNECEDOR", "Não sou fornecedor")

MSGS = {
    "SAUDACAO": (
        "Olá! Seja bem-vindo(a) ao cadastro de fornecedores da Direcional.\n\n"
        "As informações fornecidas nesta conversa serão utilizadas para analisar o interesse da empresa "
        "em fornecer produtos ou serviços ao Grupo Direcional, possibilitar contatos relacionados ao "
        "processo e, quando aplicável, conduzir o cadastro e a homologação de fornecedores.\n\n"
        "Eventuais dados pessoais informados durante o atendimento serão tratados conforme nossa "
        "Política de Privacidade, disponível em:\n"
        "https://ri.direcional.com.br/governanca-corporativa/estatuto-politicas-e-codigos/"
    ),
    "SUCESSO": "Cadastro realizado com sucesso! Os responsáveis pela contratação entrarão em contato com você.",
    "PEDE_EMAIL_PORTAL": (
        "Para receber as cotações, sua empresa também precisa estar no Portal do Fornecedor. "
        "Qual e-mail devemos usar no Portal?"
    ),
    "EMAIL_PORTAL_OK": "Obrigado! Vamos usar *{email}* no seu cadastro do Portal do Fornecedor, onde ficam as cotações.",
    "EMAIL_PORTAL_JA_INFORMADO": "Vamos usar *{email}* no seu cadastro do Portal do Fornecedor, onde ficam as cotações.",
    "EMAIL_PORTAL_INVALIDO": "Não reconheci um e-mail. Envie no formato compras@suaempresa.com.br, ou toque em *Agora não*.",
    "LINK_PORTAL": (
        "Tudo bem! Quando quiser, cadastre-se no Portal do Fornecedor para ter acesso às cotações: "
        f"{portal.URL}"
    ),
    "REINICIO": "Sem problemas, vamos recomeçar.",
    # Recomeço forçado no meio da conversa (pergunta removida no Manager, estado desconhecido):
    # o fornecedor já viu o aviso de privacidade, então não repete a saudação inteira.
    "RECOMECO": "Precisamos recomeçar o seu cadastro.",
    "ERRO_TECNICO": "Tivemos um problema técnico ao processar sua mensagem. Por favor, envie novamente em alguns minutos.",
    "ERRO_SALVAR": "Ocorreu um problema técnico ao salvar. Por favor, tente novamente mais tarde.",
    # Depois de 3 respostas inválidas a conversa continua (as respostas já dadas são mantidas),
    # mas o fornecedor recebe a saída para falar com uma pessoa.
    "MAX_TENTATIVAS": (
        "Parece que essa pergunta está difícil. Se preferir, fale com a nossa equipe pelo "
        f"{CONTATO_EQUIPE}. Ou digite CANCELAR para encerrar."
    ),
    "APENAS_TEXTO": "Por favor, responda apenas com texto.",
    "MIDIA_AUDIO": "Ainda não consigo ouvir áudios. Por favor, escreva a sua resposta.",
    "MIDIA_ARQUIVO": "Ainda não consigo ler imagens nem arquivos. Por favor, digite a sua resposta.",
    "NAO_FORNECEDOR": (
        "Este canal é só para o cadastro de fornecedores da Direcional. Para comprar um imóvel, "
        "falar sobre a sua unidade, trabalhar na Direcional ou outros assuntos, acesse:\n"
        f"{URL_CONTATO_DIRECIONAL}"
    ),
    "SE_FOR_FORNECEDOR": "Se você é fornecedor, é só continuar respondendo:",
    "ATENDENTE": (
        f"Para falar com a nossa equipe, ligue ou mande mensagem para o {CONTATO_EQUIPE}.\n"
        "Se quiser continuar o cadastro por aqui, é só responder:"
    ),
    "PERGUNTA_LIVRE": (
        "Por aqui eu só consigo fazer o cadastro. Para dúvidas, fale com a nossa equipe pelo "
        f"{CONTATO_EQUIPE}.\nPara continuar o cadastro, é só responder:"
    ),
    "SEM_CNPJ": (
        "O cadastro de fornecedores precisa de um CNPJ (MEI também vale). Se tiver dúvidas, fale "
        f"com a nossa equipe pelo {CONTATO_EQUIPE}.\nQuando tiver o CNPJ, é só enviar aqui."
    ),
    "CONTINUAR": "Vamos continuar o cadastro:",
    "CONCLUIDO": (
        "Seu cadastro já foi concluído. Obrigado!\n"
        "Para cadastrar outra empresa, digite RECOMEÇAR. Para falar com a nossa equipe: "
        f"{CONTATO_EQUIPE}."
    ),
    "SEM_CONFIG": "Bot sem perguntas configuradas. Entre em contato com o administrador.",
    "CONFIRMACAO_INVALIDA": "Por favor, responda S para confirmar ou N para recomeçar.",
    "CANCELADO": "Tudo bem! Encerramos por aqui. Quando quiser retomar, é só enviar uma mensagem.",
    "AJUDA_GERAL": (
        "Posso te ajudar\n"
        "• Digite AJUDA para receber exemplos de resposta\n"
        "• Digite VOLTAR para corrigir a pergunta anterior\n"
        "• Digite RECOMEÇAR para iniciar do zero\n"
        "• Digite ATENDENTE para falar com a nossa equipe\n"
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
_INTENT_NAO_FORNECEDOR = {"NAO_FORNECEDOR", "NAO SOU FORNECEDOR", "NAO SOU FORNECEDORA"}
_INTENT_ATENDENTE = {
    "ATENDENTE", "ATENDIMENTO", "HUMANO", "FALAR COM ATENDENTE", "FALAR COM UM ATENDENTE",
    "FALAR COM ALGUEM", "FALAR COM UMA PESSOA", "QUERO FALAR COM ALGUEM", "QUERO FALAR COM UM ATENDENTE",
}

# Só olhados quando a resposta NÃO é válida para a pergunta — assim "Imóveis XYZ Ltda" como
# Razão Social continua valendo. Comparação por palavra inteira, sem acento.
_PALAVRAS_NAO_FORNECEDOR = (
    "NAO SOU FORNECEDOR", "COMPRAR", "COMPRA DE", "APARTAMENTO", "APTO", "IMOVEL", "MINHA UNIDADE",
    "MEU APARTAMENTO", "FINANCIAMENTO", "BOLETO", "PARCELA", "CORRETOR", "CURRICULO", "EMPREGO",
    "VAGA DE", "VAGAS DE", "TRABALHAR NA", "RECLAMACAO", "RECLAMAR", "ASSISTENCIA TECNICA", "SAC",
)
_PALAVRAS_ATENDENTE = ("ATENDENTE", "FALAR COM", "HUMANO", "UMA PESSOA", "LIGAR", "TELEFONE DE VOCES")
# Tipos em que a resposta tem formato próprio: "ok"/"sim"/"vi no Instagram" nunca é a resposta.
_TIPOS_ESTRUTURADOS = {"cnpj", "email", "telefone", "contato", "servicos", "estados", "estados_atendidos"}
# Tipos de menu: "assistência técnica" e "manutenção de imóvel" são serviços, não assunto de cliente.
_TIPOS_MENU = {"servicos", "estados_atendidos"}
_SAUDACOES = {"OI", "OIE", "OII", "OLA", "OLAA", "BOM", "BOA", "DIA", "TARDE", "NOITE", "TUDO", "BEM",
              "E", "VOCE", "VC", "COMO", "VAI"}
_PALAVRAS_SEM_CNPJ = (
    "NAO TENHO CNPJ", "SEM CNPJ", "NAO POSSUO CNPJ", "NAO TENHO", "PESSOA FISICA", "CPF", "AUTONOMO",
)
# "Oi", "bom dia", "tudo bem?", "quero me cadastrar", 👍: conversa, não resposta à pergunta.
_PALAVRAS_CONVERSA = {
    "OI", "OIE", "OII", "OLA", "OLAA", "BOM", "BOA", "DIA", "TARDE", "NOITE", "TUDO", "BEM", "BEM?",
    "E", "VOCE", "VC", "COMO", "VAI", "OK", "OBRIGADO", "OBRIGADA", "VALEU", "BLZ", "BELEZA", "TA",
    "CERTO", "ENTENDI", "PESSOAL", "QUERO", "GOSTARIA", "DE", "ME", "CADASTRAR", "CADASTRO", "SER",
    "FORNECEDOR", "FORNECEDORA", "FAZER", "O", "MEU", "UM", "UMA", "VI", "NO", "NA", "POST",
    "LINKEDIN", "INSTAGRAM", "INSTA", "AQUI", "TUDO", "BOM", "SIM",
}

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
    sem_pontuacao = _sem_pontuacao(text)
    if base in _INTENT_NAO_FORNECEDOR or sem_pontuacao in _INTENT_NAO_FORNECEDOR:
        return "NAO_FORNECEDOR"
    if sem_pontuacao in _INTENT_ATENDENTE:
        return "ATENDENTE"

    return None


def _sem_pontuacao(text: str) -> str:
    """Texto base só com letras, números e espaços (tira emoji, ?, !, vírgulas)."""
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", _texto_base(text)).split())


def _contem(text: str, expressoes) -> bool:
    limpo = f" {_sem_pontuacao(text)} "
    return any(f" {e} " in limpo for e in expressoes)


def _e_conversa(text: str, tipo: str) -> bool:
    """Cumprimento, agradecimento, emoji ou "quero me cadastrar" — sem dado nenhum.

    Num campo de texto livre (ex: uma pergunta "Possui alvará?" criada no Manager), "Sim",
    "Ok" ou "Vi no Instagram" são respostas de verdade: lá só cumprimento puro é conversa."""
    if not text.strip() or any(ch.isdigit() for ch in text) or "@" in text:
        return False
    palavras = _sem_pontuacao(text).split()
    vocabulario = _PALAVRAS_CONVERSA if (tipo or "texto").lower() in _TIPOS_ESTRUTURADOS else _SAUDACOES
    return all(p in vocabulario for p in palavras)


def _cpf_valido(digitos: str) -> bool:
    """Confere os dígitos verificadores — um celular com DDD também tem 11 dígitos."""
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    nums = [int(d) for d in digitos]
    for n in (9, 10):
        dv = sum(nums[i] * (n + 1 - i) for i in range(n)) * 10 % 11 % 10
        if dv != nums[n]:
            return False
    return True


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
        return "Exemplo de e-mail: compras@suaempresa.com.br"
    if tipo == "estados":
        return "Exemplo: MG, SP, RJ"
    if tipo == "servicos":
        return (f"Escolha até {MAX_SERVICOS} serviços. Envie os números da lista, separados por vírgula "
                "(ex: 3, 15, 22) ou uma faixa (ex: 3 a 5). Também vale o nome do serviço (ex: gás, pintura).")
    if tipo == "estados_atendidos":
        return f"Envie os números ou as siglas, separados por vírgula (ex: MG, SP). Atendemos: {', '.join(ESTADOS_ATENDIDOS)}."
    return "Responda com um texto curto e direto."


_ALIASES_CAMPO = {
    "RAZAO": ("razao_social",),
    "SOCIAL": ("razao_social",),
    "NOME": ("razao_social",),
    "CNPJ": ("cnpj",),
    "CONTATO": ("contato", portal.CAMPO_EMAIL),
    "TELEFONE": ("contato",),
    "EMAIL": (portal.CAMPO_EMAIL, "contato"),
    "E-MAIL": (portal.CAMPO_EMAIL, "contato"),
    "SERVICO": ("servico",),
    "SERVICOS": ("servico",),
    "ESTADO": ("estados",),
    "ESTADOS": ("estados",),
    "UF": ("estados",),
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
        for campo in _ALIASES_CAMPO.get(palavra, ()):
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
    if opcoes is SERVICOS:
        instrucao = f"Escolha até {MAX_SERVICOS} serviços. {instrucao}"
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
        # Mesma regra do Portal: o e-mail aceito aqui é o que vai para o cadastro de lá.
        return portal.normalizar_email(text)
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
        _concluir(phone)
        return MSGS["LINK_PORTAL"]

    email = portal.normalizar_email(text)
    if email is None and sugestao and (base == "USAR" or base.startswith("USAR ")
                                       or _resposta_confirmacao(text) == "SIM"):
        email = sugestao

    if email is None:
        n = tentativas.get(ESTADO_EMAIL_PORTAL, 0) + 1
        if n >= MAX_TENTATIVAS:
            _concluir(phone)
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
        _concluir(phone)
    except Exception:
        log.exception("E-mail do Portal salvo, mas falhou ao encerrar sessão de %s", mascarar(phone))
    return MSGS["EMAIL_PORTAL_OK"].format(email=email)


def _concluir(phone: str) -> None:
    """Cadastro terminado: a sessão fica em CONCLUIDO, sem nenhum dado, para que o "obrigado"
    seguinte não abra um cadastro novo. Ela some na limpeza de 24h, como as demais."""
    update_session(phone, ESTADO_CONCLUIDO, {}, {})


def _recente(session: dict) -> bool:
    """O bot respondeu há menos de JANELA_RAJADA_S segundos?"""
    try:
        ts = datetime.fromisoformat(str(session.get("atualizado_em", "")).replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - ts < timedelta(seconds=JANELA_RAJADA_S)


def _repetir(state: str, dados: dict, perguntas: list[dict]) -> str:
    """O que o fornecedor precisa responder agora, para repetir depois de um aviso."""
    if state.startswith(("AGUARDA_", "ALTERA_")):
        campo = state.split("_", 1)[1]
        p = next((p for p in perguntas if p["campo"] == campo), None)
        if p:
            return _pergunta(p)
    if state == "CONFIRMACAO":
        return _gerar_resumo(dados, perguntas)
    if state == ESTADO_EMAIL_PORTAL:
        botoes = [_BOTAO_USAR, _BOTAO_PULAR] if dados.get("_sugestao_email") else [_BOTAO_PULAR]
        return Resposta(MSGS["PEDE_EMAIL_PORTAL"], botoes=botoes)
    return _pergunta(perguntas[0])


def _com_cartao(resposta) -> Resposta:
    """Junta o cartão de contato da equipe à resposta: o fornecedor salva ou abre a conversa com um toque."""
    return Resposta(resposta, botoes=getattr(resposta, "botoes", None), lista=getattr(resposta, "lista", None),
                    lista_botao=getattr(resposta, "lista_botao", "Escolher"), cartao=CARTAO_EQUIPE)


def _com_botoes_do_resumo(resposta):
    # Toda resposta que traz o resumo pede confirmação: vai com os botões.
    if resposta and _RESUMO_TITULO in resposta and not getattr(resposta, "botoes", None):
        return Resposta(resposta, botoes=_BOTOES_CONFIRMACAO)
    return resposta


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
        """Responde a uma mensagem de texto. Uma resposta vazia ("") quer dizer: não responder."""
        perguntas = get_perguntas()
        if not perguntas:
            return MSGS["SEM_CONFIG"]

        session = self._sessao(phone)
        state = session["state"]
        dados = dict(session.get("dados") or {})
        tentativas = dict(session.get("tentativas") or {})

        resposta = self._handle(phone, text, state, dados, tentativas, perguntas, _recente(session))
        return _com_botoes_do_resumo(resposta)

    def process_midia(self, phone: str, tipo: str) -> str:
        """Áudio, foto, figurinha etc.: avisa que só lemos texto e repete a pergunta atual, sem
        contar como resposta errada. Reação (👍 numa mensagem) e tipos de sistema: sem resposta."""
        if tipo in {"audio", "voice"}:
            aviso = MSGS["MIDIA_AUDIO"]
        elif tipo in {"image", "document", "video"}:
            aviso = MSGS["MIDIA_ARQUIVO"]
        elif tipo in {"sticker", "location", "contacts"}:
            aviso = MSGS["APENAS_TEXTO"]
        else:
            return ""

        perguntas = get_perguntas()
        if not perguntas:
            return MSGS["SEM_CONFIG"]
        session = self._sessao(phone)
        state = session["state"]
        dados = dict(session.get("dados") or {})
        tentativas = dict(session.get("tentativas") or {})

        if state == "SAUDACAO":
            # Primeiro contato foi uma figurinha ou um áudio: é um "oi" — manda a saudação.
            return self._handle(phone, "", state, dados, tentativas, perguntas, False)
        if state == ESTADO_CONCLUIDO:
            return MSGS["CONCLUIDO"]
        update_session(phone, state, dados, tentativas)  # renova a janela de mensagens seguidas
        return _com_botoes_do_resumo(prefixar(aviso, _repetir(state, dados, perguntas)))

    @staticmethod
    def _sessao(phone: str) -> dict:
        session = get_session(phone)
        if session is None or _sessao_expirada(session):
            if session:
                delete_session(phone)
            session = create_session(phone)
        return session

    def _handle(self, phone, text, state, dados, tentativas, perguntas, recente=False):
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

        if intencao == "NAO_FORNECEDOR":
            delete_session(phone)
            return MSGS["NAO_FORNECEDOR"]

        if state == ESTADO_CONCLUIDO:
            # Sem update_session: a sessão concluída expira 24h depois do fim do cadastro.
            return MSGS["CONCLUIDO"]

        if intencao == "ATENDENTE":
            if state == "SAUDACAO":
                # Primeira mensagem já pede atendente: passa o contato e já abre o cadastro (com
                # o aviso de privacidade), para que um CNPJ enviado em seguida valha como resposta.
                update_session(phone, f"AGUARDA_{primeira['campo']}", dados, tentativas)
                resp = _com(f"{MSGS['ATENDENTE']}\n\n{MSGS['SAUDACAO']}", primeira)
                if not resp.botoes and not resp.lista:
                    resp = Resposta(resp, botoes=[BOTAO_NAO_FORNECEDOR])
                return _com_cartao(resp)
            update_session(phone, state, dados, tentativas)
            return _com_cartao(prefixar(MSGS["ATENDENTE"], _repetir(state, dados, perguntas)))

        if intencao == "AJUDA" and state == "SAUDACAO":
            update_session(phone, f"AGUARDA_{primeira['campo']}", dados, tentativas)
            return _com(MSGS["AJUDA_GERAL"], primeira)

        if state == "SAUDACAO":
            update_session(phone, f"AGUARDA_{primeira['campo']}", dados, tentativas)
            resp = _com(f"{MSGS['SAUDACAO']}\n\nVou te guiar rapidinho no cadastro.", primeira)
            if not resp.botoes and not resp.lista:
                resp = Resposta(resp, botoes=[BOTAO_NAO_FORNECEDOR])
            return resp

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
                return _com(MSGS["RECOMECO"], primeira)

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

            def sem_contar(resposta):
                """Responde sem contar tentativa, mas renova o horário da sessão: é ele que diz se a
                próxima mensagem chegou "logo depois" da nossa (janela de mensagens seguidas)."""
                update_session(phone, state, dados, tentativas)
                return resposta

            # "Oi", "tudo bem?", 👍: não é resposta. Se chegou logo depois da nossa mensagem, o
            # fornecedor está escrevendo em várias mensagens seguidas — não responde de novo.
            if _e_conversa(text, tipo):
                return "" if recente else sem_contar(_com(MSGS["CONTINUAR"], pergunta_cfg))

            # Uma pergunta ("o que é razão social?") não é resposta, nem num campo de texto livre.
            if tipo.lower() == "texto" and text.strip().endswith("?"):
                return sem_contar(_com_cartao(_com(MSGS["PERGUNTA_LIVRE"], pergunta_cfg)))

            valor = _validar(text, tipo)

            if valor is None:
                # Respostas que não são erro de digitação: não contam como tentativa.
                if tipo.lower() not in _TIPOS_MENU and _contem(text, _PALAVRAS_NAO_FORNECEDOR):
                    return sem_contar(_com(f"{MSGS['NAO_FORNECEDOR']}\n\n{MSGS['SE_FOR_FORNECEDOR']}",
                                           pergunta_cfg))
                if tipo.lower() == "cnpj" and (_contem(text, _PALAVRAS_SEM_CNPJ)
                                       or _cpf_valido(re.sub(r"\D", "", text))):
                    return sem_contar(_com_cartao(MSGS["SEM_CNPJ"]))
                if _contem(text, _PALAVRAS_ATENDENTE):
                    return sem_contar(_com_cartao(_com(MSGS["ATENDENTE"], pergunta_cfg)))
                if text.strip().endswith("?"):
                    return sem_contar(_com_cartao(_com(MSGS["PERGUNTA_LIVRE"], pergunta_cfg)))

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
                    # Não apaga o que já foi respondido: zera a contagem e oferece a equipe.
                    tentativas.pop(campo, None)
                    update_session(phone, state, dados, tentativas)
                    return _com_cartao(_com(f"{MSGS['MAX_TENTATIVAS']}\n\nDica: {_mensagem_ajuda(tipo)}",
                                            pergunta_cfg))
                update_session(phone, state, dados, tentativas)
                opcoes = _MENUS.get(tipo.lower())
                escolhidos, invalidos = escolher(text, SERVICOS) if opcoes is SERVICOS else ([], [])
                if not invalidos and len(escolhidos) > MAX_SERVICOS:
                    return (f"Você escolheu {len(escolhidos)} serviços, mas o limite é {MAX_SERVICOS}. "
                            f"Envie só os {MAX_SERVICOS} principais (ex: 3, 15, 22).")
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
                email = dados.get(portal.CAMPO_EMAIL)
                if email:
                    # O e-mail já foi perguntado no cadastro: não há o que pedir depois.
                    try:
                        _concluir(phone)
                    except Exception:
                        log.exception("Cadastro salvo, mas falhou ao encerrar sessão de %s", mascarar(phone))
                    return f"{MSGS['SUCESSO']}\n\n{MSGS['EMAIL_PORTAL_JA_INFORMADO'].format(email=email)}"
                # Sem a pergunta do e-mail (desativada no Manager): a sessão segue só para pedi-lo.
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
        return _com(MSGS["RECOMECO"], primeira)
