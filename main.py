
import os
import asyncio
import logging
import threading

from flask import Flask
from telethon import TelegramClient, StringSession, events
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- SETTINGS ----------
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])

BOT_USERNAME = "@Demon_secretarybot"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("abyss")

# ---------- DARK AESTHETIC REPLIES ----------
INTRO = (
    "☠️ 𝐇𝐄𝐋𝐋𝐎, 𝐒𝐓𝐑𝐀𝐍𝐆𝐄𝐑. 🖤\n\n"
    "𝘐'𝘮 𝘵𝘩𝘦 𝘷𝘰𝘪𝘤𝘦 𝘣𝘦𝘩𝘪𝘯𝘥 𝘵𝘩𝘦 𝘴𝘩𝘢𝘥𝘰𝘸𝘴. 🌑\n"
    "𝘞𝘩𝘰 𝘢𝘮 𝘐 𝘴𝘱𝘦𝘢𝘬𝘪𝘯𝘨 𝘸𝘪𝘵𝘩?"
)

BUSY = (
    "🌑 𝐌𝐀𝐒𝐓𝐄𝐑 𝐈𝐒 𝐔𝐍𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄. 🥀\n\n"
    "𝘐'𝘮 𝘣𝘶𝘴𝘺 𝘢𝘯𝘥 𝘸𝘰𝘯'𝘵 𝘣𝘦 𝘢𝘳𝘰𝘶𝘯𝘥 "
    "𝘧𝘰𝘳 𝘢 𝘧𝘦𝘸 𝘥𝘢𝘺𝘴. 🖤"
)

dm_counts = {}


# ---------- RENDER HEALTH CHECK ----------
web = Flask(__name__)

@web.get("/")
def health():
    return "Abyss Auto-Reply is running.", 200

def run_web():
    port = int(os.environ.get("PORT", "10000"))
    web.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )


# ---------- BOT: /start ----------
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data["waiting"] = True

    await update.effective_message.reply_text(
        "🌑 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐌𝐘 𝐌𝐀𝐒𝐓𝐄𝐑. 🖤\n\n"
        "Send your username and message in ONE message.\n\n"
        "Format:\n"
        "@yourusername | Your message here\n\n"
        "🥀 Your message will be delivered privately."
    )


# ---------- BOT: RECEIVE MESSAGE ----------
async def receive_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    msg = update.effective_message

    if not user or not msg or not msg.text:
        return

    if not context.user_data.get("waiting"):
        await msg.reply_text("Send /start to submit a message. 🌑")
        return

    if "|" not in msg.text:
        await msg.reply_text(
            "⚠️ Use this format:\n"
            "@yourusername | Your message"
        )
        return

    username, body = msg.text.split("|", 1)
    username = username.strip()
    body = body.strip()

    if (
        not username.startswith("@")
        or len(username) < 2
        or not body
    ):
        await msg.reply_text(
            "⚠️ Include your @username and message."
        )
        return

    if len(body) > 3000:
        await msg.reply_text(
            "⚠️ Please keep your message under 3000 characters."
        )
        return

    report = (
        "📩 𝐍𝐄𝐖 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 — 𝐀𝐁𝐘𝐒𝐒\n\n"
        f"👤 Submitted username: {username}\n"
        f"🆔 Sender Telegram ID: {user.id}\n"
        f"🤖 Received via: {BOT_USERNAME}\n\n"
        "💬 Message:\n"
        f"{body}"
    )

    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=report,
        )
    except Exception:
        log.exception("Message delivery to master failed")
        await msg.reply_text(
            "⚠️ Message delivery failed. Please try again later."
        )
        return

    context.user_data["waiting"] = False

    await msg.reply_text(
        "📨 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐒𝐄𝐍𝐓. 🖤\n\n"
        "🌑 Your message has reached my master.\n"
        "🥀 Wait for a reply."
    )


