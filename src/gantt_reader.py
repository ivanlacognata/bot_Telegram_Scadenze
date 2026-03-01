# gantt_reader.py

# ============================================================
# IMPORT
# ============================================================

import re
from datetime import date, datetime, timedelta
from typing import List, Tuple, Optional


# ============================================================
# UTILITA': ESTRAZIONE SPREADSHEET ID DAL LINK
# ============================================================

def extract_spreadsheet_key(url: str) -> str:
    """
    Estrae lo spreadsheetId da un link Google Sheets.

    Accetta:
    - link completo (https://docs.google.com/spreadsheets/d/...)
    - oppure direttamente un ID

    Ritorna:
    - ID valido (stringa)
    - solleva ValueError se non riesce ad estrarlo
    """
    url = (url or "").strip()

    # Caso 1: è già un ID valido
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", url):
        return url

    # Caso 2: formato classico /spreadsheets/d/<ID>
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    # Caso 3: parametro ?id=<ID>
    m = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    # Caso 4: fallback generico /d/<ID>
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    raise ValueError(f"Link Gantt non valido: impossibile estrarre la key. Valore letto: {url}")


# ============================================================
# CONVERSIONE DATA SERIALE GOOGLE
# ============================================================

def gs_serial_to_date(serial: float) -> date:
    """
    Converte un seriale Google Sheets in oggetto date.

    Google Sheets conta i giorni dal 1899-12-30.
    """
    base = date(1899, 12, 30)
    return base + timedelta(days=int(serial))


# ============================================================
# LETTURA CELLA SINGOLA
# ============================================================

def _get_cell(sheet_api, spreadsheet_id: str, a1: str, value_render_option: str) -> Optional[str]:
    """
    Legge una singola cella da Google Sheets usando A1 notation.

    Parametri:
    - sheet_api: oggetto sheets().values()
    - spreadsheet_id: ID foglio
    - a1: riferimento cella (es: "GANTT!F9")
    - value_render_option: UNFORMATTED_VALUE o FORMATTED_VALUE

    Ritorna:
    - valore cella oppure None se vuota
    """
    res = sheet_api.values().get(
        spreadsheetId=spreadsheet_id,
        range=a1,
        valueRenderOption=value_render_option,
    ).execute()

    vals = res.get("values", [])
    if not vals or not vals[0]:
        return None
    return vals[0][0]


# ============================================================
# LETTURA DATA INIZIO PROGETTO (F9)
# ============================================================

def read_start_date(service, spreadsheet_id: str, worksheet_title: str, debug: bool = False) -> date:
    """
    Legge la data inizio progetto da cella F9.

    Logica robusta:
    1) Prova come seriale numerico (UNFORMATTED_VALUE)
    2) Fallback parsing stringa:
       - dd/mm
       - dd/mm/yy
       - dd/mm/yyyy
       - ISO format
    """

    sheet_api = service.spreadsheets()

    # 1) Tentativo lettura seriale numerico
    try:
        raw = _get_cell(sheet_api, spreadsheet_id, f"{worksheet_title}!F9", "UNFORMATTED_VALUE")
        if raw is not None and str(raw).strip() != "":
            d = gs_serial_to_date(float(raw))
            if debug:
                print(f"[GANTT] F9 unformatted={raw} -> start_date={d}")
            return d
    except Exception as e:
        if debug:
            print(f"[GANTT] F9 unformatted read failed: {type(e).__name__}: {e}")

    # 2) Fallback: stringa formattata
    raw = _get_cell(sheet_api, spreadsheet_id, f"{worksheet_title}!F9", "FORMATTED_VALUE")
    if not raw:
        raise ValueError("Cella F9 (data inizio progetto) vuota")

    raw = str(raw).strip()
    parts = raw.split("/")

    # dd/mm/yyyy o dd/mm/yy
    if len(parts) == 3:
        d, m, y = parts
        y_i = int(y)
        if y_i < 100:
            y_i += 2000
        return date(y_i, int(m), int(d))

    # dd/mm (senza anno)
    if len(parts) == 2:
        d, m = parts
        return date(date.today().year, int(m), int(d))

    # formato ISO
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        raise ValueError(f"Formato data inizio (F9) non supportato: {raw}")


