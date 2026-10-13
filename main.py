
import os
import asyncio
import logging
import threading
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

# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------- ENVIRONMENT ----------
def get_config():
    required = [
        "API_ID",
        "API_HASH",
        "SESSION_STRING",
        "BOT_TOKEN",
        "OWNER_ID",
    ]

    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
        )

    try:
        api_id = int(os.environ["API_ID"])
        owner_id = int(os.environ["OWNER_ID"])
    except ValueError as exc:
        raise RuntimeError(
            "API_ID and OWNER_ID must be numeric."
        ) from exc

    return {
        "api_id": api_id,
        "api_hash": os.environ["API_HASH"],
        "session": os.environ["SESSION_STRING"],
        "bot_token": os.environ["BOT_TOKEN"],
        "owner_id": owner_id,
    }


# ---------- HEALTH CHECK ----------
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


# ---------- MESSAGE COUNTS ----------
message_counts = defaultdict(int)

BOT_USERNAME = "Demon_secretarybot"


# ---------- BOT COMMANDS ----------
async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.effective_message.reply_text(
        "🌑 Welcome to Demon Secretary.\n\n"
        "Send your message in this format:\n"
        "@username | Your message\n\n"
        "Example:\n"
        "@example | Hello, please contact me."
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

    if user.id == int(context.bot_data["owner_id"]):
        await message.reply_text(
            "🌑 Owner message received."
        )
        return

    text = message.text.strip()

    if "|" not in text:
        await message.reply_text(
            "⚠️ Use this format:\n"
            "@username | Your message"
        )
        return

    recipient, content = text.split("|", 1)
    recipient = recipient.strip()
    content = content.strip()

    if not recipient.startswith("@") or not content:
        await message.reply_text(
            "⚠️ Enter a valid username and message."
        )
        return

    sender_name = user.full_name
    sender_username = (
        f"@{user.username}" if user.username else "No username"
    )

    owner_message = (
        "🌑 NEW MESSAGE\n\n"
        f"From: {sender_name}\n"
        f"Username: {sender_username}\n"
        f"User ID: {user.id}\n\n"
        f"To: {recipient}\n"
        f"Message:\n{content}"
    )

    try:
        await context.bot.send_message(
            chat_id=context.bot_data["owner_id"],
            text=owner_message,
        )
    except Exception:
        logger.exception("Message delivery to owner failed")
        await message.reply_text(
            "⚠️ Delivery failed. Please try again later."
        )
        return

    await message.reply_text(
        "✅ Your message has been delivered to the owner."
    )


# ---------- PERSONAL ACCOUNT AUTO-REPLY ----------
async def main():
    config = get_config()

    # Start health-check web server.
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
        logger.info(
            "Personal account connected: ID %s",
            account.id,
        )

        bot_info = await application.bot.get_me()
        logger.info("Bot connected: @%s", bot_info.username)

        if (bot_info.username or "").lower() != BOT_USERNAME.lower():
            raise RuntimeError(
                f"Wrong bot token. Expected @{BOT_USERNAME}, "
                f"but connected to @{bot_info.username}."
            )

        @client.on(events.NewMessage(incoming=True))
        async def auto_reply(event):
            if not event.is_private or event.out:
                return

            sender = await event.get_sender()
            if not sender or getattr(sender, "bot", False):
                return

            # Ignore service notifications and messages without text.
            if not event.raw_text:
                return

            # Do not auto-reply to your own account.
            if sender.id == account.id:
                return

            message_counts[sender.id] += 1
            count = message_counts[sender.id]

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
            else:
                reply = (
                    f"🌑 Shabbir is currently unavailable.\n"
                    f"Message @{BOT_USERNAME}, send /start, "
                    "then submit your message in this format:\n\n"
                    "@username | Your message"
                )

            try:
                await event.reply(reply)
            except Exception:
                logger.exception("Auto-reply failed")

        await application.initialize()
        await application.start()

        if application.updater is None:
            raise RuntimeError("Bot polling could not be initialized.")

        await application.updater.start_polling()
        logger.info("Bot polling started.")
        logger.info("Personal account auto-replies are enabled.")

        # Keep both Telegram clients running.
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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
    except Exception:
        logger.exception("Bot stopped because of an error.")
        raise