# ---------- PERSONAL TELEGRAM ACCOUNT ----------
async def run_all():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_message,
        )
    )

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH,
    )

    await client.start()
    me = await client.get_me()

    bot_info = await app.bot.get_me()
    actual_bot_username = "@" + bot_info.username

    if actual_bot_username.lower() != BOT_USERNAME.lower():
        raise RuntimeError(
            "BOT_USERNAME does not match BOT_TOKEN. "
            "Check your bot token and username."
        )

    log.info("Personal account connected: %s", me.id)
    log.info("Message bot connected: %s", actual_bot_username)

    async def personal_auto_reply(event):
        sender = await event.get_sender()

        if not sender or getattr(sender, "bot", False):
            return

        if sender.id == me.id:
            return

        count = dm_counts.get(sender.id, 0) + 1
        dm_counts[sender.id] = count

        if count == 1:
            reply = INTRO

        elif count == 2:
            reply = (
                BUSY
                + "\n\n📩 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐌𝐘 𝐁𝐎𝐓:\n"
                + BOT_USERNAME
            )

        else:
            reply = (
                "🌑 𝐖𝐀𝐍𝐓 𝐓𝐎 𝐑𝐄𝐀𝐂𝐇 𝐌𝐘 𝐌𝐀𝐒𝐓𝐄𝐑? 🖤\n\n"
                "Don't send your message here.\n"
                f"𖤐 𝐌𝐘 𝐁𝐎𝐓: {BOT_USERNAME}\n\n"
                "🥀 Open my bot, press /start, then send "
                "your @username and message."
            )

        try:
            await event.reply(reply)
        except Exception:
            log.exception("Personal auto-reply failed")

    client.add_event_handler(
        personal_auto_reply,
        events.NewMessage(
            incoming=True,
            func=lambda event: event.is_private,
        ),
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    log.info("Abyss services started successfully.")

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await client.disconnect()



import os
import asyncio
import logging
import threading

from flask import Flask
from telethon import TelegramClient, StringSession, events
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- SETTINGS ----------
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])

BOT_USERNAME = "@Demon_secretarybot"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("abyss")

# ---------- DARK AESTHETIC REPLIES ----------
INTRO = (
    "☠️ 𝐇𝐄𝐋𝐋𝐎, 𝐒𝐓𝐑𝐀𝐍𝐆𝐄𝐑. 🖤\n\n"
    "𝘐'𝘮 𝘵𝘩𝘦 𝘷𝘰𝘪𝘤𝘦 𝘣𝘦𝘩𝘪𝘯𝘥 𝘵𝘩𝘦 𝘴𝘩𝘢𝘥𝘰𝘸𝘴. 🌑\n"
    "𝘞𝘩𝘰 𝘢𝘮 𝘐 𝘴𝘱𝘦𝘢𝘬𝘪𝘯𝘨 𝘸𝘪𝘵𝘩?"
)

BUSY = (
    "🌑 𝐌𝐀𝐒𝐓𝐄𝐑 𝐈𝐒 𝐔𝐍𝐀𝐕𝐀𝐈𝐋𝐀𝐁𝐋𝐄. 🥀\n\n"
    "𝘐'𝘮 𝘣𝘶𝘴𝘺 𝘢𝘯𝘥 𝘸𝘰𝘯'𝘵 𝘣𝘦 𝘢𝘳𝘰𝘶𝘯𝘥 "
    "𝘧𝘰𝘳 𝘢 𝘧𝘦𝘸 𝘥𝘢𝘺𝘴. 🖤"
)

dm_counts = {}


# ---------- RENDER HEALTH CHECK ----------
web = Flask(__name__)

@web.get("/")
def health():
    return "Abyss Auto-Reply is running.", 200

def run_web():
    port = int(os.environ.get("PORT", "10000"))
    web.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )


