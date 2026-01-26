# main.py
from telegram import Bot
from telegram.ext import Updater, CommandHandler
import schedule
import time
from threading import Thread
from datetime import date

import googleSheetRead as gs
from gannt_reader import read_services_deadlines

TOKEN = ""
ERROR_CHAT_ID = -5257429831  # metti un gruppo log o il tuo id
MESSAGE_TIME = "08:30"

bot = Bot(TOKEN)


def thresholds_for_service(duration_days: int) -> set:
    """
    Soglie di avviso per un servizio:
    - metà percorso: ceil(d/2)
    - 2 giorni, 1 giorno, 0 giorni
    - + 7 giorni se è un servizio "lungo"
    """
    half = (duration_days + 1) // 2  # ceil(d/2)
    th = {half, 2, 1, 0}
    if duration_days >= 14:
        th.add(7)
    return th


def build_message(project_name: str, gantt_url: str, grouped: dict) -> str:
    """
    grouped: dict days_left -> list of (service_name, deadline_date)
    """
    lines = [
        "⏰ PROMEMORIA SCADENZE SERVIZI",
        f"📌 Progetto: {project_name}",
        "",
    ]

    for days_left in sorted(grouped.keys()):
        if days_left == 0:
            header = "🟥 Scadono OGGI"
        elif days_left == 1:
            header = "🟧 Scadono DOMANI (1 giorno)"
        else:
            header = f"🟨 Scadono tra {days_left} giorni"

        lines.append(header)
        for name, dline in grouped[days_left]:
            lines.append(f"• {name} — {dline.strftime('%d/%m/%Y')}")
        lines.append("")

    if gantt_url:
        lines.append(f"📎 Gantt: {gantt_url}")

    return "\n".join(lines).strip()


def check_deadlines():
    data, sheet, client = gs.export_data()

    if data == -1 or sheet is None or client is None:
        bot.send_message(chat_id=ERROR_CHAT_ID, text="⚠️ Errore: impossibile leggere il foglio di configurazione.")
        return

    today = date.today()

    for idx, entry in enumerate(data):
        try:
            project_name = (entry.get("Nome", "") or "").strip()
            chat_id_raw = (entry.get("ChatId", "") or "").strip()
            gantt_url = (entry.get("Gannt", "") or "").strip()

            if not project_name or not chat_id_raw or not gantt_url:
                continue

            chat_id = int(chat_id_raw)

            # Legge servizi: (nome, durata, scadenza)
            services = read_services_deadlines(client, gantt_url)

            grouped = {}  # days_left -> list[(service_name, deadline)]
            for service_name, duration_days, deadline in services:
                days_left = (deadline - today).days
                th = thresholds_for_service(duration_days)

                if days_left in th:
                    grouped.setdefault(days_left, []).append((service_name, deadline))

            if grouped:
                msg = build_message(project_name, gantt_url, grouped)
                bot.send_message(chat_id=chat_id, text=msg)

        except Exception as e:
            bot.send_message(
                chat_id=ERROR_CHAT_ID,
                text=f"⚠️ Errore riga config {idx+2}: {type(e).__name__}: {e}"
            )


def run_scheduler():
    schedule.every().day.at(MESSAGE_TIME).do(check_deadlines)
    while True:
        schedule.run_pending()
        time.sleep(1)


def start(update, context):
    update.message.reply_text("Bot scadenze attivo.")


def main():
    updater = Updater(TOKEN)
    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.start_polling()

    # ✅ per test iniziale: fai un check all'avvio
    # Se non lo vuoi (per evitare doppio invio nel giorno), commenta la riga sotto.
    check_deadlines()

    scheduler_thread = Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    updater.idle()


if __name__ == "__main__":
    main()
