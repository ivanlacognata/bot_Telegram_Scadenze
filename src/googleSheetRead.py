# googleSheetRead.py
import os
import re
from typing import List, Dict, Tuple, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ===== CONFIGURAZIONE =====
SERVICE_ACCOUNT_FILE = "service_account_official.json"
IMPERSONATED_USER = "ivan.lacognata@jetop.com"  # email reale con accesso ai file

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CONFIG_SPREADSHEET_ID = "1-F8QkULRrF_kfAVcyPdLNiuqqlmsi5ftpQcY7uSnogk"
CONFIG_RANGE = "Foglio1!A2:D"  # A: Nome | B: ChatId | C: Giorni_avviso | D: Gantt

HEADERS = ["Nome", "ChatId", "Giorni_avviso", "Gantt"]


def get_sheets_service():
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"File non trovato: {SERVICE_ACCOUNT_FILE}")

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )

    delegated_creds = creds.with_subject(IMPERSONATED_USER)
    return build("sheets", "v4", credentials=delegated_creds)


def extract_id_from_url(url: str) -> Optional[str]:
    """
    Estrae lo spreadsheetId da un link di Google Sheets.
    Accetta anche direttamente un ID.
    """
    if not url:
        return None
    url = str(url).strip()

    # caso: già un ID
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", url):
        return url

    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    m = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    return None


def export_data() -> Tuple[List[Dict[str, str]], object, object]:
    """
    Ritorna:
      - data: lista di dict con chiavi HEADERS
      - sheet_api
      - service
    Se errore:
      - (-1, None, None)
    """
    try:
        service = get_sheets_service()
        sheet_api = service.spreadsheets()

        result = sheet_api.values().get(
            spreadsheetId=CONFIG_SPREADSHEET_ID,
            range=CONFIG_RANGE,
            valueRenderOption="FORMATTED_VALUE",
        ).execute()

        rows = result.get("values", [])

        data: List[Dict[str, str]] = []
        for row in rows:
            # skip righe completamente vuote
            if not row or not any(str(x).strip() for x in row):
                continue
            # padding: se la riga ha meno colonne di HEADERS
            row = row + [""] * (len(HEADERS) - len(row))

            entry = dict(zip(HEADERS, row))
            data.append(entry)

        return data, sheet_api, service

    except Exception as e:
        print("ERRORE export_data:", e)
        return -1, None, None
