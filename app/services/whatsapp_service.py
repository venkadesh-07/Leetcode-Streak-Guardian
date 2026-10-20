"""
WhatsApp notification service for LeetCode Streak Guardian using CallMeBot Gateway.
Dispatches streak risk reminders and verification alerts to users' personal WhatsApp.
"""

import logging
import re
import urllib.parse
import requests

logger = logging.getLogger(__name__)

CALLMEBOT_API_URL = "https://api.callmebot.com/whatsapp.php"


def sanitize_phone_number(phone: str) -> str:
    """
    Sanitize and format phone number for CallMeBot.
    CallMeBot accepts numbers with or without leading '+', containing international country code.
    Example: '+91 98765-43210' -> '+919876543210'
    """
    if not phone:
        return ""
    cleaned = re.sub(r"[^\d+]", "", phone.strip())
    # Ensure there is no '+' in the middle
    if "+" in cleaned:
        cleaned = "+" + cleaned.replace("+", "")
    return cleaned


def send_whatsapp_message(phone: str, apikey: str, message: str) -> dict:
    """
    Dispatches a WhatsApp message using the CallMeBot API.

    Returns:
        dict: {"success": bool, "status_code": int, "message": str, "mode": "live" | "simulated", "error": str | None}
    """
    cleaned_phone = sanitize_phone_number(phone)
    clean_apikey = (apikey or "").strip()

    if not cleaned_phone or not clean_apikey:
        return {
            "success": False,
            "error": "Phone number and CallMeBot API key are both required.",
            "mode": "failed",
        }

    params = {
        "phone": cleaned_phone,
        "text": message,
        "apikey": clean_apikey,
    }

    try:
        response = requests.get(CALLMEBOT_API_URL, params=params, timeout=12)
        resp_text = response.text or ""

        # CallMeBot typically returns HTTP 200 with text like:
        # "Message queued" or "Message sent" or "Success"
        # On error: "API Key not found", "Wrong phone number", etc.
        if response.status_code == 200:
            lower_resp = resp_text.lower()
            if "not found" in lower_resp or "error" in lower_resp or "invalid" in lower_resp or "failed" in lower_resp:
                return {
                    "success": False,
                    "status_code": 200,
                    "error": resp_text.strip(),
                    "mode": "live",
                }
            return {
                "success": True,
                "status_code": 200,
                "message": resp_text.strip() or "Message dispatched successfully.",
                "mode": "live",
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"CallMeBot API returned status {response.status_code}: {resp_text.strip()}",
                "mode": "live",
            }

    except requests.exceptions.RequestException as exc:
        logger.error(f"Failed to reach CallMeBot WhatsApp API: {exc}")
        return {
            "success": False,
            "error": f"Network error contacting CallMeBot API: {exc}",
            "mode": "live",
        }


def send_whatsapp_streak_reminder(
    phone: str,
    apikey: str,
    user,
    submissions_today: int = 0,
    current_streak: int = 0,
    date_utc: str = None,
) -> dict:
    """
    Constructs and dispatches an urgent LeetCode streak reminder to WhatsApp.
    """
    username = getattr(user, "leetcode_username", "Adventurer") or "Adventurer"
    streak_count = current_streak or 0
    date_str = date_utc or "today"

    msg = (
        f"🔥 *LEETCODE STREAK AT RISK!*\n\n"
        f"Hey @{username},\n"
        f"You have submitted *{submissions_today}* problem(s) for UTC date {date_str}.\n"
        f"Your active *{streak_count}-day streak* will reset at midnight UTC if you do not solve at least 1 problem!\n\n"
        f"⏳ *Action Required:* Solve a problem now to protect your streak:\n"
        f"👉 https://leetcode.com/problemset/all/\n\n"
        f"— _LeetCode Streak Guardian_"
    )

    return send_whatsapp_message(phone=phone, apikey=apikey, message=msg)


def send_test_whatsapp_message(phone: str, apikey: str, user) -> dict:
    """
    Sends a test verification alert to confirm the user's WhatsApp channel is working.
    """
    username = getattr(user, "leetcode_username", "Adventurer") or "Adventurer"
    streak_count = getattr(user, "current_streak", 0) or 0

    msg = (
        f"🎉 *LeetCode Streak Guardian: WhatsApp Connected!*\n\n"
        f"Hi @{username}, your WhatsApp alerts are now active!\n"
        f"• Current Streak: *{streak_count} day(s)*\n"
        f"• Status: *Active 24/7 Protection*\n\n"
        f"You will automatically receive reminders every 4 hours if you haven't solved your daily problem before UTC midnight.\n\n"
        f"Happy Coding! 🚀"
    )

    return send_whatsapp_message(phone=phone, apikey=apikey, message=msg)
