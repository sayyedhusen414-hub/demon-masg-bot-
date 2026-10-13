
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

# ---------------- CONFIG ----------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

BOT_USERNAME = "Demon_secretarybot"
COOLDOWN_SECONDS = 60
MANUAL_PAUSE_SECONDS = 600

# These sets are stored in memory and reset on restart.
already_replied = set()
cooldown_until = {}
manual_pause_until = {}
reply_lock = set()


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


# ---------------- RENDER HEALTH CHECK ----------------

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


# ---------------- BOT COMMANDS ----------------

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    # No extra welcome or format warning.
    # Users can send @username | message to contact the owner.
    return


async def receive_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    user = update.effective_user

    if not message or not user or not message.text:
        return

    # Do not process the owner's own messages.
    if user.id == context.bot_data["owner_id"]:
        return

    text = message.text.strip()

    # Only forward correctly formatted submissions.
    # Ignore all other messages silently.
    if "|" not in text:
        return

    recipient, content = text.split("|", 1)
    recipient = recipient.strip()
    content = content.strip()

    if (
        not recipient.startswith("@")
        or not content
        or len(recipient) < 2
    ):
        return

    username = f"@{user.username}" if user.username else "No username"

    forwarded_text = (
        "🌑 NEW MESSAGE\n\n"
        f"From: {user.full_name}\n"
        f"Username: {username}\n"
        f"User ID: {user.id}\n"
        f"To: {recipient}\n\n"
        f"Message:\n{content}"
    )

    try:
        await context.bot.send_message(
            chat_id=context.bot_data["owner_id"],
            text=forwarded_text,
        )
        # No success confirmation is sent to the user.
    except Exception:
        logger.exception("Could not forward submitted message")


# ---------------- MAIN ACCOUNT AUTO-REPLY ----------------

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
        logger.info("Personal Telegram account connected.")

        bot_info = await application.bot.get_me()
        logger.info("Bot connected: @%s", bot_info.username)

        if (bot_info.username or "").lower() != BOT_USERNAME.lower():
            raise RuntimeError(
                f"Wrong bot token. Expected @{BOT_USERNAME}, "
                f"got @{bot_info.username}."
            )

        # Only one fixed auto-reply per private chat.
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

            # Mark before sending so repeated incoming messages
            # cannot trigger repeated replies.
            already_replied.add(chat_id)
            cooldown_until[chat_id] = now + COOLDOWN_SECONDS

            fixed_reply = (
                "🌑 Hello user, I am Demon Secretary Bot.\n\n"
                "My master won't be around for a few days "
                "because he has gone away.\n\n"
                f"If you want to talk to him, message "
                f"@{BOT_USERNAME} with your Telegram username. "
                "I'll deliver your message to him. 🖤"
            )

            try:
                await event.reply(fixed_reply)
                logger.info("Sent one auto-reply to a private chat.")
            except Exception:
                logger.exception("Auto-reply failed")
            finally:
                reply_lock.discard(chat_id)

        # When you manually message a person, pause automation
        # for that chat so it doesn't interrupt your conversation.
        @client.on(events.NewMessage(outgoing=True))
        async def on_manual_message(event):
            if not event.is_private or not event.raw_text:
                return

            chat_id = event.chat_id
            manual_pause_until[chat_id] = (
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
