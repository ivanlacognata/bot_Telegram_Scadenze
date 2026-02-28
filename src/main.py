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
ERROR_CHAT_ID = -1003492993374 # Quale usiamo?
MESSAGE_TIME = "15:26"         # Quale orario mettere?
TZ = ZoneInfo("Europe/Rome")


# -----------------------
# Utility: soglie avvisi
# -----------------------
def parse_custom_days(raw: str) -> set[int]:
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

            # riga non valida
            if not project_name or not chat_id_raw or not gantt_url:
                continue

            # evita righe “spazzatura” tipo header ripetuti
            if not chat_id_raw.lstrip("-").isdigit():
                continue

            chat_id = int(chat_id_raw)
            custom_days = parse_custom_days(giorni_avviso_raw)
            total_projects += 1

            services = read_services_deadlines(service, gantt_url)

            per_area: Dict[str, Dict[int, List[Tuple[str, date]]]] = {}

            for area, service_name, duration_days, deadline in services:
                days_left = (deadline - today).days
                thresholds = thresholds_for_service(duration_days, custom_days)

                if days_left in thresholds:
                    per_area.setdefault(area, {})
                    per_area[area].setdefault(days_left, [])
                    per_area[area][days_left].append((service_name, deadline))

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

