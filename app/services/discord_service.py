"""
Discord Webhook Notification Service for LeetCode Streak Guardian.
Delivers rich embedded notifications to user-configured Discord channels.
"""

from datetime import datetime, timezone
import logging
import os
import re
import requests

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_PATTERN = re.compile(
    r"^https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+$"
)


def validate_discord_webhook_url(url: str) -> bool:
    """Validate that the provided string matches Discord's official webhook URL format."""
    if not isinstance(url, str):
        return False
    return bool(DISCORD_WEBHOOK_PATTERN.match(url.strip()))


def send_discord_streak_reminder(
    webhook_url: str,
    user,
    submissions_today: int,
    current_streak: int,
    date_utc: str,
) -> dict:
    """
    Dispatch a rich embed notification to the user's Discord webhook.

    Returns:
        dict: {"success": bool, "mode": "discord"|"simulated", "error": str|None}
    """
    if not webhook_url:
        return {"success": False, "error": "Discord webhook URL is empty."}

    webhook_url = webhook_url.strip()

    if not validate_discord_webhook_url(webhook_url):
        return {"success": False, "error": "Invalid Discord webhook URL format."}

    # Simulation mode for testing environments
    if os.environ.get("SIMULATE_DISCORD", "").lower() in ("true", "1") or "simulate" in webhook_url:
        logger.info(f"[DISCORD SIMULATION] Dispatched alert for {user.email} (Streak: {current_streak})")
        return {"success": True, "mode": "simulated"}

    now_iso = datetime.now(timezone.utc).isoformat()
    username = getattr(user, "leetcode_username", None) or getattr(user, "email", "Coder")

    embed = {
        "title": "🔥 LeetCode Streak at Risk!",
        "description": (
            f"Hey **{username}**, you haven't solved any problems yet today!\n"
            f"Your **{current_streak}-day streak** is about to reset."
        ),
        "color": 0xF59E0B,  # Vibrant amber/orange
        "fields": [
            {
                "name": "🔥 Current Streak",
                "value": f"**{current_streak} days**",
                "inline": True,
            },
            {
                "name": "⚡ Today's Submissions",
                "value": f"**{submissions_today}**",
                "inline": True,
            },
            {
                "name": "📅 Date (UTC)",
                "value": f"`{date_utc}`",
                "inline": True,
            },
            {
                "name": "🎯 Take Action",
                "value": "[👉 Click here to solve today's challenge on LeetCode](https://leetcode.com/problemset/all/)",
                "inline": False,
            },
        ],
        "footer": {
            "text": "LeetCode Streak Guardian • Autonomous Protection",
            "icon_url": "https://assets.leetcode.com/static_assets/public/icons/favicon-192x192.png",
        },
        "timestamp": now_iso,
    }

    payload = {
        "username": "LeetCode Streak Guardian",
        "avatar_url": "https://assets.leetcode.com/static_assets/public/icons/favicon-192x192.png",
        "embeds": [embed],
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        # Discord returns 204 No Content on successful message creation
        if response.status_code in (200, 204):
            logger.info(f"Discord alert dispatched successfully to webhook for {user.email}")
            return {"success": True, "mode": "discord"}
        elif response.status_code == 429:
            logger.warning(f"Discord rate limited for {user.email}")
            return {"success": False, "error": "Discord rate limit reached. Please try again later."}
        elif response.status_code == 404:
            return {"success": False, "error": "Webhook not found or deleted on Discord."}
        else:
            return {
                "success": False,
                "error": f"Discord returned status {response.status_code}: {response.text}",
            }
    except requests.RequestException as exc:
        logger.error(f"Network error sending Discord notification: {exc}")
        return {"success": False, "error": f"Connection error: {exc}"}
