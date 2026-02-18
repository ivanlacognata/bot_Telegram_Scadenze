# main.py (python-telegram-bot v20+)
from datetime import date, time as dtime
from typing import Dict, List, Tuple

from zoneinfo import ZoneInfo

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

TOKEN = "8206230317:AAFOu75hERY8s-siVMuvH95g7JMUNdVJFlI"
ERROR_CHAT_ID = -1001234567890  # metti un gruppo dove il bot è dentro, o il tuo user id
MESSAGE_TIME = "00:01"          # HH:MM in Europe/Rome
TZ = ZoneInfo("Europe/Rome")


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
        return "🟥 Scaduto IERI (-1)"
    if days_left == 0:
        return "🟥 Scade OGGI (0)"
    if days_left == 1:
        return "🟧 Scade DOMANI (1)"
    return f"🟨 Scade tra {days_left} giorni"


def build_message(project_name: str, area: str, gantt_url: str, grouped: dict) -> str:
    """
    grouped: dict days_left -> list[(service_name, deadline_date)]
    """
    lines = [
        "⏰ PROMEMORIA SCADENZE SERVIZI",
        f"📌 Progetto: {project_name}",
        f"🏷️ Area: {area}",
        "",
    ]

    for days_left in sorted(grouped.keys()):
        lines.append(label_for_days_left(days_left))
        for name, dline in grouped[days_left]:
            lines.append(f"• {name} — {dline.strftime('%d/%m/%Y')}")
        lines.append("")

    lines.append(f"📎 Gantt: {gantt_url}")
    return "\n".join(lines).strip()


# -----------------------
# Invio su topic o generale
# -----------------------
async def send_to_group_or_topic(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    area: str,
    text: str,
):
    topic_id = tr.get_topic(chat_id, area)
    if topic_id is None:
        await context.bot.send_message(chat_id=chat_id, text=text)
    else:
        await context.bot.send_message(chat_id=chat_id, message_thread_id=topic_id, text=text)


# -----------------------
# Job: controllo scadenze
# -----------------------
async def check_deadlines_job(context: ContextTypes.DEFAULT_TYPE):

    data, sheet, client = gs.export_data()
    if data == -1 or sheet is None or client is None:
        # durante debug: stampa sempre
        print("❌ Errore: impossibile leggere il foglio di configurazione.")
        try:
            await context.bot.send_message(
                chat_id=ERROR_CHAT_ID,
                text="⚠️ Errore: impossibile leggere il foglio di configurazione.",
            )
        except Exception as e2:
            print("❌ Non riesco a scrivere su ERROR_CHAT_ID:", e2)
        return

    today = date.today()

    for idx, entry in enumerate(data):
        try:
            project_name = (entry.get("Nome", "") or "").strip()
            chat_id_raw = (entry.get("ChatId", "") or "").strip()
            gantt_url = (entry.get("Gannt", "") or "").strip()
            giorni_avviso_raw = (entry.get("Giorni_Avviso", "") or "").strip()

            if not project_name or not chat_id_raw or not gantt_url:
                continue

            chat_id = int(chat_id_raw)
            custom_days = parse_custom_days(giorni_avviso_raw)

            # servizi: (area, service_name, duration_days, deadline_date)
            services = read_services_deadlines(client, gantt_url)

            # raggruppa: area -> days_left -> [(service, deadline)]
            per_area: Dict[str, Dict[int, List[Tuple[str, date]]]] = {}

            for area, service_name, duration_days, deadline in services:
                days_left = (deadline - today).days
                thresholds = thresholds_for_service(duration_days, custom_days)

                if days_left in thresholds:
                    per_area.setdefault(area, {})
                    per_area[area].setdefault(days_left, [])
                    per_area[area][days_left].append((service_name, deadline))

            # invia 1 messaggio per area (quindi topic diverso)
            for area, grouped in per_area.items():
                msg = build_message(project_name, area, gantt_url, grouped)
                await send_to_group_or_topic(context, chat_id, area, msg)

        except Exception as e:
            print(f"❌ ERRORE riga config {idx+2}: {type(e).__name__}: {e}")
            try:
                await context.bot.send_message(
                    chat_id=ERROR_CHAT_ID,
                    text=f"⚠️ Errore riga config {idx+2}: {type(e).__name__}: {e}",
                )
            except Exception as e2:
                print("❌ Non riesco a scrivere su ERROR_CHAT_ID:", e2)


# -----------------------
# Auto-register / auto-rename topic
# -----------------------
async def on_forum_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    chat = update.effective_chat
    if not chat:
        return

    thread_id = getattr(msg, "message_thread_id", None)
    if thread_id is None:
        return

    # topic creato -> salva nome topic come area
    if msg.forum_topic_created:
        name = msg.forum_topic_created.name.strip()
        tr.set_topic(chat.id, name, thread_id)
        print(f"✅ Auto-registrato topic creato: '{name}' -> {thread_id}")
        return

    # topic rinominato -> aggiorna area associata a quel thread_id
    if msg.forum_topic_edited and msg.forum_topic_edited.name:
        new_name = msg.forum_topic_edited.name.strip()
        tr.rename_area_by_thread(chat.id, thread_id, new_name)
        print(f"✅ Auto-aggiornato topic rinominato -> '{new_name}' (thread {thread_id})")
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

    print("job_queue =", app.job_queue)

    # Handler comandi
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register_area", register_area))

    # Handler service messages topic create/rename
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, on_forum_events))

    if app.job_queue is None:
        print("❌ JobQueue è None. Installa: pip install 'python-telegram-bot[job-queue]'")
    else:
        # Test immediato all'avvio (puoi commentare quando sei sicuro)
        #app.job_queue.run_once(check_deadlines_job, when=1)

        # Job giornaliero
        t = parse_hhmm(MESSAGE_TIME)
        app.job_queue.run_daily(check_deadlines_job, time=t)

    app.run_polling()


if __name__ == "__main__":
    main()
