# main.py (python-telegram-bot v20+)
from datetime import date, time as dtime
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import os

load_dotenv()

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

import googleSheetRead as gs
from gantt_reader import read_services_deadlines
import topic_registry as tr

import random

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ERROR_CHAT_ID = int(os.getenv("ERROR_CHAT_ID"))

MESSAGE_TIME = os.getenv("MESSAGE_TIME", "15:00")
TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Rome"))


# --------------------------------------
# Messaggi personalizzabili per gravità
# --------------------------------------

OVERDUE_MESSAGES = [
    "Spero che abbiate già consegnato, altrimenti GUAI",
    "Non c'è più nulla da fare...",
    "Ormai è troppo tardi...",
    "Vediamo chi verrà eliminato oggi",
]

TODAY_MESSAGES = [
    "Meno di 24 ore alla fine dei giochi",
    "Spero per voi che abbiate già finito...",
    "Non so se vi siete accorti di che giorno è oggi"
    "Prevedo qualche richiamo formale...",
    "Questo... è l'endgame",
]

TOMORROW_MESSAGES = [
    "Dovreste già aver finito, altrimenti...",
    "Il cliente nonn sarà felice di sapere che non avete ancora finito",
    "Dovreste darvi una mossa",
    "La scadenza è già domani e non avete ancora finito, sarà per i postumi dell'AperiJEToP?",
    "Ultimo sforzo per un progetto che sarà leggen...aspetta...DARIO",
]

SOON_MESSAGES = [
    "Dovreste iniziare a preoccuparvi",
    "Sarebbe meglio per voi essere già a buon punto",
    "Se qualcuno non dovesse aver finito entro la scadenza, prenderò seri provvedimenti\n~ Presidente (lo giuro)",
    "Il tesoriere si aspetta quei soldi nel bilancio finale, non deludetelo",
    "La data si avvicina, e anche il prossimo aperiJEToP",
    "Vi conviene darvi una mossa",
    "Sbrigatevi, non vorrete che vada a finire come il JEIMM..."
]

DEFAULT_MESSAGES = [
    "Per ora state tranquilli, ma non troppo",
    "Il cliente può ancora aspettare",
    "Non illudetevi, presto sarà troppo tardi",
    "Avete ancora tempo di andare a bere da qualche parte, però dopo tornate a lavorare",
    "C'è davvero qualcuno che legge queste frasi?",
    "Il Giappone trasforma i passi in elettricità! ⚡ Grazie alle piastrelle piezoelettriche, ogni passo genera una piccola quantità di energia. Milioni di passi insieme possono alimentare luci e display a LED in luoghi affollati come la stazione di Shibuya. Un modo brillante per creare una città sostenibile e intelligente: trasformare il movimento in energia pulita e rinnovabile 🌱💡",
    "Siamo JEToP perché siamo i più forti... o siamo i più forti perché siamo JEToP?"
    "Non importa che tu sia un leone o una gazzella, l'importante è che se muori me lo dici prima",
    "Chi ha paura muore ogni giorno, chi non ha paura va al CUS senza prenotazione",
    "Se ti è spuntato questo messaggio congratulazioni, hai vinto un abbraccio❤️",
    "Due cose sono infinite: l’universo e le modifiche richieste dai clienti, ma riguardo l’universo ho ancora dei dubbi."
]

# Classifica la "gravità" delle scadenze per i messaggi personalizzati
def get_severity_messages(days_left: int) -> list[str]:
    """
    Restituisce la lista base di frasi in base alla gravità.
    """
    if days_left < 0:
        return OVERDUE_MESSAGES.copy()
    if days_left == 0:
        return TODAY_MESSAGES.copy()
    if days_left == 1:
        return TOMORROW_MESSAGES.copy()
    if days_left < 5:
        return SOON_MESSAGES.copy()
    return DEFAULT_MESSAGES.copy()


# Aggiunge condizioni extra per i messaggi in base al topic
def extend_conditional_messages(messages: list[str], area: str, days_left: int) -> list[str]:
    """
    Aggiunge frasi extra in base a condizioni personalizzate.
    """
    area_clean = (area or "").strip()

    # Esempio: aggiungi frasi solo se l'area NON è IT o Web
    if area_clean not in {"IT", "Web"}:
        messages.extend([
            "Un IT avrebbe già finito...",
            "Un IT farebbe decisamente di meglio",
            "Credo ci siano pochi IT qui in mezzo...",
        ])
    return messages


# Sceglie la frase a caso 
def get_random_fun_message(area: str, days_left: int) -> str:
    """
    Costruisce la lista finale di frasi candidate e ne sceglie una a caso.
    """
    candidates = get_severity_messages(days_left)
    candidates = extend_conditional_messages(candidates, area, days_left)

    if not candidates:
        candidates = DEFAULT_MESSAGES

    return random.choice(candidates)


# -----------------------
# Utility: soglie avvisi
# -----------------------
def parse_custom_days(raw: str) -> set[int]:
    """
    "7,5,4" -> {7,5,4}
    Celle vuote/valori non numerici -> ignorati
    """
    if not raw:
        return set()
    raw = str(raw).strip()
    if not raw:
        return set()

    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except Exception:
            continue
    return out


