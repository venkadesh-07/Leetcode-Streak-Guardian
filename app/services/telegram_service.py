"""
Telegram Bot Notification Service for LeetCode Streak Guardian.
Delivers direct, private 1-on-1 messages to user chat IDs via Telegram Bot API.
"""

from datetime import datetime, timezone
import logging
import os
import re
import requests

logger = logging.getLogger(__name__)


def validate_telegram_chat_id(chat_id: str) -> bool:
    """Validate that chat_id is numeric or signed numeric (private user or group)."""
    if not isinstance(chat_id, str):
        return False
    chat_id = chat_id.strip()
    return bool(re.match(r"^-?\d{5,16}$", chat_id))


def send_telegram_streak_reminder(
    chat_id: str,
    user,
    submissions_today: int,
    current_streak: int,
    date_utc: str,
) -> dict:
    """
    Send a markdown-formatted streak reminder message to the user's private Telegram chat.

    Returns:
        dict: {"success": bool, "mode": "telegram"|"simulated", "error": str|None}
    """
    if not chat_id:
        return {"success": False, "error": "Telegram Chat ID is empty."}

    chat_id = str(chat_id).strip()

    if not validate_telegram_chat_id(chat_id):
        return {"success": False, "error": "Invalid Telegram Chat ID format. It must be numeric."}

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    # Simulation mode for local development/testing without real token
    if (
        os.environ.get("SIMULATE_TELEGRAM", "").lower() in ("true", "1")
        or not bot_token
        or "simulate" in chat_id
    ):
        logger.info(f"[TELEGRAM SIMULATION] Dispatched alert to Chat ID {chat_id} (Streak: {current_streak})")
        return {"success": True, "mode": "simulated"}

    username = getattr(user, "leetcode_username", None) or getattr(user, "email", "Coder")
    # Escape HTML special characters for safety
    import html
    safe_username = html.escape(str(username))
    safe_streak = html.escape(str(current_streak))
    safe_submissions = html.escape(str(submissions_today))
    safe_date = html.escape(str(date_utc))

    message_text = (
        f"🔥 <b>LeetCode Streak Alert!</b>\n\n"
        f"Hey <b>{safe_username}</b>, you haven't solved any problems yet today!\n\n"
        f"📊 <b>Current Streak:</b> <code>{safe_streak} days</code>\n"
        f"⚡ <b>Today's Submissions:</b> <code>{safe_submissions}</code>\n"
        f"📅 <b>Date (UTC):</b> <code>{safe_date}</code>\n\n"
        f"⚠️ Solve at least 1 problem before <b>23:59 UTC</b> to keep your streak alive!\n\n"
        f"👉 <a href=\"https://leetcode.com/problemset/all/\">Solve Daily Problem on LeetCode</a>"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=25)
        res_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

        if response.status_code == 200 and res_data.get("ok"):
            logger.info(f"Telegram alert dispatched successfully to chat {chat_id}")
            return {"success": True, "mode": "telegram"}
        elif response.status_code == 403:
            return {"success": False, "error": "Bot was blocked by the user or chat not started. Please open your bot in Telegram and click START."}
        elif response.status_code == 400:
            return {"success": False, "error": f"Invalid chat request: {res_data.get('description', response.text)}"}
        else:
            return {"success": False, "error": f"Telegram API error {response.status_code}: {res_data.get('description', response.text)}"}
    except requests.Timeout:
        logger.warning(f"Telegram API request timed out for chat {chat_id}")
        return {"success": False, "error": "Telegram server timed out. Check your internet connection or retry in a moment."}
    except requests.RequestException as exc:
        logger.error(f"Network error sending Telegram notification: {exc}")
        return {"success": False, "error": f"Connection error: {exc}"}


def get_telegram_bot_username() -> str:
    """Retrieve the bot's username from environment or Telegram API."""
    configured = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if configured:
        return configured
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        return "LeetcodeStreakGuardianbot"
    try:
        resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=6)
        if resp.status_code == 200 and resp.json().get("ok"):
            return resp.json()["result"].get("username", "LeetcodeStreakGuardianbot")
    except Exception:
        pass
    return "LeetcodeStreakGuardianbot"


