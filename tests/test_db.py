"""
Testes — db.py (sem banco real: só a montagem das consultas e a conversão de tipos)
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import db


def test_A_serializa_datas_e_uuid_como_string():
    row = {
        "id": UUID("12345678-1234-5678-1234-567812345678"),
        "criado_em": datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc),
        "dados": {"cnpj": "1"},
    }
    out = db._serializar(row)
    assert out["id"] == "12345678-1234-5678-1234-567812345678"
    assert out["criado_em"] == "2026-10-14T12:00:00+00:00"
    assert out["dados"] == {"cnpj": "1"}


def test_A_update_pergunta_ignora_colunas_desconhecidas():
    base = db.Database("postgresql://x")
    base._query = MagicMock(return_value=[])
    base.update_pergunta(7, {"ordem": 2, "id": 99, "label; DROP TABLE perguntas": "x"})
    sql, params = base._query.call_args.args[:2]
    assert sql == "UPDATE perguntas SET ordem = %s WHERE id = %s"
    assert params == [2, 7]


def test_B_update_pergunta_sem_colunas_validas_nao_consulta():
    base = db.Database("postgresql://x")
    base._query = MagicMock()
    base.update_pergunta(7, {"id": 1})
    base._query.assert_not_called()


def test_A_get_cadastros_do_bot_traz_todos_em_ordem_cronologica():
    base = db.Database("postgresql://x")
    base._query = MagicMock(return_value=[{"id": "a"}])
    assert base.get_cadastros() == [{"id": "a"}]
    assert base._query.call_args.args[0] == "SELECT * FROM cadastros ORDER BY criado_em ASC"


def test_A_query_repete_uma_vez_se_conexao_do_pool_morreu(monkeypatch):
    import psycopg
    base = db.Database("postgresql://x")
    base._pool = MagicMock()  # só para ativar a repetição; _conn é substituído abaixo
    cur = MagicMock(description=None)
    conn = MagicMock(); conn.cursor.return_value = cur
    chamadas = []

    from contextlib import contextmanager
    @contextmanager
    def fake_conn():
        chamadas.append(1)
        if len(chamadas) == 1:
            raise psycopg.OperationalError("server closed the connection")
        yield conn
    monkeypatch.setattr(base, "_conn", fake_conn)
    assert base._query("DELETE FROM sessions WHERE phone = %s", ("1",), fetch=False) == []
    assert len(chamadas) == 2
    base._pool.check.assert_called_once()


def test_A_perguntas_em_cache_por_60s(monkeypatch):
    fake = MagicMock(); fake.get_perguntas.return_value = [{"campo": "cnpj"}]
    monkeypatch.setattr(db, "_get_db", lambda: fake)
    monkeypatch.setattr(db, "_cache_perguntas", None)
    relogio = [1000.0]
    monkeypatch.setattr(db.time, "monotonic", lambda: relogio[0])
    db.get_perguntas(); db.get_perguntas()
    assert fake.get_perguntas.call_count == 1
    relogio[0] += 61
    db.get_perguntas()
    assert fake.get_perguntas.call_count == 2