# ---------- BOT: /start ----------
async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data["waiting"] = True

    await update.effective_message.reply_text(
        "🌑 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐌𝐘 𝐌𝐀𝐒𝐓𝐄𝐑. 🖤\n\n"
        "Send your username and message in ONE message.\n\n"
        "Format:\n"
        "@yourusername | Your message here\n\n"
        "🥀 Your message will be delivered privately."
    )


# ---------- BOT: RECEIVE MESSAGE ----------
async def receive_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    msg = update.effective_message

    if not user or not msg or not msg.text:
        return

    if not context.user_data.get("waiting"):
        await msg.reply_text("Send /start to submit a message. 🌑")
        return

    if "|" not in msg.text:
        await msg.reply_text(
            "⚠️ Use this format:\n"
            "@yourusername | Your message"
        )
        return

    username, body = msg.text.split("|", 1)
    username = username.strip()
    body = body.strip()

    if (
        not username.startswith("@")
        or len(username) < 2
        or not body
    ):
        await msg.reply_text(
            "⚠️ Include your @username and message."
        )
        return

    if len(body) > 3000:
        await msg.reply_text(
            "⚠️ Please keep your message under 3000 characters."
        )
        return

    report = (
        "📩 𝐍𝐄𝐖 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 — 𝐀𝐁𝐘𝐒𝐒\n\n"
        f"👤 Submitted username: {username}\n"
        f"🆔 Sender Telegram ID: {user.id}\n"
        f"🤖 Received via: {BOT_USERNAME}\n\n"
        "💬 Message:\n"
        f"{body}"
    )

    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=report,
        )
    except Exception:
        log.exception("Message delivery to master failed")
        await msg.reply_text(
            "⚠️ Message delivery failed. Please try again later."
        )
        return

    context.user_data["waiting"] = False

    await msg.reply_text(
        "📨 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐒𝐄𝐍𝐓. 🖤\n\n"
        "🌑 Your message has reached my master.\n"
        "🥀 Wait for a reply."
    )


# ---------- PERSONAL TELEGRAM ACCOUNT ----------
async def run_all():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_message,
        )
    )

    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH,
    )

    await client.start()
    me = await client.get_me()

    bot_info = await app.bot.get_me()
    actual_bot_username = "@" + bot_info.username

    if actual_bot_username.lower() != BOT_USERNAME.lower():
        raise RuntimeError(
            "BOT_USERNAME does not match BOT_TOKEN. "
            "Check your bot token and username."
        )

    log.info("Personal account connected: %s", me.id)
    log.info("Message bot connected: %s", actual_bot_username)

    async def personal_auto_reply(event):
        sender = await event.get_sender()

        if not sender or getattr(sender, "bot", False):
            return

        if sender.id == me.id:
            return

        count = dm_counts.get(sender.id, 0) + 1
        dm_counts[sender.id] = count

        if count == 1:
            reply = INTRO

        elif count == 2:
            reply = (
                BUSY
                + "\n\n📩 𝐌𝐄𝐒𝐒𝐀𝐆𝐄 𝐌𝐘 𝐁𝐎𝐓:\n"
                + BOT_USERNAME
            )

        else:
            reply = (
                "🌑 𝐖𝐀𝐍𝐓 𝐓𝐎 𝐑𝐄𝐀𝐂𝐇 𝐌𝐘 𝐌𝐀𝐒𝐓𝐄𝐑? 🖤\n\n"
                "Don't send your message here.\n"
                f"𖤐 𝐌𝐘 𝐁𝐎𝐓: {BOT_USERNAME}\n\n"
                "🥀 Open my bot, press /start, then send "
                "your @username and message."
            )

        try:
            await event.reply(reply)
        except Exception:
            log.exception("Personal auto-reply failed")

    client.add_event_handler(
        personal_auto_reply,
        events.NewMessage(
            incoming=True,
            func=lambda event: event.is_private,
        ),
    )

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    log.info("Abyss services started successfully.")

    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await client.disconnect()


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(run_all())
