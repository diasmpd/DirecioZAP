import os
import threading
from datetime import datetime

import openpyxl
from openpyxl import Workbook

from config import settings

_lock = threading.Lock()


def append_fornecedor(phone: str, dados: dict, perguntas: list[dict]) -> None:
    with _lock:
        path = settings.EXCEL_PATH
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        labels = [p.get("label") or p["campo"] for p in perguntas]
        cabecalho = ["Telefone"] + labels + ["Data Cadastro"]
        row = (
            [phone]
            + [dados.get(p["campo"], "") for p in perguntas]
            + [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        )

        if os.path.exists(path):
            wb = openpyxl.load_workbook(path)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            ws.append(cabecalho)

        ws.append(row)
        wb.save(path)
