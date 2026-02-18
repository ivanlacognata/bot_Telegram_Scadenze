# topic_registry.py
import json
import os
from typing import Optional, Dict


def _path() -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "topic_map.json")


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
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_map(m: Dict[str, Dict[str, int]]) -> None:
    p = _path()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def set_topic(chat_id: int, area: str, thread_id: int) -> None:
    m = load_map()
    chat_key = str(chat_id)
    m.setdefault(chat_key, {})
    m[chat_key][area] = int(thread_id)
    save_map(m)


def get_topic(chat_id: int, area: str) -> Optional[int]:
    m = load_map()
    chat_key = str(chat_id)
    return m.get(chat_key, {}).get(area)


def rename_area_by_thread(chat_id: int, thread_id: int, new_area: str) -> bool:
    m = load_map()
    chat_key = str(chat_id)
    if chat_key not in m:
        return False

    # trova la vecchia area che aveva quel thread_id
    old_area = None
    for area, tid in m[chat_key].items():
        if int(tid) == int(thread_id):
            old_area = area
            break

    if old_area is None:
        return False

    # aggiorna chiave (area name)
    m[chat_key].pop(old_area, None)
    m[chat_key][new_area] = int(thread_id)
    save_map(m)
    return True