def thresholds_for_service(duration_days: int, custom_days: set[int]) -> set[int]:
    """
    Standard:
      - metà: ceil(d/2)
      - giorno prima: 1
      - giorno stesso: 0
      - giorno dopo: -1
    + custom days dal foglio config (es. 7,5,4)
    """
    half = (duration_days + 1) // 2  # ceil(d/2)
    return {half, 1, 0, -1} | custom_days


def label_for_days_left(days_left: int) -> str:
    if days_left == -1:
        return "🟥 Scaduto IERI"
    if days_left == 0:
        return "🟥 In scadenza OGGI"
    if days_left == 1:
        return "🟧 Scade DOMANI"
    return f"🟨 Scade tra {days_left} giorni"


def build_message(project_name: str, area: str, gantt_url: str, grouped: dict) -> str:
    """
    grouped: dict days_left -> list[(service_name, deadline_date, service_area)]
    """
    lines = [
        "⏰ PROMEMORIA SCADENZE",
        f"📌 Progetto: {project_name}",
    ]

    for days_left in sorted(grouped.keys()):
        lines.append(label_for_days_left(days_left))
        for name, dline, service_area in grouped[days_left]:
            fun_line = get_random_fun_message(service_area, days_left)
            lines.append(f" 🏷️ {name} — {dline.strftime('%d/%m/%Y')}")
            lines.append(f"    💬 {fun_line}")
        lines.append("")

    return "\n".join(lines).strip()


def parse_topic_destination(raw: str) -> tuple[str, int | None]:
    """
    Interpreta il campo 'Topic_Destinazione' dal foglio config.

    Supporta:
    - "" (vuoto) -> ("", None)  => nessun override
    - "Generale" -> ("generale", None) => invia nel generale
    - "IT" / "Marketing" -> ("IT", None) => invia nel topic con quel nome (via topic_registry)
    - "4" (numero) -> ("", 4) => invia direttamente nel thread_id 4 (senza lookup)
    """
    if not raw:
        return "", None

    s = str(raw).strip()
    if not s:
        return "", None

    # se è numerico -> thread_id esplicito
    if s.lstrip("-").isdigit():
        try:
            return "", int(s)
        except Exception:
            return "", None

    return s, None


# -----------------------
# Invio su topic o generale
# -----------------------
async def send_to_group_or_topic(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    area_or_topic_name: str,
    text: str,
    forced_thread_id: int | None = None,
):
    """
    Invia messaggio:
    - se forced_thread_id è dato: invia in quel thread_id
    - altrimenti prova lookup area/topic_name -> thread_id (topic_registry)
    - fallback nel generale
    """
    if forced_thread_id is not None:
        await context.bot.send_message(chat_id=chat_id, message_thread_id=forced_thread_id, text=text)
        return

    topic_id = tr.get_topic(chat_id, area_or_topic_name)
    if topic_id is None:
        await context.bot.send_message(chat_id=chat_id, text=text)
    else:
        await context.bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=text)


