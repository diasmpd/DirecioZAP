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
