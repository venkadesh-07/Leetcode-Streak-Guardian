"""
Telegram Bot Notification Service for LeetCode Streak Guardian.
Delivers direct, private 1-on-1 messages to user chat IDs via Telegram Bot API.
"""

from datetime import datetime, timezone
import html
import logging
import os
import re
import requests

logger = logging.getLogger(__name__)


DEFAULT_BOT_TOKEN = "8669464605:AAHPnXQzw3Ia4xeK2EFZV0VyTZwn1SoLgT8"


def get_telegram_bot_token() -> str:
    """Retrieve the Telegram bot API token from environment with production fallback."""
    from flask import current_app, has_app_context
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token and has_app_context():
        token = current_app.config.get("TELEGRAM_BOT_TOKEN", "").strip()
    return token or DEFAULT_BOT_TOKEN


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

    bot_token = get_telegram_bot_token()

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
    from app.services.time_utils import get_time_remaining_until_reset, format_ist_date
    safe_username = html.escape(str(username))
    safe_streak = html.escape(str(current_streak))
    safe_submissions = html.escape(str(submissions_today))
    time_info = get_time_remaining_until_reset()
    safe_date_ist = html.escape(time_info.get("date_ist_str") or format_ist_date())
    time_display = time_info["time_display"]

    if time_info["hours"] <= 1:
        urgency_line = f"🚨 <b>CRITICAL:</b> Only <b>{time_display}</b> left before 05:30 AM IST reset!"
    elif time_info["hours"] <= 4:
        urgency_line = f"⏰ <b>URGENT:</b> Only <b>{time_display}</b> left before 05:30 AM IST reset!"
    else:
        urgency_line = f"⏳ <b>Time Remaining:</b> <b>{time_display}</b> before 05:30 AM IST reset"

    sub_count = int(submissions_today) if str(submissions_today).isdigit() else 0
    if sub_count == 0:
        headline = f"Hey <b>{safe_username}</b>, you haven't solved any problems yet today!"
        action_note = f"⚠️ Solve at least 1 problem before <b>05:30 AM IST</b> to keep your streak alive!"
    else:
        headline = f"Hey <b>{safe_username}</b>, you have solved <b>{safe_submissions}/3</b> problem(s) today!"
        action_note = f"⚠️ Daily Goal: Complete at least 3 problems today (currently <b>{safe_submissions}/3</b>) before <b>05:30 AM IST</b>!"

    message_text = (
        f"🔥 <b>LeetCode Streak Alert!</b>\n\n"
        f"{headline}\n\n"
        f"📊 <b>Current Streak:</b> <code>{safe_streak} days</code>\n"
        f"{urgency_line}\n"
        f"⚡ <b>Today's Submissions:</b> <code>{safe_submissions}</code> (Goal: 3)\n"
        f"📅 <b>Date (IST):</b> <code>{safe_date_ist}</code>\n"
        f"⏰ <b>Reset Deadline:</b> <b>05:30 AM IST</b>\n\n"
        f"{action_note}\n\n"
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
    bot_token = get_telegram_bot_token()
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
    """Send a plain or HTML message via the configured Telegram Bot with plain text fallback."""
    bot_token = get_telegram_bot_token()
    if not bot_token or not chat_id:
        logger.warning(f"send_telegram_message: Missing bot_token or chat_id (chat_id: {chat_id})")
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": str(chat_id).strip(), "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json().get("ok", False):
            return True

        # If HTML parsing failed or Telegram rejected formatting, retry as plain text without parse_mode
        plain_text = re.sub(r"<[^>]+>", "", text)
        resp2 = requests.post(
            url,
            json={"chat_id": str(chat_id).strip(), "text": plain_text},
            timeout=10,
        )
        return resp2.status_code == 200 and resp2.json().get("ok", False)
    except Exception as e:
        logger.warning(f"Error sending Telegram message to {chat_id}: {e}")
        return False


def _build_welcome_single(user, first_name=None, tip_type="pin"):
    """Build welcome HTML for a single linked account."""
    safe_name = html.escape(str(user.leetcode_username or first_name or "Streak Guardian"))
    tip = (
        "💡 <i>Tip: Sharing this Telegram with friends? They can send their own 6-digit PIN in this chat to receive their alerts here too!</i>"
        if tip_type == "pin"
        else "We'll alert you right here whenever your streak is at risk before 05:30 AM IST reset!"
    )
    return (
        f"🎉 <b>LeetCode Streak Guardian Connected!</b>\n\n"
        f"Welcome, <b>{safe_name}</b>!\n"
        f"Your Telegram account is now linked to <code>{html.escape(str(user.email))}</code>.\n\n"
        f"⚡ <b>Commands you can use anytime:</b>\n"
        f"🔥 <code>/streak</code> - Check live LeetCode streak & today's progress\n"
        f"ℹ️ <code>/help</code> - View bot commands\n\n"
        f"{tip}"
    )


def _build_welcome_squad(user, all_linked, first_name=None):
    """Build welcome HTML for a shared squad inbox."""
    safe_name = html.escape(str(user.leetcode_username or first_name or "Streak Guardian"))
    accounts_list = []
    for idx, acc in enumerate(all_linked, 1):
        uname = acc.leetcode_username or acc.email
        accounts_list.append(f"{idx}. <b>{html.escape(str(uname))}</b> (<code>{html.escape(str(acc.email))}</code>)")
    accounts_str = "\n".join(accounts_list)
    return (
        f"🎉 <b>Account Connected! (Shared Squad Inbox)</b>\n\n"
        f"Welcome, <b>{safe_name}</b>!\n"
        f"Your Telegram is now linked to <code>{html.escape(str(user.email))}</code>.\n\n"
        f"👥 <b>Active accounts in this chat ({len(all_linked)}):</b>\n"
        f"{accounts_str}\n\n"
        f"All linked accounts will receive daily streak reminders right here!\n"
        f"🔥 Send <code>/streak</code> anytime to check everyone's live progress."
    )


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
    import html
    import time
    now_ts = int(time.time())

    # Option B + Idea 1: Detect 6-digit numeric pairing PIN
    # Matches patterns like: "842190", "842 190", "842-190", "/link 842190", "/pin 842190", "/start 842190"
    pin_match = re.search(r"^(?:/(?:start|link|pin)[=\s]+)?\s*(\d{3})[\s-]?(\d{3})\s*$", text)
    if pin_match:
        pin_code = f"{pin_match.group(1)}{pin_match.group(2)}"
        matched_user = User.query.filter_by(telegram_pin=pin_code).first()

        if matched_user:
            if matched_user.telegram_pin_expires_at and matched_user.telegram_pin_expires_at < now_ts:
                send_telegram_message(
                    chat_id,
                    "⏱️ <b>This pairing PIN has expired (valid for 15 minutes).</b>\n\n"
                    "Please refresh your Streak Guardian Settings page on the website to generate a fresh 6-digit PIN."
                )
                return {"handled": True, "action": "expired_pin"}

            # Connect user to this Telegram Chat without unlinking friends (Option B: Shared Chat Support)
            matched_user.telegram_chat_id = chat_id
            matched_user.notify_telegram = True
            matched_user.telegram_pin = None
            matched_user.telegram_pin_expires_at = None
            db.session.commit()

            all_linked = User.query.filter_by(telegram_chat_id=chat_id).all()
            if len(all_linked) > 1:
                welcome_text = _build_welcome_squad(matched_user, all_linked, first_name)
            else:
                welcome_text = _build_welcome_single(matched_user, first_name, tip_type="pin")

            send_telegram_message(chat_id, welcome_text)
            return {"handled": True, "action": "linked", "user_id": matched_user.id, "mode": "pin"}
        else:
            send_telegram_message(
                chat_id,
                "⚠️ <b>Invalid pairing PIN.</b>\n\n"
                "Please verify the 6-digit PIN on your Streak Guardian Settings page and try again."
            )
            return {"handled": True, "action": "invalid_pin"}

    # Extract token from various legacy or deep-link formats:
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
            # Option B: Do NOT unlink existing accounts so multiple accounts can share 1 Telegram
            user.telegram_chat_id = chat_id
            user.notify_telegram = True
            db.session.commit()

            all_linked = User.query.filter_by(telegram_chat_id=chat_id).all()
            if len(all_linked) > 1:
                welcome_text = _build_welcome_squad(user, all_linked, first_name)
            else:
                welcome_text = _build_welcome_single(user, first_name, tip_type="token")
            send_telegram_message(chat_id, welcome_text)
            return {"handled": True, "action": "linked", "user_id": user.id, "mode": "token"}
        else:
            send_telegram_message(
                chat_id,
                "⚠️ <b>Invalid or expired sync token.</b>\n\n"
                "Please visit your Streak Guardian Dashboard Settings and use the 6-digit PIN or fresh link."
            )
            return {"handled": True, "action": "invalid_token"}

    # Plain /start or /link without token or pin
    if text.startswith("/start") or text.startswith("/link"):
        linked_users = User.query.filter_by(telegram_chat_id=chat_id).all()
        if linked_users:
            if len(linked_users) == 1:
                u = linked_users[0]
                send_telegram_message(
                    chat_id,
                    f"👋 Hello <b>{html.escape(str(u.leetcode_username or first_name))}</b>!\n\n"
                    f"This chat is currently linked to <b>{html.escape(str(u.email))}</b>.\n\n"
                    f"🔥 Send <code>/streak</code> to view live stats.\n"
                    f"➕ To connect additional accounts to this chat, simply send their 6-digit pairing PIN!"
                )
            else:
                names = ", ".join([html.escape(str(u.leetcode_username or u.email)) for u in linked_users])
                send_telegram_message(
                    chat_id,
                    f"👋 Hello Squad!\n\n"
                    f"This chat is connected to <b>{len(linked_users)} accounts</b>: {names}.\n\n"
                    f"🔥 Send <code>/streak</code> to view live stats for everyone.\n"
                    f"➕ To link another account, simply send its 6-digit pairing PIN."
                )
        else:
            send_telegram_message(
                chat_id,
                f"👋 <b>Welcome to LeetCode Streak Guardian!</b>\n\n"
                f"To connect your account and receive autonomous streak alerts:\n"
                f"1️⃣ Open your <b>LeetCode Streak Guardian Settings</b>\n"
                f"2️⃣ Look for your bold <b>6-digit Pairing PIN</b>\n"
                f"3️⃣ Send the 6 digits right here in this chat (e.g. <code>842190</code>)!"
            )
        return {"handled": True, "action": "start_help"}

    # Command 2: /streak or /today or /status
    if text in ("/streak", "/today", "/status", "streak", "status"):
        users = User.query.filter_by(telegram_chat_id=chat_id).all()
        if not users:
            send_telegram_message(
                chat_id,
                "⚠️ Your Telegram is not linked to any LeetCode Streak Guardian account yet.\n"
                "Visit your website settings and send your 6-digit PIN here to link."
            )
            return {"handled": True, "action": "not_linked"}

        from app.services.leetcode_checker import check_daily_activity

        if len(users) == 1:
            user = users[0]
            if not user.leetcode_username:
                send_telegram_message(
                    chat_id,
                    "⚠️ You have not set a LeetCode username yet in your website dashboard settings."
                )
                return {"handled": True, "action": "no_username"}

            try:
                result = check_daily_activity(user.leetcode_username)
                user.current_streak = result.get("current_streak", 0)
                user.today_submissions = result.get("submissions_today", 0)
                user.is_active_today = result.get("active_today", False)
                user.last_checked_date_utc = result.get("checked_date_utc")
                db.session.commit()

                from app.services.time_utils import get_time_remaining_until_reset, format_ist_date
                time_info = get_time_remaining_until_reset()
                ist_date_str = time_info.get("date_ist_str") or format_ist_date()
                status_icon = "✅ Streak Protected!" if user.is_active_today else "⚠️ Streak At Risk!"
                msg_reply = (
                    f"🔥 <b>LeetCode Streak Status</b>\n\n"
                    f"👤 <b>User:</b> <code>{html.escape(str(user.leetcode_username))}</code>\n"
                    f"📊 <b>Current Streak:</b> <code>{user.current_streak} days</code>\n"
                    f"⚡ <b>Today's Submissions:</b> <code>{user.today_submissions}</code>\n"
                    f"🛡️ <b>Status:</b> <b>{status_icon}</b>\n"
                    f"📅 <b>Date (IST):</b> <code>{ist_date_str}</code>\n"
                    f"⏰ <b>Reset Deadline:</b> <code>05:30 AM IST</code> ({time_info['time_display']} left)\n\n"
                    f"{'Keep up the great work! Streak is protected until next reset.' if user.is_active_today else 'Solve at least 1 problem before 05:30 AM IST to maintain your streak!'}"
                )
                send_telegram_message(chat_id, msg_reply)
                return {"handled": True, "action": "streak_reported"}
            except Exception as e:
                send_telegram_message(chat_id, f"⚠️ Could not check LeetCode status right now: {e}")
                return {"handled": True, "action": "streak_error"}

        else:
            # Multi-user Option B Squad report!
            cards = []
            for idx, u in enumerate(users, 1):
                if not u.leetcode_username:
                    cards.append(f"{idx}️⃣ <b>{html.escape(str(u.email))}</b>: <i>No LeetCode username configured</i>")
                    continue
                try:
                    result = check_daily_activity(u.leetcode_username)
                    u.current_streak = result.get("current_streak", 0)
                    u.today_submissions = result.get("submissions_today", 0)
                    u.is_active_today = result.get("active_today", False)
                    u.last_checked_date_utc = result.get("checked_date_utc")
                    status_icon = "✅ Protected" if u.is_active_today else "⚠️ At Risk!"
                    cards.append(
                        f"{idx}️⃣ <b>{html.escape(str(u.leetcode_username))}</b> (<code>{html.escape(str(u.email))}</code>)\n"
                        f"   📊 Streak: <b>{u.current_streak} days</b> | Today: <b>{u.today_submissions}</b> solved ({status_icon})"
                    )
                except Exception:
                    status_icon = "✅ Protected" if u.is_active_today else "⚠️ At Risk!"
                    cards.append(
                        f"{idx}️⃣ <b>{html.escape(str(u.leetcode_username))}</b>\n"
                        f"   📊 Streak: <b>{u.current_streak or 0} days</b> | Today: <b>{u.today_submissions or 0}</b> solved ({status_icon})"
                    )

            db.session.commit()
            summary_text = (
                f"🔥 <b>LeetCode Squad Streaks ({len(users)} Linked Accounts)</b>\n\n"
                + "\n\n".join(cards)
                + "\n\n🛡️ <i>Solve today's problem before 05:30 AM IST to keep all streaks alive!</i>"
            )
            send_telegram_message(chat_id, summary_text)
            return {"handled": True, "action": "squad_streak_reported", "count": len(users)}

    # Command 3: /help
    if text.startswith("/help"):
        send_telegram_message(
            chat_id,
            "🛡️ <b>LeetCode Streak Guardian Bot Commands:</b>\n\n"
            "🔢 <code>&lt;6-Digit PIN&gt;</code> - Link any website account directly\n"
            "🔥 <code>/streak</code> - Check live streak & today's submissions (for all linked accounts)\n"
            "ℹ️ <code>/help</code> - Show this commands message\n\n"
            "💡 <b>Shared Chat Support:</b> Multiple friends can send their 6-digit PIN in this chat so everyone gets notified together!\n"
            "We automatically check your profile and alert you if today's problem hasn't been solved!"
        )
        return {"handled": True, "action": "help_sent"}

    return {"handled": False, "reason": "unrecognized_command"}



def sync_telegram_account_links() -> dict:
    """
    Fetch recent updates from Telegram and automatically process deep links and commands.
    Returns:
        dict: {"connected_users": list_of_user_ids, "count": int}
    """
    bot_token = get_telegram_bot_token()
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
