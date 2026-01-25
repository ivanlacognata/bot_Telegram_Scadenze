# googleSheetRead.py
from datetime import date
import os

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ✅ ID del foglio CONFIG (tra /d/ e /edit nell'URL)
CONFIG_SPREADSHEET_KEY = "1mwmIAiZjGw831iLQsLBwWPzj6I9tzxX7DNREu6cyuBE"

WORKSHEET_INDEX = 0
SERVICE_ACCOUNT_FILENAME = "service_account.json"


def get_client() -> gspread.Client:
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, SERVICE_ACCOUNT_FILENAME)
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
    return gspread.authorize(creds)


def export_data():
    """
    Ritorna:
      - (data, sheet, client) se ok
      - (-1, None, None) se errore
    """
    try:
        client = get_client()
        sh = client.open_by_key(CONFIG_SPREADSHEET_KEY)
        sheet = sh.get_worksheet(WORKSHEET_INDEX)

        all_data = sheet.get_all_values()
        if not all_data:
            print(
                f"⚠️ Errore\nSeverity: 🟠\nTipo: SheetFormat\nCodice errore: 0007\n"
                f"Data: {date.today()}\nMessaggio: Foglio config vuoto o intestazioni mancanti"
            )
            return -1, None, None

        headers = all_data[0]
        rows = all_data[1:]
        data = [dict(zip(headers, row)) for row in rows if any((c or "").strip() for c in row)]

        return data, sheet, client

    except Exception as e:
        print(
            f"⚠️ Errore\nSeverity: 🔴\nTipo: DataImport\nCodice errore: 0001\n"
            f"Data: {date.today()}\nMessaggio: {type(e).__name__}: {repr(e)}"
        )
        return -1, None, None
