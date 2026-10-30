"""Telegram channel: SOS in (text, voice, location), alerts out (text + voice + shelter pin),
and the heard → safe loop for zone alerts approved by an operator.
"""

import asyncio
import html
import logging
import os

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update)
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters)

from . import store, voice
from .http import mark
from .responder import plain, respond

log = logging.getLogger("rahat.bot")

RESEND_AFTER_S = int(os.getenv("RAHAT_RESEND_AFTER_S", "600"))
MAX_ATTEMPTS = 3

STEP_LABEL = {"intake": "संदेश समझा · Request read", "sentinel": "मौसम और चेतावनियाँ · Hazards checked",
              "impact": "आसपास की जगहें · Facilities found", "logistics": "सुरक्षित स्थान · Shelter and route",
              "verifier": "रास्ते की जाँच · Route checked", "comms": "संदेश तैयार · Alert ready"}
STATUS_ICON = {"ok": "✅", "fix": "🔁", "fail": "⚠️"}

WELCOME = (
    "<b>RAHAT राहत</b>\n"
    "बाढ़, लू या तूफ़ान में मदद के लिए संदेश, आवाज़ या लोकेशन भेजें।\n"
    "Send a message, a voice note or your location if you need help in a flood, heatwave or storm.\n\n"
    "📍 लोकेशन भेजने पर आपके इलाके की चेतावनियाँ भी मिलेंगी। बंद करने के लिए /stop भेजें।\n"
    "Sharing your location also signs you up for alerts for your area. Send /stop to opt out.\n\n"
    "आपात स्थिति में 112 पर कॉल करें · In an emergency, call 112."
)

_app: Application | None = None
_retry_task: asyncio.Task | None = None


def enabled() -> bool:
    return _app is not None


def username() -> str | None:
    return _app.bot.username if _app else None


def _location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton("📍 लोकेशन भेजें · Share location", request_location=True)]],
                               resize_keyboard=True, one_time_keyboard=True)


def _reply_buttons(alert_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ मिल गया · Got it", callback_data=f"h:{alert_id}")],
        [InlineKeyboardButton("🟢 मैं सुरक्षित हूँ · Safe", callback_data=f"s:{alert_id}"),
         InlineKeyboardButton("🔴 मदद चाहिए · Need help", callback_data=f"x:{alert_id}")],
    ])


def _route_link(origin: dict, shelter: dict, mode: str | None) -> str:
    engine = "fossgis_osrm_foot" if mode == "walk" else "fossgis_osrm_car"
    return (f"https://www.openstreetmap.org/directions?engine={engine}"
            f"&route={origin['lat']:.5f}%2C{origin['lon']:.5f}%3B{shelter['lat']:.5f}%2C{shelter['lon']:.5f}")


async def _send_voice(chat_id: int, text: str, lang: str) -> None:
    spoken = await voice.speak(text, lang)
    if not spoken or not _app:
        return
    audio, kind = spoken
    try:
        if kind == "ogg":
            await _app.bot.send_voice(chat_id, audio)
        else:
            await _app.bot.send_audio(chat_id, audio, filename="rahat-alert.wav", title="RAHAT alert")
    except TelegramError as e:
        log.warning("voice send failed: %s", e)


