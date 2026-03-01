# main.py (python-telegram-bot v20+)

# ================================
# IMPORT
# ================================

# Librerie standard Python
from datetime import date, time as dtime
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo  # gestione timezone (Python 3.9+)

# Librerie Telegram (python-telegram-bot v20+)
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

# Moduli interni del progetto
import googleSheetRead as gs               # lettura foglio di configurazione
from gantt_reader import read_services_deadlines  # lettura servizi dal Gantt
import topic_registry as tr                # gestione mapping area -> topic_id


# ================================
# CONFIGURAZIONE PRINCIPALE
# ================================

# Token del bot Telegram (ottenuto da BotFather)
TOKEN = "8206230317:AAFOu75hERY8s-siVMuvH95g7JMUNdVJFlI"

# Chat dove inviare eventuali errori (può essere gruppo log o utente admin)
ERROR_CHAT_ID = -1003492993374  # ⚠️ impostare correttamente in produzione

# Orario giornaliero di invio (formato HH:MM)
MESSAGE_TIME = "18:15"

# Timezone ufficiale del progetto
TZ = ZoneInfo("Europe/Rome")


# ============================================================
# UTILITY: GESTIONE SOGLIE AVVISI (logica business principale)
# ============================================================

def parse_custom_days(raw: str) -> set[int]:
    """
    Converte una stringa tipo "7,5,4" in un set di interi {7,5,4}.
    Valori non numerici o celle vuote vengono ignorati.
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
    Calcola le soglie di invio per un servizio.

    Standard:
    - metà durata (ceil(d/2))
    - 1 giorno prima
    - giorno stesso
    - giorno dopo (-1)

    + eventuali soglie custom inserite nel foglio config.
    """
    half = (duration_days + 1) // 2  # ceil(d/2)
    return {half, 1, 0, -1} | custom_days


def label_for_days_left(days_left: int) -> str:
    """
    Restituisce etichetta leggibile per Telegram
    in base ai giorni mancanti.
    """
    if days_left == -1:
        return "🟥 Scaduto IERI"
    if days_left == 0:
        return "🟥 In scadenza OGGI"
    if days_left == 1:
        return "🟧 Scade DOMANI"
    return f"🟨 Scade tra {days_left} giorni"


def build_message(project_name: str, area: str, gantt_url: str, grouped: dict) -> str:
    """
    Costruisce il messaggio Telegram finale.

    grouped: dict nel formato:
        days_left -> [(nome_servizio, data_scadenza), ...]

    Genera un messaggio unico per ogni area.
    """
    lines = [
        "⏰ PROMEMORIA SCADENZE",
        f"📌 Progetto: {project_name}",
        f"🏷️ Area: {area}",
        "",
    ]

    for days_left in sorted(grouped.keys()):
        lines.append(label_for_days_left(days_left))
        for name, dline in grouped[days_left]:
            lines.append(f" • {name} — {dline.strftime('%d/%m/%Y')}")
        lines.append("")

    return "\n".join(lines).strip()


# ============================================================
# INVIO MESSAGGI (gestione topic o generale)
# ============================================================

async def send_to_group_or_topic(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    area: str,
    text: str,
):
    """
    Invia il messaggio:
    - nel topic corretto se esiste un mapping area -> topic_id
    - nel generale del gruppo altrimenti
    """
    topic_id = tr.get_topic(chat_id, area)

    if topic_id is None:
        await context.bot.send_message(chat_id=chat_id, text=text)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=topic_id,
            text=text
        )


# ============================================================
# JOB PRINCIPALE: CONTROLLO SCADENZE
# ============================================================

