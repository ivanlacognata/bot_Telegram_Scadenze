# topic_registry.py
import json
import os
from typing import Optional, Dict


def _path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "topic_map.json")


def _norm_area(area: str) -> str:
    """Normalizza il nome area per evitare duplicati tipo 'IT' vs ' IT '."""
    return (area or "").strip()


def load_map() -> Dict[str, Dict[str, int]]:
    """
    Struttura:
      {
        "<chat_id>": {
          "IT": 12345,
          "Marketing": 67890
        }
      }
    """
    p = _path()
    if not os.path.exists(p):
        return {}

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            # garantisce che i thread_id siano int
            out: Dict[str, Dict[str, int]] = {}
            for chat_id, areas in (data or {}).items():
                out[str(chat_id)] = {str(k): int(v) for k, v in (areas or {}).items()}
            return out
    except Exception:
        # file corrotto o non leggibile: riparto vuoto
        return {}


def save_map(m: Dict[str, Dict[str, int]]) -> None:
    """
    Scrittura atomica: salva in .tmp e poi replace.
    Evita corruzione se il processo si interrompe durante la scrittura.
    """
    p = _path()
    tmp = p + ".tmp"

    os.makedirs(os.path.dirname(p), exist_ok=True)

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

    os.replace(tmp, p)


def set_topic(chat_id: int, area: str, thread_id: int) -> None:
    m = load_map()
    chat_key = str(chat_id)
    area_key = _norm_area(area)
    if not area_key:
        return

    m.setdefault(chat_key, {})
    m[chat_key][area_key] = int(thread_id)
    save_map(m)


def get_topic(chat_id: int, area: str) -> Optional[int]:
    m = load_map()
    chat_key = str(chat_id)
    area_key = _norm_area(area)
    if not area_key:
        return None
    return m.get(chat_key, {}).get(area_key)


def rename_area_by_thread(chat_id: int, thread_id: int, new_area: str) -> bool:
    m = load_map()
    chat_key = str(chat_id)
    new_area_key = _norm_area(new_area)
    if not new_area_key:
        return False

    if chat_key not in m:
        return False

    # trova la vecchia area associata a thread_id
    old_area = None
    for area, tid in m[chat_key].items():
        if int(tid) == int(thread_id):
            old_area = area
            break

    if old_area is None:
        return False

    if old_area == new_area_key:
        return True

    # aggiorna chiave
    m[chat_key].pop(old_area, None)
    m[chat_key][new_area_key] = int(thread_id)
    save_map(m)
    return True
