"""
Testes — supabase_session.py (paginação da exportação)
"""
from unittest.mock import MagicMock

import supabase_session


def test_A_get_cadastros_busca_todas_as_paginas(mock_supabase, monkeypatch):
    monkeypatch.setattr("supabase_session._PAGINA", 2)
    paginas = [[{"id": 1}, {"id": 2}], [{"id": 3}, {"id": 4}], [{"id": 5}]]
    query = mock_supabase.table.return_value.select.return_value.order.return_value
    query.range.return_value.execute.side_effect = [MagicMock(data=p) for p in paginas]

    rows = supabase_session.get_cadastros()

    assert [r["id"] for r in rows] == [1, 2, 3, 4, 5]
    assert [c.args for c in query.range.call_args_list] == [(0, 1), (2, 3), (4, 5)]