async def check_deadlines_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Funzione eseguita ogni giorno all'orario MESSAGE_TIME.
    1) Legge foglio configurazione
    2) Per ogni progetto legge il Gantt
    3) Calcola soglie
    4) Invia messaggi per area
    """
    print(f"✅ check_deadlines_job avviato ({date.today()})")

    # Lettura foglio di configurazione
    data, sheet_api, service = gs.export_data()

    # Se errore nella lettura config
    if data == -1 or sheet_api is None or service is None:
        try:
            await context.bot.send_message(
                chat_id=ERROR_CHAT_ID,
                text="⚠️ Errore: impossibile leggere il foglio di configurazione."
            )
        except Exception as e2:
            print("❌ Errore invio su ERROR_CHAT_ID:", type(e2).__name__, e2)
        return

    today = date.today()
    sent_messages = 0
    total_projects = 0

    # Ciclo su ogni progetto configurato
    for idx, entry in enumerate(data):
        try:
            project_name = (entry.get("Nome", "") or "").strip()
            chat_id_raw = (entry.get("ChatId", "") or "").strip()
            gantt_url = (entry.get("Gantt", "") or entry.get("Gannt", "") or "").strip()
            giorni_avviso_raw = (
                entry.get("Giorni_Avviso", "")
                or entry.get("Giorni_avviso", "")
                or ""
            ).strip()

            # Salta righe incomplete
            if not project_name or not chat_id_raw or not gantt_url:
                continue

            # Evita header ripetuti o valori non validi
            if not chat_id_raw.lstrip("-").isdigit():
                continue

            chat_id = int(chat_id_raw)
            custom_days = parse_custom_days(giorni_avviso_raw)
            total_projects += 1

            # Lettura servizi dal Gantt
            services = read_services_deadlines(service, gantt_url)

            # Struttura: area -> days_left -> lista servizi
            per_area: Dict[str, Dict[int, List[Tuple[str, date]]]] = {}

            for area, service_name, duration_days, deadline in services:
                days_left = (deadline - today).days
                thresholds = thresholds_for_service(duration_days, custom_days)

                if days_left in thresholds:
                    per_area.setdefault(area, {})
                    per_area[area].setdefault(days_left, [])
                    per_area[area][days_left].append((service_name, deadline))

            # Invio un messaggio per area
            for area, grouped in per_area.items():
                msg = build_message(project_name, area, gantt_url, grouped)
                await send_to_group_or_topic(context, chat_id, area, msg)
                sent_messages += 1

        except Exception as e:
            print(f"❌ ERRORE riga config {idx+2}: {type(e).__name__}: {e}")
            try:
                await context.bot.send_message(
                    chat_id=ERROR_CHAT_ID,
                    text=f"⚠️ Errore riga config {idx+2}: {type(e).__name__}: {e}"
                )
            except Exception as e2:
                print("❌ Errore invio su ERROR_CHAT_ID:", type(e2).__name__, e2)

    print(
        f"✅ Job completato: progetti_processati={total_projects}, "
        f"messaggi_inviati={sent_messages}"
    )


# ============================================================
# GESTIONE AUTOMATICA TOPIC (creazione e rename)
# ============================================================

async def on_forum_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Gestisce:
    - Creazione nuovo topic → salva mapping area -> topic_id
    - Rinomina topic → aggiorna mapping
    """
    msg = update.effective_message
    chat = update.effective_chat

    if not msg or not chat:
        return

    thread_id = getattr(msg, "message_thread_id", None)
    if thread_id is None:
        return

    # Topic creato
    if msg.forum_topic_created:
        name = msg.forum_topic_created.name.strip()
        tr.set_topic(chat.id, name, thread_id)
        print(f"✅ Topic creato auto-registrato: '{name}' -> {thread_id}")
        return

    # Topic rinominato
    if msg.forum_topic_edited and msg.forum_topic_edited.name:
        new_name = msg.forum_topic_edited.name.strip()
        tr.rename_area_by_thread(chat.id, thread_id, new_name)
        print(f"✅ Topic rinominato aggiornato: '{new_name}' (thread {thread_id})")
        return


# ============================================================
# COMANDI BOT
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start."""
    await update.effective_message.reply_text(
        "Bot scadenze attivo.\n"
        "Usa /register_area NOME_AREA dentro un topic per mappare un'area."
    )


async def register_area(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando manuale per mappare un'area a un topic.
    Va eseguito DENTRO il topic.
    """
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


# ============================================================
# UTILITA' ORARIO SCHEDULER
# ============================================================

def parse_hhmm(s: str) -> dtime:
    """
    Converte stringa "HH:MM" in oggetto datetime.time con timezone.
    """
    hh, mm = s.split(":")
    return dtime(hour=int(hh), minute=int(mm), tzinfo=TZ)


# ============================================================
# ENTRY POINT PRINCIPALE
# ============================================================

def main():
    """
    Inizializza il bot, registra handler e avvia scheduler.
    """
    defaults = Defaults(tzinfo=TZ)
    app = ApplicationBuilder().token(TOKEN).defaults(defaults).build()

    # Handler comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register_area", register_area))

    # Handler eventi forum (creazione/rinomina topic)
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, on_forum_events))

    if app.job_queue is None:
        print("❌ JobQueue non disponibile. Installare: pip install 'python-telegram-bot[job-queue]'")
    else:
        # Job giornaliero
        t = parse_hhmm(MESSAGE_TIME)
        app.job_queue.run_daily(check_deadlines_job, time=t)

        print(f"✅ Scheduler attivo: invio giornaliero alle {MESSAGE_TIME} ({TZ})")

    # Avvio bot in modalità polling
    app.run_polling()


if __name__ == "__main__":
    main()