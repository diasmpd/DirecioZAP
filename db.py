"""Acesso ao banco Postgres (Neon) — fonte única da verdade de perguntas, sessões e cadastros.

O bot usa um pool de conexões: abrir uma conexão nova com o Neon leva de 1 a 4 s nesta
rede (TLS + autenticação), e cada mensagem faz várias consultas — com conexão reaproveitada
cada consulta leva ~100 ms. O Neon suspende o banco após ~5 min ocioso e derruba conexões
abertas; em vez de testar a conexão antes de cada consulta (uma ida e volta a mais),
a consulta é repetida uma vez numa conexão nova se a primeira estiver morta. As conexões
são autocommit: cada comando já é uma transação, sem a ida e volta extra do COMMIT.
O Manager, que faz poucas consultas espaçadas, abre uma conexão por operação.
Datas e UUIDs voltam como string ISO, no mesmo formato que o resto do código já usa.
"""
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS perguntas (
  id        SERIAL PRIMARY KEY,
  ordem     INTEGER NOT NULL,
  campo     TEXT NOT NULL UNIQUE,
  label     TEXT NOT NULL,
  pergunta  TEXT NOT NULL,
  tipo      TEXT NOT NULL DEFAULT 'texto',
  msg_erro  TEXT,
  ativo     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS cadastros (
  id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone     TEXT NOT NULL,
  dados     JSONB NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- Preenchido pelo avisos_pc.py quando o e-mail de aviso sai; NULL = aviso pendente.
  notificado_em TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sessions (
  phone         TEXT PRIMARY KEY,
  state         TEXT NOT NULL DEFAULT 'SAUDACAO',
  dados         JSONB NOT NULL DEFAULT '{}',
  tentativas    JSONB NOT NULL DEFAULT '{}',
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS sessions_atualizado_em_idx ON sessions (atualizado_em);

-- Portal do Fornecedor (portal.py): status do envio, motivo/resposta e o que foi enviado.
-- portal_status NULL = ainda não processado.
ALTER TABLE cadastros ADD COLUMN IF NOT EXISTS portal_status TEXT;
ALTER TABLE cadastros ADD COLUMN IF NOT EXISTS portal_em TIMESTAMPTZ;
ALTER TABLE cadastros ADD COLUMN IF NOT EXISTS portal_detalhe TEXT;
ALTER TABLE cadastros ADD COLUMN IF NOT EXISTS portal_envio JSONB;

-- Ajustes de dados que devem rodar uma vez só (ver init_schema).
CREATE TABLE IF NOT EXISTS migracoes (
  nome        TEXT PRIMARY KEY,
  aplicada_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

PERGUNTAS_PADRAO = [
    # CNPJ primeiro: a consulta na Receita preenche a Razão Social e ela não é perguntada.
    (1, "cnpj", "CNPJ", "Por favor, informe o CNPJ da empresa.", "cnpj", "CNPJ inválido."),
    (2, "razao_social", "Razão Social", "Qual é a Razão Social da sua empresa?", "texto", None),
    # O telefone não é perguntado: é o próprio número do WhatsApp. O e-mail vai para o Portal.
    (3, "email_portal", "E-mail", "Qual o e-mail da empresa?", "email", "E-mail inválido."),
    (4, "servico", "Serviços", "Quais serviços sua empresa oferece?", "servicos", None),
    (5, "estados", "Regionais", "Em quais regionais da Direcional vocês atendem? Pode escolher mais de uma.", "estados_atendidos", None),
]

# Colunas que o Manager pode gravar em perguntas — nomes de coluna não podem vir de fora sem filtro.
_COLUNAS_PERGUNTA = ("ordem", "campo", "label", "pergunta", "tipo", "msg_erro", "ativo")


def _serializar(row: dict) -> dict:
    return {
        k: v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, UUID) else v
        for k, v in row.items()
    }


class Database:
    def __init__(self, url: str, pool: bool = False):
        self.url = url
        self._pool: ConnectionPool | None = None
        if pool:
            self._pool = ConnectionPool(
                url,
                min_size=1,
                max_size=4,
                # Fecha conexões ociosas antes de o Neon derrubá-las ao suspender (~5 min).
                max_idle=240,
                # keepalives: o firewall da rede corporativa derruba conexões TCP ociosas em
                # ~2 min; um pacote a cada 30 s mantém a conexão viva.
                kwargs={"connect_timeout": 15, "autocommit": True,
                        "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10,
                        "keepalives_count": 3},
                open=True,
            )

    @contextmanager
    def _conn(self):
        if self._pool is not None:
            with self._pool.connection() as conn:
                yield conn
        else:
            with psycopg.connect(self.url, connect_timeout=15) as conn:
                yield conn

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()

    def _query(self, sql: str, params=(), fetch: bool = True) -> list[dict]:
        tentativas = 2 if self._pool is not None else 1
        for tentativa in range(tentativas):
            try:
                with self._conn() as conn:
                    cur = conn.cursor(row_factory=dict_row)
                    cur.execute(sql, params)
                    if fetch and cur.description:
                        return [_serializar(r) for r in cur.fetchall()]
                    return []
            except psycopg.OperationalError:
                # Conexão do pool derrubada pelo Neon ao suspender: o pool já a descartou;
                # repetir pega uma nova. Comandos daqui são idempotentes ou nem chegaram ao banco.
                if tentativa + 1 == tentativas:
                    raise
                # Se uma conexão morreu, as outras ociosas do pool provavelmente também:
                # testa e descarta todas antes de repetir, para não pegar outra morta.
                self._pool.check()
        return []

    # ── Estrutura ──────────────────────────────────────────────

    def init_schema(self) -> bool:
        """Cria as tabelas que faltarem e, se não houver nenhuma pergunta, insere as padrão.
        Retorna True quando inseriu as perguntas padrão."""
        with self._conn() as conn:
            conn.execute(SCHEMA_SQL)
            sem_coluna = conn.execute(
                "SELECT NOT EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'cadastros' AND column_name = 'notificado_em')"
            ).fetchone()[0]
            if sem_coluna:
                # Banco anterior aos avisos: os cadastros que já existem não devem gerar e-mail.
                conn.execute("ALTER TABLE cadastros ADD COLUMN notificado_em TIMESTAMPTZ")
                conn.execute("UPDATE cadastros SET notificado_em = NOW()")
            self._preparar_lista(conn)
            vazio = conn.execute("SELECT NOT EXISTS (SELECT 1 FROM perguntas)").fetchone()[0]
            if vazio:
                conn.cursor().executemany(
                    "INSERT INTO perguntas (ordem, campo, label, pergunta, tipo, msg_erro) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    PERGUNTAS_PADRAO,
                )
            # Out/2026: o CNPJ passa a vir antes da Razão Social (que a Receita preenche).
            # Só uma vez — depois disso, a ordem definida no Manager é respeitada.
            with conn.transaction():
                primeira_vez = conn.execute(
                    "INSERT INTO migracoes (nome) VALUES ('cnpj_antes_da_razao_social') "
                    "ON CONFLICT DO NOTHING RETURNING nome"
                ).fetchone()
                if primeira_vez and not vazio:
                    ordens = dict(conn.execute(
                        "SELECT campo, ordem FROM perguntas WHERE campo IN ('cnpj', 'razao_social')"
                    ).fetchall())
                    if len(ordens) == 2 and ordens["razao_social"] < ordens["cnpj"]:
                        for campo, outro in (("cnpj", "razao_social"), ("razao_social", "cnpj")):
                            conn.execute("UPDATE perguntas SET ordem = %s WHERE campo = %s",
                                         (ordens[outro], campo))
            # Out/2026: o Contato (telefone ou e-mail) vira só o e-mail — o telefone já é o
            # número do WhatsApp. Só uma vez, e só se o Contato ainda for o padrão.
            with conn.transaction():
                primeira_vez = conn.execute(
                    "INSERT INTO migracoes (nome) VALUES ('contato_vira_email') "
                    "ON CONFLICT DO NOTHING RETURNING nome"
                ).fetchone()
                if primeira_vez and not vazio:
                    _, campo, label, pergunta, tipo, msg_erro = PERGUNTAS_PADRAO[2]
                    conn.execute(
                        "UPDATE perguntas SET campo = %s, label = %s, pergunta = %s, tipo = %s, msg_erro = %s "
                        "WHERE campo = 'contato' AND tipo = 'contato' "
                        "AND NOT EXISTS (SELECT 1 FROM perguntas WHERE campo = %s)",
                        (campo, label, pergunta, tipo, msg_erro, campo),
                    )
                    # A instrução do menu já diz quantos serviços escolher.
                    conn.execute(
                        "UPDATE perguntas SET pergunta = %s WHERE campo = 'servico' AND pergunta = %s",
                        (PERGUNTAS_PADRAO[3][3], "Quais serviços sua empresa oferece? Pode escolher mais de um."),
                    )
            # Nov/2026: a saudação ganhou o aviso de privacidade e a pergunta do CNPJ, o
            # "Por favor". Só uma vez, e só se a pergunta ainda for o texto padrão antigo.
            with conn.transaction():
                primeira_vez = conn.execute(
                    "INSERT INTO migracoes (nome) VALUES ('cnpj_por_favor') "
                    "ON CONFLICT DO NOTHING RETURNING nome"
                ).fetchone()
                if primeira_vez and not vazio:
                    conn.execute(
                        "UPDATE perguntas SET pergunta = %s WHERE campo = 'cnpj' AND pergunta = %s",
                        (PERGUNTAS_PADRAO[0][3], "Informe o CNPJ da empresa:"),
                    )
            return vazio

    @staticmethod
    def _preparar_lista(conn) -> None:
        """Colunas do LISTA_FORNECEDORES.xlsm (lista_fornecedores.py). Os cadastros que já
        existiam quando elas foram criadas ficam como "anterior": só os novos entram na lista."""
        sem_coluna = conn.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'cadastros' AND column_name = 'lista_status')"
        ).fetchone()[0]
        if not sem_coluna:
            return
        with conn.transaction():
            conn.execute("ALTER TABLE cadastros ADD COLUMN IF NOT EXISTS lista_status TEXT")
            conn.execute("ALTER TABLE cadastros ADD COLUMN IF NOT EXISTS lista_em TIMESTAMPTZ")
            conn.execute("ALTER TABLE cadastros ADD COLUMN IF NOT EXISTS lista_detalhe TEXT")
            conn.execute("ALTER TABLE cadastros ADD COLUMN IF NOT EXISTS lista_envio JSONB")
            conn.execute("UPDATE cadastros SET lista_status = 'anterior', lista_em = NOW(), "
                         "lista_detalhe = 'Cadastro anterior à inclusão automática na lista'")

    def preparar_lista(self) -> None:
        with self._conn() as conn:
            self._preparar_lista(conn)

    # ── Sessões ────────────────────────────────────────────────

    def get_session(self, phone: str) -> dict | None:
        rows = self._query("SELECT * FROM sessions WHERE phone = %s", (phone,))
        return rows[0] if rows else None

    def create_session(self, phone: str) -> dict:
        now = datetime.now(timezone.utc)
        self._query(
            """INSERT INTO sessions (phone, state, dados, tentativas, criado_em, atualizado_em)
               VALUES (%s, 'SAUDACAO', '{}', '{}', %s, %s)
               ON CONFLICT (phone) DO UPDATE SET
                 state = 'SAUDACAO', dados = '{}', tentativas = '{}',
                 criado_em = EXCLUDED.criado_em, atualizado_em = EXCLUDED.atualizado_em""",
            (phone, now, now),
            fetch=False,
        )
        return {
            "phone": phone,
            "state": "SAUDACAO",
            "dados": {},
            "tentativas": {},
            "criado_em": now.isoformat(),
            "atualizado_em": now.isoformat(),
        }

    def update_session(self, phone: str, state: str, dados: dict, tentativas: dict) -> None:
        self._query(
            """INSERT INTO sessions (phone, state, dados, tentativas, atualizado_em)
               VALUES (%s, %s, %s, %s, NOW())
               ON CONFLICT (phone) DO UPDATE SET
                 state = EXCLUDED.state, dados = EXCLUDED.dados,
                 tentativas = EXCLUDED.tentativas, atualizado_em = EXCLUDED.atualizado_em""",
            (phone, state, Jsonb(dados), Jsonb(tentativas)),
            fetch=False,
        )

    def delete_session(self, phone: str) -> None:
        self._query("DELETE FROM sessions WHERE phone = %s", (phone,), fetch=False)

    def delete_sessoes_expiradas(self, horas: int = 24) -> int:
        """Apaga conversas abandonadas. Retorna quantas foram apagadas."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM sessions WHERE atualizado_em < NOW() - make_interval(hours => %s)",
                (horas,),
            )
            return cur.rowcount

    def get_sessions(self, limit: int = 50) -> list[dict]:
        return self._query(
            "SELECT * FROM sessions ORDER BY atualizado_em DESC LIMIT %s", (limit,)
        )

    # ── Perguntas ──────────────────────────────────────────────

    def get_perguntas(self) -> list[dict]:
        return self._query("SELECT * FROM perguntas WHERE ativo ORDER BY ordem")

    def get_todas_perguntas(self) -> list[dict]:
        """Inclui as inativas — usadas para rotular colunas de cadastros antigos na exportação."""
        return self._query("SELECT * FROM perguntas ORDER BY ordem")

    def create_pergunta(self, data: dict) -> dict:
        cols = [c for c in _COLUNAS_PERGUNTA if c in data]
        rows = self._query(
            f"INSERT INTO perguntas ({', '.join(cols)}) "
            f"VALUES ({', '.join(['%s'] * len(cols))}) RETURNING *",
            [data[c] for c in cols],
        )
        return rows[0]

    def update_pergunta(self, id_: int, data: dict) -> None:
        cols = [c for c in _COLUNAS_PERGUNTA if c in data]
        if not cols:
            return
        self._query(
            f"UPDATE perguntas SET {', '.join(f'{c} = %s' for c in cols)} WHERE id = %s",
            [data[c] for c in cols] + [id_],
            fetch=False,
        )

    def delete_pergunta(self, id_: int) -> None:
        self._query("DELETE FROM perguntas WHERE id = %s", (id_,), fetch=False)

    # ── Cadastros concluídos ───────────────────────────────────

    def save_cadastro(self, phone: str, dados: dict) -> str:
        """Grava o cadastro e devolve o id dele."""
        rows = self._query(
            "INSERT INTO cadastros (phone, dados) VALUES (%s, %s) RETURNING id",
            (phone, Jsonb(dados)),
        )
        return rows[0]["id"]

    def completar_cadastro(self, id_: str, campos: dict) -> None:
        """Junta campos a um cadastro já gravado (ex.: o e-mail do Portal, pedido depois)."""
        self._query(
            "UPDATE cadastros SET dados = dados || %s WHERE id = %s",
            (Jsonb(campos), id_),
            fetch=False,
        )

    def get_cadastros_sem_aviso(self) -> list[dict]:
        return self._query("SELECT * FROM cadastros WHERE notificado_em IS NULL ORDER BY criado_em")

    def marcar_notificado(self, id_: str) -> None:
        self._query("UPDATE cadastros SET notificado_em = NOW() WHERE id = %s", (id_,), fetch=False)

    # ── Portal do Fornecedor ──────────────────────────────────

    def get_cadastros_portal_pendentes(self) -> list[dict]:
        """Cadastros com e-mail do Portal ainda não processados (o e-mail é pedido depois da
        confirmação: sem ele, o fornecedor ainda pode estar respondendo ou pulou)."""
        return self._query(
            "SELECT * FROM cadastros WHERE portal_status IS NULL AND dados ? 'email_portal' "
            "ORDER BY criado_em"
        )

    def get_cadastros_portal(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT * FROM cadastros WHERE portal_status IS NOT NULL "
            "ORDER BY (portal_status IN ('revisar', 'erro')) DESC, criado_em DESC LIMIT %s",
            (limit,),
        )

    def marcar_portal(self, id_: str, status: str, detalhe: str | None, envio: dict | None) -> None:
        self._query(
            "UPDATE cadastros SET portal_status = %s, portal_em = NOW(), portal_detalhe = %s, "
            "portal_envio = %s WHERE id = %s",
            (status, detalhe, Jsonb(envio) if envio is not None else None, id_),
            fetch=False,
        )

    # ── LISTA_FORNECEDORES.xlsm ───────────────────────────────

    def get_cadastros_lista_pendentes(self, espera_min: int = 60) -> list[dict]:
        """Cadastros ainda não processados para a lista. Espera o e-mail do Portal (pedido depois
        da confirmação) ou, se o fornecedor não respondeu, espera_min minutos."""
        return self._query(
            "SELECT * FROM cadastros WHERE lista_status IS NULL AND (dados ? 'email_portal' "
            "OR criado_em < NOW() - make_interval(mins => %s)) ORDER BY criado_em",
            (espera_min,),
        )

    def get_cadastros_lista(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT * FROM cadastros WHERE lista_status IS NOT NULL AND lista_status <> 'anterior' "
            "ORDER BY (lista_status IN ('revisar', 'erro')) DESC, criado_em DESC LIMIT %s",
            (limit,),
        )

    def marcar_lista(self, id_: str, status: str, detalhe: str | None, envio: dict | None) -> None:
        self._query(
            "UPDATE cadastros SET lista_status = %s, lista_em = NOW(), lista_detalhe = %s, "
            "lista_envio = %s WHERE id = %s",
            (status, detalhe, Jsonb(envio) if envio is not None else None, id_),
            fetch=False,
        )

    def get_cadastros(self, limit: int | None = None, recentes_primeiro: bool = False) -> list[dict]:
        ordem = "DESC" if recentes_primeiro else "ASC"
        if limit is None:
            return self._query(f"SELECT * FROM cadastros ORDER BY criado_em {ordem}")
        return self._query(f"SELECT * FROM cadastros ORDER BY criado_em {ordem} LIMIT %s", (limit,))


# ── Funções usadas pelo bot (lêem DATABASE_URL do .env via config) ──

_db: Database | None = None
_db_lock = threading.Lock()

# As perguntas mudam raramente (só pelo Manager) e são lidas em toda mensagem: um cache
# curto corta uma consulta por mensagem. Uma edição no Manager vale em até 60 s.
_CACHE_PERGUNTAS_S = 60
_cache_perguntas: tuple[float, list[dict]] | None = None


def _get_db() -> Database:
    global _db
    with _db_lock:
        if _db is None:
            from config import settings
            _db = Database(settings.DATABASE_URL, pool=True)
        return _db


def fechar() -> None:
    """Fecha o pool (o Manager para e reinicia o bot no mesmo processo)."""
    global _db, _cache_perguntas
    with _db_lock:
        if _db is not None:
            _db.close()
            _db = None
        _cache_perguntas = None


def get_session(phone: str) -> dict | None:
    return _get_db().get_session(phone)


def create_session(phone: str) -> dict:
    return _get_db().create_session(phone)


def update_session(phone: str, state: str, dados: dict, tentativas: dict) -> None:
    _get_db().update_session(phone, state, dados, tentativas)


def delete_session(phone: str) -> None:
    _get_db().delete_session(phone)


def get_perguntas() -> list[dict]:
    global _cache_perguntas
    agora = time.monotonic()
    if _cache_perguntas and agora - _cache_perguntas[0] < _CACHE_PERGUNTAS_S:
        return _cache_perguntas[1]
    perguntas = _get_db().get_perguntas()
    _cache_perguntas = (agora, perguntas)
    return perguntas


def get_todas_perguntas() -> list[dict]:
    return _get_db().get_todas_perguntas()


def save_cadastro(phone: str, dados: dict) -> str:
    return _get_db().save_cadastro(phone, dados)


def completar_cadastro(id_: str, campos: dict) -> None:
    _get_db().completar_cadastro(id_, campos)


def get_cadastros() -> list[dict]:
    return _get_db().get_cadastros()


def init_schema() -> bool:
    return _get_db().init_schema()


def delete_sessoes_expiradas(horas: int = 24) -> int:
    return _get_db().delete_sessoes_expiradas(horas)
