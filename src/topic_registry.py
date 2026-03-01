# topic_registry.py

# ============================================================
# GESTIONE MAPPATURA AREA -> THREAD_ID (TOPIC TELEGRAM)
# ============================================================
#
# Questo file gestisce la persistenza locale della mappatura:
#
#   chat_id  →  area  →  thread_id
#
# Serve per sapere in quale topic (thread_id) inviare i messaggi
# relativi a una determinata area (IT, Marketing, Sales, ecc.).
#
# I dati vengono salvati in un file JSON locale: topic_map.json
# nella stessa directory del file.
#
# Struttura JSON:
#
# {
#   "<chat_id>": {
#       "IT": 12345,
#       "M&C": 67890,
#        ecc.
#   }
# }
#
# ============================================================

import json
import os
from typing import Optional, Dict


# ============================================================
# PERCORSO FILE JSON
# ============================================================

def _path() -> str:
    """
    Restituisce il percorso assoluto del file topic_map.json.
    Il file viene salvato nella stessa directory di questo script.
    """
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "topic_map.json")


# ============================================================
# NORMALIZZAZIONE NOME AREA
# ============================================================

def _norm_area(area: str) -> str:
    """
    Normalizza il nome area per evitare duplicati dovuti a spazi.
    Esempio:
      " IT " → "IT"
    """
    return (area or "").strip()


# ============================================================
# LETTURA MAPPATURA DA FILE
# ============================================================

def load_map() -> Dict[str, Dict[str, int]]:
    """
    Carica la mappatura da topic_map.json.

    Ritorna:
      Dict[str, Dict[str, int]]

    Se il file non esiste → ritorna dict vuoto.
    Se il file è corrotto → ritorna dict vuoto (fail-safe).
    """
    p = _path()

    if not os.path.exists(p):
        return {}

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

            # Garantisce che:
            # - chat_id sia stringa
            # - area sia stringa
            # - thread_id sia int
            out: Dict[str, Dict[str, int]] = {}

            for chat_id, areas in (data or {}).items():
                out[str(chat_id)] = {
                    str(k): int(v) for k, v in (areas or {}).items()
                }

            return out

    except Exception:
        # Se il file è corrotto o non leggibile
        # ripartiamo da mappa vuota (evita crash del bot)
        return {}


# ============================================================
# SCRITTURA MAPPATURA (ATOMIC WRITE)
# ============================================================

def save_map(m: Dict[str, Dict[str, int]]) -> None:
    """
    Salva la mappatura su file in modo atomico.

    Scrittura atomica:
      1) Scrive su file temporaneo (.tmp)
      2) Sostituisce il file originale con os.replace()

    Questo evita la corruzione del JSON se il processo
    viene interrotto durante la scrittura.
    """
    p = _path()
    tmp = p + ".tmp"

    # Assicura che la directory esista
    os.makedirs(os.path.dirname(p), exist_ok=True)

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    # Replace atomico
    os.replace(tmp, p)


# ============================================================
# SET TOPIC
# ============================================================

def set_topic(chat_id: int, area: str, thread_id: int) -> None:
    """
    Associa un'area a un thread_id per un determinato gruppo (chat_id).

    Se l'area esiste già → viene aggiornata.
    Se non esiste → viene creata.
    """
    m = load_map()

    chat_key = str(chat_id)
    area_key = _norm_area(area)

    # Evita inserimento area vuota
    if not area_key:
        return

    m.setdefault(chat_key, {})
    m[chat_key][area_key] = int(thread_id)

    save_map(m)


# ============================================================
# GET TOPIC
# ============================================================

def get_topic(chat_id: int, area: str) -> Optional[int]:
    """
    Restituisce il thread_id associato a:
        (chat_id, area)

    Se non esiste → ritorna None.
    """
    m = load_map()

    chat_key = str(chat_id)
    area_key = _norm_area(area)

    if not area_key:
        return None

    return m.get(chat_key, {}).get(area_key)


# ============================================================
# RENAME AREA QUANDO UN TOPIC CAMBIA NOME
# ============================================================

def rename_area_by_thread(chat_id: int, thread_id: int, new_area: str) -> bool:
    """
    Aggiorna il nome area quando un topic Telegram viene rinominato.

    Logica:
      - Cerca l'area che aveva quel thread_id
      - Se trovata:
          - Rimuove la vecchia chiave
          - Inserisce nuova chiave con stesso thread_id

    Ritorna:
      True  → aggiornamento effettuato
      False → nessuna area trovata o input non valido
    """
    m = load_map()

    chat_key = str(chat_id)
    new_area_key = _norm_area(new_area)

    if not new_area_key:
        return False

    if chat_key not in m:
        return False

    # Trova la vecchia area associata a questo thread_id
    old_area = None

    for area, tid in m[chat_key].items():
        if int(tid) == int(thread_id):
            old_area = area
            break

    if old_area is None:
        return False

    # Se il nome non è cambiato, non serve fare nulla
    if old_area == new_area_key:
        return True

    # Aggiornamento chiave
    m[chat_key].pop(old_area, None)
    m[chat_key][new_area_key] = int(thread_id)

    save_map(m)

    return True