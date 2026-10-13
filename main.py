
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
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

BOT_USERNAME = "Demon_secretarybot"
COOLDOWN_SECONDS = 60
MANUAL_PAUSE_SECONDS = 600

already_replied = set()
cooldown_until = {}
manual_pause_until = {}
reply_lock = set()


def get_config():
    keys = [
        "API_ID",
        "API_HASH",
        "SESSION_STRING",
        "BOT_TOKEN",
        "OWNER_ID",
    ]
    missing = [key for key in keys if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
        )

    try:
        return {
            "api_id": int(os.environ["API_ID"]),
            "api_hash": os.environ["API_HASH"],
            "session": os.environ["SESSION_STRING"],
            "bot_token": os.environ["BOT_TOKEN"],
            "owner_id": int(os.environ["OWNER_ID"]),
        }
    except ValueError as exc:
        raise RuntimeError(
            "API_ID and OWNER_ID must be numeric."
        ) from exc


# Render health check
web = Flask(__name__)


@web.get("/")
def home():
    return "Demon Secretary is running.", 200


@web.get("/health")
def health():
    return {"status": "ok"}, 200


def run_web():
    port = int(os.environ.get("PORT", "10000"))
    web.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False,
    )


# BotFather bot: owner-only access
async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.effective_message

    if not user or not message:
        return

    if user.id != context.bot_data["owner_id"]:
        await message.reply_text(
            "🌑 I am nothing but my master's loyal servant. 🖤\n\n"
            "I exist only to serve him. Only my master has "
            "the authority to use me. ⚔️"
        )
        return

    await message.reply_text(
        "🌑 I am nothing but my master's loyal servant. 🖤\n\n"
        "I exist only to serve him. Only my master has "
        "the authority to use me. ⚔️"
    )


async def receive_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or not message.text:
        return

    # Block everyone except the owner from using the bot.
    if user.id != context.bot_data["owner_id"]:
        return

    # The owner can use the bot, but it should not forward
    # the owner's own messages back to the owner.
    # Add any owner-only commands or actions below this check.
    return


# Personal account: one fixed auto-reply per private chat
async def main():
    config = get_config()

    threading.Thread(
        target=run_web,
        daemon=True,
    ).start()

    client = TelegramClient(
        StringSession(config["session"]),
        config["api_id"],
        config["api_hash"],
    )

    application = Application.builder().token(
        config["bot_token"]
    ).build()

    application.bot_data["owner_id"] = config["owner_id"]

    application.add_handler(
        CommandHandler("start", start_command)
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_message,
        )
    )

    try:
        logger.info("Connecting personal Telegram account...")
        await client.start()
        account = await client.get_me()

        bot_info = await application.bot.get_me()
        logger.info("Personal account connected.")
        logger.info("Bot connected: @%s", bot_info.username)

        if (bot_info.username or "").lower() != BOT_USERNAME.lower():
            raise RuntimeError(
                f"Wrong bot token: expected @{BOT_USERNAME}, "
                f"got @{bot_info.username}."
            )

        @client.on(events.NewMessage(incoming=True))
        async def on_incoming(event):
            if not event.is_private or not event.raw_text:
                return

            sender = await event.get_sender()

            if not sender or getattr(sender, "bot", False):
                return
            if sender.id == account.id:
                return

            chat_id = event.chat_id
            now = time.monotonic()

            if chat_id in already_replied:
                return
            if manual_pause_until.get(chat_id, 0) > now:
                return
            if cooldown_until.get(chat_id, 0) > now:
                return
            if chat_id in reply_lock:
                return

            reply_lock.add(chat_id)
            already_replied.add(chat_id)
            cooldown_until[chat_id] = now + COOLDOWN_SECONDS

            reply = (
                "🌑 Hello user, I am Demon Secretary Bot.\n\n"
                "My master won't be around for a few days "
                "because he has gone away.\n\n"
                f"If you want to talk to him, message "
                f"@{BOT_USERNAME} with your Telegram username. "
                "I'll deliver your message to him. 🖤"
            )

            try:
                await event.reply(reply)
            except Exception:
                logger.exception("Auto-reply failed")
            finally:
                reply_lock.discard(chat_id)

        @client.on(events.NewMessage(outgoing=True))
        async def on_manual_message(event):
            if not event.is_private or not event.raw_text:
                return

            if event.chat_id not in reply_lock:
                manual_pause_until[event.chat_id] = (
                    time.monotonic() + MANUAL_PAUSE_SECONDS
                )

        await application.initialize()
        await application.start()

        if application.updater is None:
            raise RuntimeError("Bot polling could not be initialized.")

        await application.updater.start_polling()
        logger.info("Demon Secretary started successfully.")

        await client.run_until_disconnected()

    except Exception:
        logger.exception("Bot startup/runtime failure")
        raise

    finally:
        if application.updater and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        if client.is_connected():
            await client.disconnect()
        if application._initialized:
            await application.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