# ============================================================
# PARSING SCADENZA
# ============================================================

def parse_deadline_value(v, today: date) -> date:
    """
    Converte la scadenza letta dal Gantt in oggetto date.

    Accetta:
    - seriale numerico
    - stringa dd/mm
    - stringa dd/mm/yy
    - stringa dd/mm/yyyy

    Se manca l'anno (dd/mm):
      - interpreta come prossima occorrenza rispetto a today
    """

    if v is None:
        raise ValueError("Scadenza vuota")

    s = str(v).strip()
    if not s:
        raise ValueError("Scadenza vuota")

    # Caso 1: seriale
    try:
        return gs_serial_to_date(float(s))
    except Exception:
        pass

    parts = s.split("/")

    # dd/mm/yyyy o dd/mm/yy
    if len(parts) == 3:
        d, m, y = parts
        y_i = int(y)
        if y_i < 100:
            y_i += 2000
        return date(y_i, int(m), int(d))

    # dd/mm senza anno → prossima occorrenza
    if len(parts) == 2:
        d, m = parts
        d_i, m_i = int(d), int(m)

        candidate = date(today.year, m_i, d_i)
        if candidate < today:
            candidate = date(today.year + 1, m_i, d_i)
        return candidate

    raise ValueError(f"Formato scadenza non riconosciuto: {s}")


# ============================================================
# PARSING DURATA
# ============================================================

def parse_duration_days(v) -> int:
    """
    Converte durata in giorni (colonna D).

    Può arrivare come:
    - 3
    - 3.0
    - stringa "3"
    """
    if v is None:
        raise ValueError("Durata vuota")

    s = str(v).strip()
    if not s:
        raise ValueError("Durata vuota")

    return int(float(s))


# ============================================================
# LETTURA SERVIZI DAL GANTT
# ============================================================

def read_services_deadlines(
    service,
    gantt_url: str,
    worksheet_title: str = "GANTT",
    start_row: int = 9,
    max_rows: int = 1200,
    debug: bool = False,
) -> List[Tuple[str, str, int, date]]:
    """
    Legge il Gantt e ritorna lista di servizi nel formato:

        (AREA, NomeServizio, DurataGiorni, Scadenza)

    Logica di riconoscimento AREA:
      - Colonna B non vuota
      - Colonna D (durata) vuota
      - Colonna E (scadenza) vuota
      → è titolo area

    Colonne lette:
      B = Nome area / Nome servizio
      D = Durata
      E = Scadenza
    """

    # Estrazione ID foglio
    key = extract_spreadsheet_key(gantt_url)
    sheet_api = service.spreadsheets()

    # Lettura data inizio progetto (utile per robustezza futura)
    _ = read_start_date(service, key, worksheet_title, debug=debug)

    # Calcolo range dinamico
    end_row = start_row + max_rows - 1
    rng = f"{worksheet_title}!B{start_row}:E{end_row}"

    # Lettura blocco dati
    res = sheet_api.values().get(
        spreadsheetId=key,
        range=rng,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()

    values = res.get("values", [])

    out: List[Tuple[str, str, int, date]] = []
    current_area = "Generale"  # fallback se nessuna area definita
    today = date.today()

    for row in values:
        # Garantisce almeno 4 colonne (B,C,D,E)
        while len(row) < 4:
            row.append("")

        nome = (row[0] or "").strip()  # Colonna B
        durata_raw = row[2]            # Colonna D
        scad_raw = row[3]              # Colonna E

        durata_str = str(durata_raw).strip() if durata_raw is not None else ""
        scad_str = str(scad_raw).strip() if scad_raw is not None else ""

        # Riga completamente vuota
        if not nome and not durata_str and not scad_str:
            continue

        # Header eventuale
        if nome.lower() == "nome area":
            continue

        # Riga AREA
        if nome and not durata_str and not scad_str:
            current_area = nome
            continue

        # Riga servizio incompleta
        if not nome or not durata_str or not scad_str:
            continue

        # Parsing robusto
        try:
            durata = parse_duration_days(durata_raw)
            scad = parse_deadline_value(scad_raw, today)
            out.append((current_area, nome, durata, scad))
        except Exception:
            # Una riga sporca non deve bloccare l'intero Gantt
            continue

    return out