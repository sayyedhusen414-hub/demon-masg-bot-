
import os
import asyncio
import logging
import threading
import time

from flask import Flask
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ========== CONFIG ==========

BOT_TOKEN = os.environ["BOT_TOKEN"]
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
STRING_SESSION = os.environ["STRING_SESSION"]

OWNER_ID = 8344335776
COOLDOWN = 24 * 60 * 60

LOYALTY_MESSAGE = (
    "🌑 I am nothing but my master's loyal servant. 🖤\n\n"
    "I exist only to serve him. Only my master has the authority "
    "to use me. ⚔️"
)

AUTO_REPLY = (
    "🌑 Hello, I am busy right now.\n\n"
    "My master is currently unavailable. "
    "Please try again later. 🖤"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

web = Flask(__name__)

auto_reply_enabled = False
last_replied = {}


# ========== RENDER HEALTH CHECK ==========

@web.route("/")
def home():
    return "Demon Secretary is running!", 200


@web.route("/health")
def health():
    return "OK", 200


def run_web():
    web.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
        use_reloader=False,
    )


# ========== BOT COMMANDS ==========

async def start_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    global auto_reply_enabled

    user = update.effective_user
    if not user or not update.effective_message:
        return

    await update.effective_message.reply_text(LOYALTY_MESSAGE)

    if user.id == OWNER_ID:
        auto_reply_enabled = True
        await update.effective_message.reply_text(
            "✅ Personal DM auto-reply is ON."
        )


async def stop_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    global auto_reply_enabled

    user = update.effective_user
    if not user or not update.effective_message:
        return

    if user.id != OWNER_ID:
        await update.effective_message.reply_text(
            "⛔ Only my master can use this command."
        )
        return

    auto_reply_enabled = False
    await update.effective_message.reply_text(
        "🛑 Auto-reply is OFF. You can chat freely."
    )


async def on_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    global auto_reply_enabled

    user = update.effective_user
    if not user or not update.effective_message:
        return

    if user.id != OWNER_ID:
        await update.effective_message.reply_text(
            "⛔ Only my master can use this command."
        )
        return

    auto_reply_enabled = True
    await update.effective_message.reply_text(
        "🌑 Auto-reply is ON again. 🖤"
    )


# ========== PERSONAL TELEGRAM DM HANDLER ==========

async def handle_dm(event):
    try:
        if not event.is_private or not event.is_incoming:
            return

        if not auto_reply_enabled:
            return

        sender = await event.get_sender()

        if not sender or getattr(sender, "bot", False):
            return

        chat_id = event.chat_id
        now = time.time()
        previous = last_replied.get(chat_id, 0)

        # One automatic reply per chat per 24 hours
        if now - previous < COOLDOWN:
            logger.info("24-hour cooldown active for chat %s", chat_id)
            return

        # Send from the PERSONAL Telegram account
        await event.respond(AUTO_REPLY)
        last_replied[chat_id] = time.time()

        logger.info("Personal account auto-reply sent to chat %s", chat_id)

    except Exception:
        logger.exception("Personal account DM handler failed")


# ========== RUN ==========

async def main():
    global auto_reply_enabled

    bot = Application.builder().token(BOT_TOKEN).build()

    bot.add_handler(CommandHandler("start", start_cmd))
    bot.add_handler(CommandHandler("stop", stop_cmd))
    bot.add_handler(CommandHandler("on", on_cmd))

    client = TelegramClient(
        StringSession(STRING_SESSION),
        API_ID,
        API_HASH,
    )

    await client.start()

    me = await client.get_me()
    logger.info("Personal account connected. ID: %s", me.id)

    client.add_event_handler(
        handle_dm,
        events.NewMessage(incoming=True),
    )

    await bot.initialize()
    await bot.start()

    if bot.updater is None:
        raise RuntimeError("Bot polling is unavailable")

    await bot.updater.start_polling()

    logger.info("Demon Secretary started successfully.")

    try:
        await client.run_until_disconnected()
    finally:
        await bot.updater.stop()
        await bot.stop()
        await bot.shutdown()
        await client.disconnect()


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(main())
