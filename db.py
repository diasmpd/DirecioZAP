"""Acesso ao banco Postgres (Neon) — fonte única da verdade de perguntas, sessões e cadastros.

Uma conexão por operação: o Neon suspende o banco após alguns minutos ocioso e derruba
conexões abertas, então manter uma conexão viva só trocaria latência por erros de conexão
morta. Datas e UUIDs voltam como string ISO, no mesmo formato que o resto do código já usa.
"""
from datetime import datetime, timezone
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

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
  criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
"""

PERGUNTAS_PADRAO = [
    (1, "razao_social", "Razão Social", "Qual é a Razão Social da sua empresa?", "texto", None),
    (2, "cnpj", "CNPJ", "Informe o CNPJ da empresa:", "cnpj", "CNPJ inválido."),
    (3, "contato", "Contato", "Qual o contato principal? (telefone ou e-mail):", "contato", "Formato inválido."),
    (4, "servico", "Serviço", "Que tipo de serviço sua empresa oferece?", "texto", None),
    (5, "estados", "Estados", "Em quais estados atuam? (ex: MG, SP):", "estados", "Siglas inválidas."),
]

# Colunas que o Manager pode gravar em perguntas — nomes de coluna não podem vir de fora sem filtro.
_COLUNAS_PERGUNTA = ("ordem", "campo", "label", "pergunta", "tipo", "msg_erro", "ativo")


def _serializar(row: dict) -> dict:
    return {
        k: v.isoformat() if isinstance(v, datetime) else str(v) if isinstance(v, UUID) else v
        for k, v in row.items()
    }


class Database:
    def __init__(self, url: str):
        self.url = url

    def _query(self, sql: str, params=(), fetch: bool = True) -> list[dict]:
        with psycopg.connect(self.url, row_factory=dict_row, connect_timeout=15) as conn:
            cur = conn.execute(sql, params)
            if fetch and cur.description:
                return [_serializar(r) for r in cur.fetchall()]
            return []

    # ── Estrutura ──────────────────────────────────────────────

    def init_schema(self) -> bool:
        """Cria as tabelas que faltarem e, se não houver nenhuma pergunta, insere as padrão.
        Retorna True quando inseriu as perguntas padrão."""
        with psycopg.connect(self.url, connect_timeout=15) as conn:
            conn.execute(SCHEMA_SQL)
            vazio = conn.execute("SELECT NOT EXISTS (SELECT 1 FROM perguntas)").fetchone()[0]
            if vazio:
                conn.cursor().executemany(
                    "INSERT INTO perguntas (ordem, campo, label, pergunta, tipo, msg_erro) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    PERGUNTAS_PADRAO,
                )
            return vazio

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

    def save_cadastro(self, phone: str, dados: dict) -> None:
        self._query(
            "INSERT INTO cadastros (phone, dados) VALUES (%s, %s)",
            (phone, Jsonb(dados)),
            fetch=False,
        )

    def get_cadastros(self, limit: int | None = None, recentes_primeiro: bool = False) -> list[dict]:
        ordem = "DESC" if recentes_primeiro else "ASC"
        if limit is None:
            return self._query(f"SELECT * FROM cadastros ORDER BY criado_em {ordem}")
        return self._query(f"SELECT * FROM cadastros ORDER BY criado_em {ordem} LIMIT %s", (limit,))


# ── Funções usadas pelo bot (lêem DATABASE_URL do .env via config) ──

_db: Database | None = None


def _get_db() -> Database:
    global _db
    if _db is None:
        from config import settings
        _db = Database(settings.DATABASE_URL)
    return _db


def get_session(phone: str) -> dict | None:
    return _get_db().get_session(phone)


def create_session(phone: str) -> dict:
    return _get_db().create_session(phone)


def update_session(phone: str, state: str, dados: dict, tentativas: dict) -> None:
    _get_db().update_session(phone, state, dados, tentativas)


def delete_session(phone: str) -> None:
    _get_db().delete_session(phone)


def get_perguntas() -> list[dict]:
    return _get_db().get_perguntas()


def get_todas_perguntas() -> list[dict]:
    return _get_db().get_todas_perguntas()


def save_cadastro(phone: str, dados: dict) -> None:
    _get_db().save_cadastro(phone, dados)


def get_cadastros() -> list[dict]:
    return _get_db().get_cadastros()