async def _deliver_plan(chat_id: int, text: str, lat: float | None, lon: float | None, lang: str | None) -> dict:
    """Runs the plan with a live progress message, then sends the alert, shelter pin and voice."""
    progress = await _app.bot.send_message(chat_id, "⏳ जाँच कर रहे हैं… Checking rain, rivers, official alerts and nearby shelters…")
    lines: list[str] = []

    async def on_step(ev: dict) -> None:
        lines.append(f"{STATUS_ICON.get(ev['status'], '•')} {STEP_LABEL.get(ev['step'], ev['step'])}")
        try:
            await progress.edit_text("⏳ जाँच जारी है · Working on it\n" + "\n".join(lines))
        except TelegramError:
            pass

    out = await respond(text, lat, lon, lang, on_step=on_step)
    if out["halted"]:
        await _app.bot.send_message(
            chat_id, "📍 आपकी जगह पता नहीं चल पाई। कृपया लोकेशन भेजें या नज़दीकी गाँव/शहर का नाम लिखें।\n"
                     "We couldn't find your location. Please share it, or type the nearest village or town.",
            reply_markup=_location_keyboard())
        await store.log_sos(chat_id, "telegram", text, lat, lon, None, None, None)
        return out

    res = out["result"]
    msg, place = res["message"], res["place"]
    body = [html.escape(msg["local"])] if msg.get("local") else []
    body += [html.escape(msg["hi"]), f"<i>{html.escape(msg['en'])}</i>"]
    if msg.get("shelter"):
        body.append(f'🗺️ <a href="{_route_link(place, msg["shelter"], (msg.get("route") or {}).get("mode"))}">रास्ता देखें · Open route</a>')
    await progress.edit_text("राहत योजना तैयार · Response plan ready\n" + "\n".join(lines))
    await _app.bot.send_message(chat_id, "\n\n".join(body), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    if msg.get("shelter"):
        s, r = msg["shelter"], msg.get("route") or {}
        dist = f"{r['distance_m'] / 1000:.1f} km" if r else ""
        await _app.bot.send_venue(chat_id, s["lat"], s["lon"], title=s["name"], address=f"सुरक्षित स्थान · Safe place {dist}".strip())
    await _send_voice(chat_id, msg.get("local") or msg["hi"], msg.get("lang") or "hi")

    need = next((plain(s["text"]).split(";")[0].replace("need: ", "") for s in out["steps"] if s["step"] == "intake"), None)
    await store.log_sos(chat_id, "telegram", text, place["lat"], place["lon"], need, msg["level"],
                        msg["shelter"]["name"] if msg.get("shelter") else None)
    return out


# ---------------------------------------------------------------- handlers

async def _start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await store.upsert_user(update.effective_chat.id, name=u.first_name if u else None)
    await update.message.reply_text(WELCOME, parse_mode=ParseMode.HTML, reply_markup=_location_keyboard())


async def _stop(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await store.upsert_user(update.effective_chat.id, consent=False)
    await update.message.reply_text("अब आपको इलाके की चेतावनियाँ नहीं मिलेंगी। You won't get area alerts any more. Send /start to join again.")


async def _location(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    loc, chat = update.message.location, update.effective_chat.id
    await store.upsert_user(chat, lat=loc.latitude, lon=loc.longitude, consent=True)
    user = await store.get_user(chat)
    await _deliver_plan(chat, "", loc.latitude, loc.longitude, user.get("lang") if user else None)


async def _text(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat.id
    user = await store.get_user(chat) or {}
    await _deliver_plan(chat, update.message.text, user.get("lat"), user.get("lon"), None)


async def _voice(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat.id
    v = update.message.voice or update.message.audio
    if v.duration and v.duration > 30:
        await update.message.reply_text("कृपया 30 सेकंड से छोटा संदेश भेजें। Please keep voice notes under 30 seconds.")
        return
    f = await v.get_file()
    audio = bytes(await f.download_as_bytearray())
    heard = await voice.transcribe(audio, "voice.ogg", v.mime_type or "audio/ogg")
    if not heard or not heard["text"]:
        await update.message.reply_text("आवाज़ समझ नहीं आई। कृपया लिखकर भेजें या लोकेशन भेजें।\n"
                                        "We couldn't understand the voice note. Please type it or share your location.",
                                        reply_markup=_location_keyboard())
        return
    await update.message.reply_text(f"🎙️ “{heard['text']}”")
    await store.upsert_user(chat, lang=heard["lang"])
    user = await store.get_user(chat) or {}
    await _deliver_plan(chat, heard["text"], user.get("lat"), user.get("lon"), heard["lang"])


async def _button(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    kind, _, alert_id = (q.data or "").partition(":")
    chat = update.effective_chat.id
    status = {"h": "heard", "s": "safe", "x": "help"}.get(kind)
    if not status or not alert_id.isdigit():
        await q.answer()
        return
    await store.set_delivery(int(alert_id), chat, status)
    if status == "heard":
        await q.answer("धन्यवाद · Thanks, noted")
    elif status == "safe":
        await q.answer("धन्यवाद, सुरक्षित रहें · Glad you're safe")
        await q.edit_message_reply_markup(None)
    else:
        await q.answer("मदद भेजी जा रही है · Sending help")
        await q.edit_message_reply_markup(None)
        user = await store.get_user(chat) or {}
        await _deliver_plan(chat, "मदद चाहिए · need help (alert reply)", user.get("lat"), user.get("lon"), user.get("lang"))


# ---------------------------------------------------------------- zone alerts

async def broadcast(place: str, level: str, lat: float, lon: float, radius_km: float, message: dict) -> dict:
    """Send an operator-approved alert to everyone who opted in inside the zone."""
    if not _app:
        raise RuntimeError("Telegram bot is not configured")
    people = await store.users_within(lat, lon, radius_km)
    alert_id = await store.create_alert(place, level, lat, lon, radius_km, message["hi"], message["en"], message.get("shelter"))
    sent = 0
    for p in people:
        if await _send_alert(alert_id, p["chat_id"], message, first=True):
            sent += 1
        await asyncio.sleep(0.05)  # stay well under Telegram's broadcast rate limit
    return {"alert_id": alert_id, "recipients": len(people), "sent": sent}


async def _send_alert(alert_id: int, chat_id: int, message: dict, first: bool) -> bool:
    prefix = "" if first else "🔁 दोबारा · Reminder\n"
    parts = [message.get("local"), message["hi"]]
    body = prefix + "\n\n".join([html.escape(p) for p in parts if p] + [f"<i>{html.escape(message['en'])}</i>"])
    try:
        await _app.bot.send_message(chat_id, body, parse_mode=ParseMode.HTML, reply_markup=_reply_buttons(alert_id))
        if message.get("shelter"):
            s = message["shelter"]
            await _app.bot.send_venue(chat_id, s["lat"], s["lon"], title=s["name"], address="सुरक्षित स्थान · Safe place")
        await _send_voice(chat_id, message.get("local") or message["hi"], message.get("lang") or "hi")
        if first:
            await store.set_delivery(alert_id, chat_id, "sent")
        return True
    except TelegramError as e:
        log.warning("alert to %s failed: %s", chat_id, e)
        if first:
            await store.set_delivery(alert_id, chat_id, "failed")
        return False


async def _retry_loop() -> None:
    """Re-send to people who haven't confirmed they heard; stop after MAX_ATTEMPTS."""
    while True:
        await asyncio.sleep(60)
        try:
            for d in await store.unheard(RESEND_AFTER_S, MAX_ATTEMPTS):
                a = await store.get_alert(d["alert_id"])
                if not a:
                    continue
                msg = {"hi": a["text_hi"], "en": a["text_en"], "shelter": a["shelter"], "local": None, "lang": "hi"}
                await _send_alert(a["id"], d["chat_id"], msg, first=False)
                await store.bump_attempt(a["id"], d["chat_id"])
        except Exception:
            log.exception("retry loop iteration failed")


# ---------------------------------------------------------------- lifecycle

async def start() -> None:
    global _app, _retry_task
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        mark("Telegram", "down", "no TELEGRAM_BOT_TOKEN")
        log.info("Telegram bot disabled: TELEGRAM_BOT_TOKEN not set")
        return
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "help"], _start))
    app.add_handler(CommandHandler("stop", _stop))
    app.add_handler(MessageHandler(filters.LOCATION, _location))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, _voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _text))
    app.add_handler(CallbackQueryHandler(_button))
    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
    except TelegramError as e:
        mark("Telegram", "down", str(e))
        log.error("Telegram bot failed to start: %s", e)
        return
    _app = app
    _retry_task = asyncio.create_task(_retry_loop())
    mark("Telegram", "live", f"@{app.bot.username}")
    log.info("Telegram bot running as @%s", app.bot.username)


async def stop() -> None:
    global _app
    if _retry_task:
        _retry_task.cancel()
    if _app:
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
        _app = None
