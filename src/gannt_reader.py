# gantt_reader.py
import re
from datetime import date, datetime, timedelta
from typing import List, Tuple

import gspread


def extract_spreadsheet_key(url: str) -> str:
    """
    Accetta:
    - URL completo Google Sheets
    - oppure direttamente la key (stringa lunga)
    """
    url = (url or "").strip()

    # se incollano solo la key
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", url):
        return url

    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    m = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    raise ValueError(f"Link Gantt non valido: impossibile estrarre la key. Valore letto: {url}")


def gs_serial_to_date(serial: float) -> date:
    """Google Sheets date serial: days since 1899-12-30."""
    base = date(1899, 12, 30)
    return base + timedelta(days=int(serial))


def read_start_date(ws: gspread.Worksheet) -> date:
    """
    Legge la data inizio progetto da F9 in modo robusto:
    - prova UNFORMATTED_VALUE (seriale numerico) -> conversione
    - fallback parsing stringa dd/mm, dd/mm/yy, dd/mm/yyyy
    """
    # 1) prova seriale numerico
    try:
        raw = ws.acell("F9", value_render_option="UNFORMATTED_VALUE").value
        if raw is not None and raw != "":
            return gs_serial_to_date(float(raw))
    except Exception:
        pass

    # 2) fallback stringa
    raw = ws.acell("F9").value
    if not raw:
        raise ValueError("Cella F9 (data inizio progetto) vuota")
    raw = str(raw).strip()

    parts = raw.split("/")
    if len(parts) == 3:
        d, m, y = parts
        y_i = int(y)
        if y_i < 100:
            y_i += 2000
        return date(y_i, int(m), int(d))

    if len(parts) == 2:
        # se manca l'anno, assumo anno corrente
        d, m = parts
        return date(date.today().year, int(m), int(d))

    # fallback ISO
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        raise ValueError(f"Formato data inizio (F9) non supportato: {raw}")


def parse_deadline_value(v, start_date: date) -> date:
    """
    Converte scadenza che può arrivare come:
    - seriale numerico (UNFORMATTED o anche stringa numerica)
    - stringa "dd/mm" o "dd/mm/yy" o "dd/mm/yyyy"
    Se manca l'anno (dd/mm):
      - usa l'anno di start_date
      - se mese < mese start -> anno+1
    """
    if v is None:
        raise ValueError("Scadenza vuota")

    s = str(v).strip()
    if not s:
        raise ValueError("Scadenza vuota")

    # prova seriale
    try:
        return gs_serial_to_date(float(s))
    except Exception:
        pass

    parts = s.split("/")
    if len(parts) == 3:
        d, m, y = parts
        y_i = int(y)
        if y_i < 100:
            y_i += 2000
        return date(y_i, int(m), int(d))

    if len(parts) == 2:
        d, m = parts
        d_i, m_i = int(d), int(m)
        y_i = start_date.year + (1 if m_i < start_date.month else 0)
        return date(y_i, m_i, d_i)

    raise ValueError(f"Formato scadenza non riconosciuto: {s}")


def parse_duration_days(v) -> int:
    """
    Durata in giorni: sempre numerica in colonna D.
    Può arrivare come "3", "3.0", ecc.
    """
    if v is None:
        raise ValueError("Durata vuota")
    s = str(v).strip()
    if not s:
        raise ValueError("Durata vuota")
    return int(float(s))


def read_services_deadlines(
    client: gspread.Client,
    gantt_url: str,
    worksheet_title: str = "GANTT",
    start_row: int = 10,
    max_rows: int = 500,
) -> List[Tuple[str, int, date]]:
    """
    Ritorna lista di tuple:
      (NomeServizio, DurataGiorni, ScadenzaDate)

    Template:
      - Nome servizio: colonna B
      - Durata (Giorni): colonna D
      - Scadenza: colonna E
    Lettura: range B{start_row}:E{start_row+max_rows-1}
    I "buchi" non sono un problema: saltiamo righe incomplete.
    """
    key = extract_spreadsheet_key(gantt_url)
    sh = client.open_by_key(key)

    try:
        ws = sh.worksheet(worksheet_title)
    except Exception:
        ws = sh.get_worksheet(0)

    start_date = read_start_date(ws)

    rng = f"B{start_row}:E{start_row + max_rows - 1}"  # B,C,D,E
    values = ws.get(rng)

    out: List[Tuple[str, int, date]] = []

    for row in values:
        while len(row) < 4:
            row.append("")

        nome = (row[0] or "").strip()      # B
        durata_raw = row[2]                # D (nell'intervallo B,C,D,E => index 2)
        scad_raw = row[3]                  # E (index 3)

        # Skip righe vuote o intestazioni
        if not nome and not str(scad_raw or "").strip() and not str(durata_raw or "").strip():
            continue
        if nome.lower() in ("nome area", "gantt"):
            continue

        # Deve avere almeno nome, durata e scadenza
        if not nome:
            continue
        if str(durata_raw or "").strip() == "" or str(scad_raw or "").strip() == "":
            continue

        try:
            durata = parse_duration_days(durata_raw)
            scad = parse_deadline_value(scad_raw, start_date)
            out.append((nome, durata, scad))
        except Exception:
            # riga non interpretabile -> skip
            continue

    return out
