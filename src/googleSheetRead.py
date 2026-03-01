# googleSheetRead.py

# ============================================================
# IMPORT
# ============================================================

import os
import re
from typing import List, Dict, Tuple, Optional

# Librerie Google API
from google.oauth2 import service_account
from googleapiclient.discovery import build


# ============================================================
# CONFIGURAZIONE ACCESSO GOOGLE (Domain Wide Delegation)
# ============================================================

# File JSON del Service Account ufficiale (con Domain-Wide Delegation attiva)
SERVICE_ACCOUNT_FILE = "service_account_official.json"

# Email reale del dominio JEToP che ha accesso ai file GDrive.
# Il service account impersonerà questo utente.
IMPERSONATED_USER = "ivan.lacognata@jetop.com"

# Scope autorizzazioni richieste.
# Attualmente full access a Sheets + Drive.
# Se si vuole maggiore sicurezza, si possono usare scope readonly.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ID del foglio Google di configurazione (NON il link completo)
CONFIG_SPREADSHEET_ID = "1-F8QkULRrF_kfAVcyPdLNiuqqlmsi5ftpQcY7uSnogk"

# Range di lettura del foglio config:
# A: Nome progetto
# B: ChatId Telegram
# C: Giorni_avviso
# D: Link Gantt
CONFIG_RANGE = "Foglio1!A2:D"

# Intestazioni usate per costruire i dizionari di output
HEADERS = ["Nome", "ChatId", "Giorni_avviso", "Gantt"]


# ============================================================
# CREAZIONE SERVIZIO GOOGLE SHEETS
# ============================================================

def get_sheets_service():
    """
    Crea e restituisce il client Google Sheets API v4
    usando Service Account + Domain Wide Delegation.

    Processo:
    1) Carica chiave JSON
    2) Applica scope
    3) Impersona utente reale (IMPERSONATED_USER)
    4) Costruisce oggetto service
    """

    # Verifica che il file credenziali esista
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"File non trovato: {SERVICE_ACCOUNT_FILE}")

    # Caricamento credenziali service account
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )

    # Impersonificazione utente reale dominio JEToP
    delegated_creds = creds.with_subject(IMPERSONATED_USER)

    # Costruzione client Sheets API v4
    return build("sheets", "v4", credentials=delegated_creds)


# ============================================================
# UTILITA': ESTRAZIONE ID DA LINK GOOGLE SHEETS
# ============================================================

def extract_id_from_url(url: str) -> Optional[str]:
    """
    Estrae lo spreadsheetId da un link di Google Sheets.

    Accetta:
    - link completo (https://docs.google.com/spreadsheets/d/...)
    - oppure direttamente un ID

    Ritorna:
    - ID stringa
    - None se non valido
    """

    if not url:
        return None

    url = str(url).strip()

    # Caso 1: è già un ID valido
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", url):
        return url

    # Caso 2: formato classico /d/<ID>/
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    # Caso 3: parametro ?id=<ID>
    m = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    return None


# ============================================================
# LETTURA FOGLIO DI CONFIGURAZIONE
# ============================================================

def export_data() -> Tuple[List[Dict[str, str]], object, object]:
    """
    Legge il foglio Google di configurazione del bot.

    Ritorna:
      - data: lista di dict nel formato:
            {
              "Nome": ...,
              "ChatId": ...,
              "Giorni_avviso": ...,
              "Gantt": ...
            }
      - sheet_api: oggetto API Sheets (per riutilizzo)
      - service: oggetto service completo (usato poi per leggere Gantt)

    In caso di errore:
      - ritorna (-1, None, None)
      - stampa errore su console
    """

    try:
        # Inizializza servizio Google Sheets
        service = get_sheets_service()
        sheet_api = service.spreadsheets()

        # Lettura range configurato
        result = sheet_api.values().get(
            spreadsheetId=CONFIG_SPREADSHEET_ID,
            range=CONFIG_RANGE,
            valueRenderOption="FORMATTED_VALUE",  # restituisce valori come mostrati nel foglio
        ).execute()

        rows = result.get("values", [])

        data: List[Dict[str, str]] = []

        for row in rows:
            # Salta righe completamente vuote
            if not row or not any(str(x).strip() for x in row):
                continue

            # Padding: se la riga ha meno colonne di HEADERS,
            # aggiungiamo stringhe vuote per evitare errori zip()
            row = row + [""] * (len(HEADERS) - len(row))

            # Crea dict associando HEADERS -> valori riga
            entry = dict(zip(HEADERS, row))
            data.append(entry)

        return data, sheet_api, service

    except Exception as e:
        # Errore generico nella lettura
        print("ERRORE export_data:", e)
        return -1, None, None