# -----------------------
# Job: controllo scadenze
# -----------------------
async def check_deadlines_job(context: ContextTypes.DEFAULT_TYPE):
    print(f"✅ check_deadlines_job avviato ({date.today()})")

    data, sheet_api, service = gs.export_data()
    if data == -1 or sheet_api is None or service is None:
        # errore già stampato da export_data(), qui notifichiamo soltanto
        try:
            await context.bot.send_message(
                chat_id=ERROR_CHAT_ID,
                text="⚠️ Errore: impossibile leggere il foglio di configurazione (export_data fallita)."
            )
        except Exception as e2:
            print("❌ Non riesco a inviare su ERROR_CHAT_ID:", type(e2).__name__, e2)
        return

    today = date.today()
    sent_messages = 0
    total_projects = 0

    for idx, entry in enumerate(data):
        try:
            project_name = (entry.get("Nome", "") or "").strip()
            chat_id_raw = (entry.get("ChatId", "") or "").strip()
            gantt_url = (entry.get("Gantt", "") or entry.get("Gannt", "") or "").strip()
            giorni_avviso_raw = (entry.get("Giorni_Avviso", "") or entry.get("Giorni_avviso", "") or "").strip()

            # NUOVO: override destinazione
            topic_dest_raw = (entry.get("Topic_Destinazione", "") or "").strip()

            # riga non valida
            if not project_name or not chat_id_raw or not gantt_url:
                continue

            # evita righe “spazzatura” tipo header ripetuti
            if not chat_id_raw.lstrip("-").isdigit():
                continue

            chat_id = int(chat_id_raw)
            custom_days = parse_custom_days(giorni_avviso_raw)
            total_projects += 1

            # parse override destinazione
            topic_dest_name, forced_thread_id = parse_topic_destination(topic_dest_raw)

            services = read_services_deadlines(service, gantt_url)

            # area -> days_left -> list[(service_name, deadline)]
            per_area: Dict[str, Dict[int, List[Tuple[str, date]]]] = {}

            for area, service_name, duration_days, deadline in services:
                days_left = (deadline - today).days
                thresholds = thresholds_for_service(duration_days, custom_days)

                if days_left in thresholds:
                    per_area.setdefault(area, {})
                    per_area[area].setdefault(days_left, [])
                    per_area[area][days_left].append((service_name, deadline, area))

            # -----------------------------------------
            # INVIO: due modalità
            # -----------------------------------------
            # 1) Se Topic_Destinazione è VUOTO -> modalità classica: un messaggio per area
            if not topic_dest_raw:
                for area, grouped in per_area.items():
                    msg = build_message(project_name, area, gantt_url, grouped)
                    await send_to_group_or_topic(context, chat_id, area, msg)
                    sent_messages += 1

            # 2) Se Topic_Destinazione è COMPILATO -> manda TUTTO in un'unica destinazione
            else:
                # unisco tutti i servizi di tutte le aree in un unico grouped
                grouped_all: Dict[int, List[Tuple[str, date]]] = {}
                for area, grouped in per_area.items():
                    for days_left, items in grouped.items():
                        grouped_all.setdefault(days_left, [])
                        # Prefix area per chiarezza quando si invia tutto insieme
                        grouped_all[days_left].extend([(f"[{item_area}] {name}", dline, item_area) for name, dline, item_area in items])
                
                # se oggi non c'è nulla da avvisare, non invio nulla
                if grouped_all:
                    # etichetta "area" nel messaggio: usiamo il nome del topic destinazione (o "Generale")
                    label = topic_dest_name if topic_dest_name else (topic_dest_raw or "Generale")
                    msg = build_message(project_name, label, gantt_url, grouped_all)

                    # se scrivono "Generale" -> invia nel generale (nessun topic)
                    if topic_dest_raw.strip().lower() == "generale":
                        await context.bot.send_message(chat_id=chat_id, text=msg)
                    else:
                        # invia nel topic indicato (nome) o nel forced thread_id numerico
                        await send_to_group_or_topic(
                            context,
                            chat_id,
                            topic_dest_name if topic_dest_name else label,
                            msg,
                            forced_thread_id=forced_thread_id,
                        )
                    sent_messages += 1

        except Exception as e:
            print(f"❌ ERRORE riga config {idx+2}: {type(e).__name__}: {e}")
            try:
                await context.bot.send_message(
                    chat_id=ERROR_CHAT_ID,
                    text=f"⚠️ Errore riga config {idx+2}: {type(e).__name__}: {e}"
                )
            except Exception as e2:
                print("❌ Non riesco a inviare su ERROR_CHAT_ID:", type(e2).__name__, e2)

    print(f"✅ Job completato: progetti_processati={total_projects}, messaggi_inviati={sent_messages}")


# -----------------------
# Auto-register / auto-rename topic
# -----------------------
async def on_forum_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return

    thread_id = getattr(msg, "message_thread_id", None)
    if thread_id is None:
        return

    if msg.forum_topic_created:
        name = msg.forum_topic_created.name.strip()
        tr.set_topic(chat.id, name, thread_id)
        print(f"✅ Topic creato auto-registrato: '{name}' -> {thread_id}")
        return

    if msg.forum_topic_edited and msg.forum_topic_edited.name:
        new_name = msg.forum_topic_edited.name.strip()
        tr.rename_area_by_thread(chat.id, thread_id, new_name)
        print(f"✅ Topic rinominato aggiornato: '{new_name}' (thread {thread_id})")
        return


# -----------------------
# Comandi
# -----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Bot scadenze attivo.\n"
        "Usa /register_area NOME_AREA dentro un topic per mappare un'area."
    )


async def register_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    thread_id = getattr(msg, "message_thread_id", None)

    if thread_id is None:
        await msg.reply_text("⚠️ Usa questo comando DENTRO un topic (forum).")
        return

    if not context.args:
        await msg.reply_text("Uso: /register_area NOME_AREA (es: /register_area IT)")
        return

    area = " ".join(context.args).strip()
    tr.set_topic(chat.id, area, thread_id)
    await msg.reply_text(f"✅ Registrato: area '{area}' → topic_id {thread_id}")


def parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")
    return dtime(hour=int(hh), minute=int(mm), tzinfo=TZ)


# -----------------------
# Main
# -----------------------
def main():
    defaults = Defaults(tzinfo=TZ)
    app = ApplicationBuilder().token(TOKEN).defaults(defaults).build()

    # Handler comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register_area", register_area))

    # Handler service messages topic create/rename
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, on_forum_events))

    if app.job_queue is None:
        print("❌ JobQueue è None. Installa: pip install 'python-telegram-bot[job-queue]'")
    else:
        # Job giornaliero
        t = parse_hhmm(MESSAGE_TIME)
        app.job_queue.run_daily(check_deadlines_job, time=t)

        # (opzionale) test immediato:
        # app.job_queue.run_once(check_deadlines_job, when=1)

        print(f"✅ Scheduler attivo: invio giornaliero alle {MESSAGE_TIME} ({TZ})")

    app.run_polling()


if __name__ == "__main__":
    main()