def send_telegram_message(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    """Send a plain or HTML message via the configured Telegram Bot."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        return resp.status_code == 200 and resp.json().get("ok", False)
    except Exception as e:
        logger.warning(f"Error sending Telegram message to {chat_id}: {e}")
        return False


def process_telegram_update(item: dict) -> dict:
    """
    Process a single Telegram update dict (from getUpdates or Webhook).
    Handles:
      - /start <token> or /link <token> -> Links user account & sends welcome message
      - /start -> Instructions on linking account
      - /streak or /today -> Replies with live LeetCode streak
      - /help -> Command reference
    """
    from flask import has_app_context
    if not has_app_context():
        from app import create_app
        _app = create_app()
        with _app.app_context():
            return process_telegram_update(item)

    from app.extensions import db
    from app.models import User

    msg = item.get("message") or item.get("edited_message")
    if not msg:
        return {"handled": False, "reason": "no_message"}

    text = str(msg.get("text", "")).strip()
    chat = msg.get("chat", {})
    chat_id = str(chat.get("id", "")).strip()

    if not chat_id or not text:
        return {"handled": False, "reason": "empty_chat_or_text"}

    first_name = msg.get("from", {}).get("first_name", "Coder")

    # Extract token from various possible user formats:
    # 1. /start <token> or /link <token> or /start=<token> or /link=<token>
    # 2. Raw token
    # 3. URL containing start=<token>
    extracted_token = None
    if text.startswith("/start") or text.startswith("/link"):
        m = re.search(r"^/(?:start|link)[=\s]+([A-Za-z0-9_-]{12,64})", text)
        if m:
            extracted_token = m.group(1).strip()
    elif "start=" in text:
        m = re.search(r"start=([A-Za-z0-9_-]{12,64})", text)
        if m:
            extracted_token = m.group(1).strip()
    elif re.fullmatch(r"[A-Za-z0-9_-]{20,64}", text):
        extracted_token = text

    if extracted_token:
        user = User.query.filter_by(api_token=extracted_token).first()
        if user:
            # Unlink previous accounts connected to this chat_id to keep mapping clean
            old_users = User.query.filter_by(telegram_chat_id=chat_id).all()
            for old_u in old_users:
                if old_u.id != user.id:
                    old_u.telegram_chat_id = None
                    old_u.notify_telegram = False

            user.telegram_chat_id = chat_id
            user.notify_telegram = True
            db.session.commit()

            safe_name = user.leetcode_username or first_name or "Streak Guardian"
            welcome_text = (
                f"🎉 <b>LeetCode Streak Guardian Connected!</b>\n\n"
                f"Welcome, <b>{safe_name}</b>!\n"
                f"Your Telegram account is now linked to <code>{user.email}</code>.\n\n"
                f"⚡ <b>Commands you can use anytime:</b>\n"
                f"🔥 <code>/streak</code> - Check live LeetCode streak & today's progress\n"
                f"ℹ️ <code>/help</code> - View bot commands\n\n"
                f"We'll alert you right here whenever your streak is at risk before UTC midnight!"
            )
            send_telegram_message(chat_id, welcome_text)
            return {"handled": True, "action": "linked", "user_id": user.id}
        else:
            send_telegram_message(
                chat_id,
                "⚠️ <b>Invalid or expired sync token.</b>\n\n"
                "Please visit your Streak Guardian Dashboard Settings and click <b>Connect with Telegram</b> to get a fresh link."
            )
            return {"handled": True, "action": "invalid_token"}

    # Plain /start or /link without token
    if text.startswith("/start") or text.startswith("/link"):
        user = User.query.filter_by(telegram_chat_id=chat_id).first()
        if user:
            send_telegram_message(
                chat_id,
                f"👋 Hello <b>{user.leetcode_username or first_name}</b>!\n\n"
                f"This chat is currently linked to <b>{user.email}</b>.\n\n"
                f"🔥 Send <code>/streak</code> to view live stats.\n"
                f"🔄 To switch to another account, send: <code>/link &lt;YOUR_NEW_SYNC_TOKEN&gt;</code>"
            )
        else:
            send_telegram_message(
                chat_id,
                f"👋 <b>Welcome to LeetCode Streak Guardian!</b>\n\n"
                f"To connect your account and receive autonomous streak alerts:\n"
                f"1️⃣ Open your <b>LeetCode Streak Guardian Dashboard</b>\n"
                f"2️⃣ Go to <b>Settings</b> ➔ Telegram Channel\n"
                f"3️⃣ Click <b>Connect with Telegram</b> or send: <code>/link &lt;YOUR_SYNC_TOKEN&gt;</code>"
            )
        return {"handled": True, "action": "start_help"}

    # Command 2: /streak or /today or /status
    if text in ("/streak", "/today", "/status", "streak", "status"):
        user = User.query.filter_by(telegram_chat_id=chat_id).first()
        if not user:
            send_telegram_message(
                chat_id,
                "⚠️ Your Telegram is not linked to any LeetCode Streak Guardian account yet.\n"
                "Visit your website settings and click <b>Connect with Telegram</b> to link."
            )
            return {"handled": True, "action": "not_linked"}

        if not user.leetcode_username:
            send_telegram_message(
                chat_id,
                "⚠️ You have not set a LeetCode username yet in your website dashboard settings."
            )
            return {"handled": True, "action": "no_username"}

        try:
            from app.services.leetcode_checker import check_daily_activity
            result = check_daily_activity(user.leetcode_username)
            user.current_streak = result.get("current_streak", 0)
            user.today_submissions = result.get("submissions_today", 0)
            user.is_active_today = result.get("active_today", False)
            user.last_checked_date_utc = result.get("checked_date_utc")
            db.session.commit()

            status_icon = "✅ Streak Protected!" if user.is_active_today else "⚠️ Streak At Risk!"
            msg_reply = (
                f"🔥 <b>LeetCode Streak Status</b>\n\n"
                f"👤 <b>User:</b> <code>{user.leetcode_username}</code>\n"
                f"📊 <b>Current Streak:</b> <code>{user.current_streak} days</code>\n"
                f"⚡ <b>Today's Submissions:</b> <code>{user.today_submissions}</code>\n"
                f"🛡️ <b>Status:</b> <b>{status_icon}</b>\n"
                f"📅 <b>Date (UTC):</b> <code>{user.last_checked_date_utc}</code>\n\n"
                f"{'Keep up the great work!' if user.is_active_today else 'Solve at least 1 problem before UTC midnight to maintain your streak!'}"
            )
            send_telegram_message(chat_id, msg_reply)
            return {"handled": True, "action": "streak_reported"}
        except Exception as e:
            send_telegram_message(chat_id, f"⚠️ Could not check LeetCode status right now: {e}")
            return {"handled": True, "action": "streak_error"}

    # Command 3: /help
    if text.startswith("/help"):
        send_telegram_message(
            chat_id,
            "🛡️ <b>LeetCode Streak Guardian Bot Commands:</b>\n\n"
            "🔥 <code>/streak</code> - Check your live streak & today's submissions\n"
            "ℹ️ <code>/help</code> - Show this commands message\n\n"
            "We automatically check your profile around the clock and alert you every 4 hours if today's problem hasn't been solved!"
        )
        return {"handled": True, "action": "help_sent"}

    return {"handled": False, "reason": "unrecognized_command"}


def sync_telegram_account_links() -> dict:
    """
    Fetch recent updates from Telegram and automatically process deep links and commands.
    Returns:
        dict: {"connected_users": list_of_user_ids, "count": int}
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        return {"connected_users": [], "count": 0}

    try:
        resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getUpdates", timeout=12)
        if resp.status_code != 200 or not resp.json().get("ok"):
            return {"connected_users": [], "count": 0}
        
        updates = resp.json().get("result", [])
        if not updates:
            return {"connected_users": [], "count": 0}

        connected = []
        highest_update_id = 0

        for item in updates:
            up_id = item.get("update_id", 0)
            if up_id > highest_update_id:
                highest_update_id = up_id

            res = process_telegram_update(item)
            if res.get("action") == "linked" and res.get("user_id"):
                connected.append(res["user_id"])

        # Acknowledge updates up to highest_update_id so we don't process repeatedly
        if highest_update_id > 0:
            try:
                requests.get(
                    f"https://api.telegram.org/bot{bot_token}/getUpdates",
                    params={"offset": highest_update_id + 1},
                    timeout=5,
                )
            except Exception:
                pass

        return {"connected_users": connected, "count": len(connected)}
    except Exception as exc:
        logger.error(f"Error checking Telegram updates: {exc}")
        return {"connected_users": [], "count": 0}
