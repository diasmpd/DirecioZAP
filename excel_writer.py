import os
import threading
from datetime import datetime

import openpyxl
from openpyxl import Workbook

from config import settings

_lock = threading.Lock()

CABECALHO = ["Razão Social", "CNPJ", "Contato", "Serviço", "Estados", "Data Cadastro"]


def append_fornecedor(dados: dict) -> None:
    with _lock:
        path = settings.EXCEL_PATH
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        if os.path.exists(path):
            wb = openpyxl.load_workbook(path)
            ws = wb.active
        else:
            wb = Workbook()
            ws = wb.active
            ws.append(CABECALHO)

        ws.append(
            [
                dados.get("razao_social", ""),
                dados.get("cnpj", ""),
                dados.get("contato", ""),
                dados.get("servico", ""),
                dados.get("estados", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )
        wb.save(path)
