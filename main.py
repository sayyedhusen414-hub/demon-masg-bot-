
import os
import asyncio
import logging
import threading
import time

from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ---------------- CONFIG ----------------

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
STRING_SESSION = os.environ["STRING_SESSION"]

COOLDOWN_SECONDS = 24 * 60 * 60

AUTO_REPLY = (
    "🌑 Hello user, I am Demon Secretary Bot.\n\n"
    "My master won't be around for a few days because he has gone away.\n\n"
    "If you want to talk to him, message @Demon_secretarybot. "
    "I'll deliver your message to him. 🖤"
)

LOYALTY_MESSAGE = (
    "🌑 I am nothing but my master's loyal servant. 🖤\n\n"
    "I exist only to serve him. Only my master has the authority "
    "to use me. ⚔️"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

web_app = Flask(__name__)

# Store last reply time per private chat
last_replied = {}


# ---------------- RENDER HEALTH CHECK ----------------

@web_app.route("/")
def home():
    return "Demon Secretary Bot is running.", 200


@web_app.route("/health")
def health():
    return "OK", 200


def run_web_server():
    port = int(os.environ.get("PORT", "10000"))
    web_app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )


# ---------------- BOTFATHER BOT ----------------

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if update.effective_message:
        await update.effective_message.reply_text(LOYALTY_MESSAGE)


# ---------------- PERSONAL ACCOUNT AUTO-REPLY ----------------

async def handle_private_message(event):
    try:
        # Only incoming private messages
        if not event.is_private or not event.is_incoming:
            return

        # Ignore Telegram bot accounts
        sender = await event.get_sender()
        if not sender or getattr(sender, "bot", False):
            return

        chat_id = event.chat_id
        now = time.time()
        previous_time = last_replied.get(chat_id, 0)

        # One auto-reply per chat every 24 hours
        if now - previous_time < COOLDOWN_SECONDS:
            return

        # Set cooldown before sending to avoid duplicate replies
        last_replied[chat_id] = now

        await event.reply(AUTO_REPLY)
        logger.info("Auto-reply sent to private chat %s", chat_id)

    except Exception:
        logger.exception("Failed to process incoming message")


# ---------------- START EVERYTHING ----------------

async def main():
    # BotFather bot
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start_command))

    # Personal Telegram account
    user_client = TelegramClient(
        StringSession(STRING_SESSION),
        API_ID,
        API_HASH,
    )

    await user_client.start()

    await bot_app.initialize()
    await bot_app.start()

    if bot_app.updater is None:
        raise RuntimeError("Telegram polling updater is unavailable")

    await bot_app.updater.start_polling()

    user_client.add_event_handler(
        handle_private_message,
        events.NewMessage(incoming=True, func=lambda event: event.is_private),
    )

    logger.info("Demon Secretary Bot started successfully.")

    try:
        await user_client.run_until_disconnected()
    finally:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        await user_client.disconnect()


if __name__ == "__main__":
    threading.Thread(
        target=run_web_server,
        daemon=True,
    ).start()

    asyncio.run(main())
