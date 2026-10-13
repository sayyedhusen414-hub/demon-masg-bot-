
import os
import asyncio
import logging
import threading
import time
from collections import defaultdict

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

# Auto-reply state for each private chat
message_counts = defaultdict(int)
cooldown_until = {}
manual_pause_until = {}
auto_reply_lock = set()

COOLDOWN_SECONDS = 60
MANUAL_PAUSE_SECONDS = 600  # 10 minutes after you send a manual message


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
    return "Demon Secretary Bot is running.", 200


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


# BotFather bot commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🌑 Welcome to Demon Secretary.\n\n"
        "Send your message in this format:\n"
        "@username | Your message"
    )


async def receive_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or not message.text:
        return

    if user.id == context.bot.id:
        return

    if user.id == context.bot_data["owner_id"]:
        await message.reply_text("🌑 Owner message received.")
        return

    text = message.text.strip()
    if "|" not in text:
        await message.reply_text(
            "⚠️ Use this format:\n@username | Your message"
        )
        return

    recipient, content = text.split("|", 1)
    recipient = recipient.strip()
    content = content.strip()

    if not recipient.startswith("@") or not content:
        await message.reply_text(
            "⚠️ Use this format:\n@username | Your message"
        )
        return

    sender_username = (
        f"@{user.username}" if user.username else "No username"
    )
    owner_message = (
        "🌑 NEW MESSAGE\n\n"
        f"From: {user.full_name}\n"
        f"Username: {sender_username}\n"
        f"User ID: {user.id}\n"
        f"To: {recipient}\n\n"
        f"Message:\n{content}"
    )

    try:
        await context.bot.send_message(
            chat_id=context.bot_data["owner_id"],
            text=owner_message,
        )
    except Exception:
        logger.exception("Could not deliver message to owner")
        await message.reply_text(
            "⚠️ Delivery failed. Please try again later."
        )
        return

    await message.reply_text("✅ Your message has been delivered.")


async def main():
    config = get_config()

    threading.Thread(target=run_web, daemon=True).start()

    client = TelegramClient(
        StringSession(config["session"]),
        config["api_id"],
        config["api_hash"],
    )

    application = Application.builder().token(
        config["bot_token"]
    ).build()
    application.bot_data["owner_id"] = config["owner_id"]

    application.add_handler(CommandHandler("start", start_command))
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

            # Don't interrupt a conversation where you recently replied.
            if manual_pause_until.get(chat_id, 0) > now:
                return

            # After the third reply, wait one minute before replying again.
            if cooldown_until.get(chat_id, 0) > now:
                return

            if chat_id in auto_reply_lock:
                return

            auto_reply_lock.add(chat_id)
            try:
                message_counts[chat_id] += 1
                count = message_counts[chat_id]

                if count == 1:
                    reply = (
                        "🌑 Hello! I'm Shabbir's personal account.\n"
                        "How can I help you?"
                    )
                elif count == 2:
                    reply = (
                        "🖤 Shabbir is busy right now and may be "
                        "unavailable for a few days.\n\n"
                        f"📩 Send your message to @{BOT_USERNAME} "
                        "and follow /start."
                    )
                elif count == 3:
                    reply = (
                        f"🌑 Shabbir is currently unavailable.\n"
                        f"Message @{BOT_USERNAME}, send /start, "
                        "then submit your message in this format:\n\n"
                        "@username | Your message"
                    )
                    cooldown_until[chat_id] = (
                        time.monotonic() + COOLDOWN_SECONDS
                    )
                else:
                    # No repeated messages after the first three.
                    return

                await event.reply(reply)

            except Exception:
                logger.exception("Personal-account auto-reply failed")
            finally:
                auto_reply_lock.discard(chat_id)

        @client.on(events.NewMessage(outgoing=True))
        async def on_manual_outgoing(event):
            if not event.is_private or not event.raw_text:
                return

            # Ignore our own automated replies.
            if event.chat_id in auto_reply_lock:
                return

            # Your own message pauses automatic replies in that chat.
            manual_pause_until[event.chat_id] = (
                time.monotonic() + MANUAL_PAUSE_SECONDS
            )
            logger.info("Auto-replies paused for one chat after manual reply.")

        await application.initialize()
        await application.start()

        if application.updater is None:
            raise RuntimeError("Bot polling could not be initialized.")

        await application.updater.start_polling()
        logger.info("Bot polling started.")

        await client.run_until_disconnected()

    except Exception:
        logger.exception("Startup or runtime error")
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
