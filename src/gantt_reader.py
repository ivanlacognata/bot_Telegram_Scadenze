# gantt_reader.py 
import re
from datetime import date, datetime, timedelta
from typing import List, Tuple, Optional


def extract_spreadsheet_key(url: str) -> str:
    url = (url or "").strip()

    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", url):
        return url

    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    m = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if m:
        return m.group(1)

    raise ValueError(f"Link Gantt non valido: impossibile estrarre la key. Valore letto: {url}")


def gs_serial_to_date(serial: float) -> date:
    """Google Sheets date serial: days since 1899-12-30."""
    base = date(1899, 12, 30)
    return base + timedelta(days=int(serial))


def _get_cell(sheet_api, spreadsheet_id: str, a1: str, value_render_option: str) -> Optional[str]:
    res = sheet_api.values().get(
        spreadsheetId=spreadsheet_id,
        range=a1,
        valueRenderOption=value_render_option,
    ).execute()

    vals = res.get("values", [])
    if not vals or not vals[0]:
        return None
    return vals[0][0]


def read_start_date(service, spreadsheet_id: str, worksheet_title: str, debug: bool = False) -> date:
    """
    Legge la data inizio progetto da F9 in modo robusto:
    - prova UNFORMATTED_VALUE (seriale numerico) -> conversione
    - fallback parsing stringa dd/mm, dd/mm/yy, dd/mm/yyyy, ISO
    """
    sheet_api = service.spreadsheets()

    # 1) seriale
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

    # 2) stringa
    raw = _get_cell(sheet_api, spreadsheet_id, f"{worksheet_title}!F9", "FORMATTED_VALUE")
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

    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        raise ValueError(f"Formato data inizio (F9) non supportato: {raw}")


def parse_deadline_value(v, today: date) -> date:
    """
    Converte scadenza che può arrivare come:
    - seriale numerico (UNFORMATTED o anche stringa numerica)
    - stringa "dd/mm" o "dd/mm/yy" o "dd/mm/yyyy"
    Se manca l'anno (dd/mm):
      - interpreta come "prossima occorrenza" rispetto a today
        (se già passata quest'anno -> anno+1)
    """
    if v is None:
        raise ValueError("Scadenza vuota")

    s = str(v).strip()
    if not s:
        raise ValueError("Scadenza vuota")

    # seriale
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

        candidate = date(today.year, m_i, d_i)
        if candidate < today:
            candidate = date(today.year + 1, m_i, d_i)
        return candidate

    raise ValueError(f"Formato scadenza non riconosciuto: {s}")


def parse_duration_days(v) -> int:
    """Durata in giorni: sempre numerica in colonna D (può arrivare come 3 o 3.0)."""
    if v is None:
        raise ValueError("Durata vuota")
    s = str(v).strip()
    if not s:
        raise ValueError("Durata vuota")
    return int(float(s))


def read_services_deadlines(
    service,
    gantt_url: str,
    worksheet_title: str = "GANTT",
    start_row: int = 9,
    max_rows: int = 1200,
    debug: bool = False,
) -> List[Tuple[str, str, int, date]]:
    """
    Ritorna lista:
      (AREA, NomeServizio, DurataGiorni, Scadenza)

    Riconoscimento AREA:
    - colonna B non vuota
    - colonna D (durata) vuota
    - colonna E (scadenza) vuota
    -> è un titolo area (es. "IT", "Marketing"...)

    Colonne lette:
      B = nome area / nome servizio
      D = durata
      E = scadenza
    """
    key = extract_spreadsheet_key(gantt_url)
    sheet_api = service.spreadsheets()

    _ = read_start_date(service, key, worksheet_title, debug=debug)

    end_row = start_row + max_rows - 1
    rng = f"{worksheet_title}!B{start_row}:E{end_row}"

    res = sheet_api.values().get(
        spreadsheetId=key,
        range=rng,
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()

    values = res.get("values", [])

    out: List[Tuple[str, str, int, date]] = []
    current_area = "Generale"
    today = date.today()

    for row in values:
        while len(row) < 4:
            row.append("")

        nome = (row[0] or "").strip()  # B
        durata_raw = row[2]            # D
        scad_raw = row[3]              # E

        durata_str = str(durata_raw).strip() if durata_raw is not None else ""
        scad_str = str(scad_raw).strip() if scad_raw is not None else ""

        # righe completamente vuote
        if not nome and not durata_str and not scad_str:
            continue

        # header
        if nome.lower() == "nome area":
            continue

        # riga AREA
        if nome and not durata_str and not scad_str:
            current_area = nome
            continue

        # riga servizio valida
        if not nome or not durata_str or not scad_str:
            continue

        try:
            durata = parse_duration_days(durata_raw)
            scad = parse_deadline_value(scad_raw, today)
            out.append((current_area, nome, durata, scad))
        except Exception:
            # una riga sporca non deve bloccare tutto
            continue

    return out
