"""
ntfy.sh push notification service for LeetCode Streak Guardian.
Dispatches instant, zero-cost push notifications to Android, iOS, and Desktop devices.
Docs: https://ntfy.sh
"""

import logging
import re
import requests

logger = logging.getLogger(__name__)

NTFY_DEFAULT_SERVER = "https://ntfy.sh"


def sanitize_topic_name(topic: str) -> str:
    """
    Sanitizes ntfy topic name.
    Topics must consist of alphanumeric characters, hyphens, and underscores.
    """
    if not topic:
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", topic.strip())
    return cleaned[:64]


def send_ntfy_notification(
    topic: str,
    message: str,
    title: str = "🔥 LeetCode Streak Guardian",
    priority: str = "urgent",
    tags: str = "warning,fire",
    click_url: str = "https://leetcode.com/problemset/all/",
    action_label: str = "⚡ Solve on LeetCode",
) -> dict:
    """
    Dispatches a push notification to an ntfy topic via HTTP POST.

    Returns:
        dict: {"success": bool, "status_code": int, "mode": "live", "error": str | None}
    """
    clean_topic = sanitize_topic_name(topic)
    if not clean_topic:
        return {
            "success": False,
            "error": "A valid ntfy.sh topic name is required.",
            "mode": "failed",
        }

    url = f"{NTFY_DEFAULT_SERVER}/{clean_topic}"

    headers = {
        "Title": title.encode("utf-8"),
        "Priority": str(priority),
        "Tags": tags,
    }

    if click_url:
        headers["Click"] = click_url
        if action_label:
            # Add interactive action button directly in the push notification
            headers["Actions"] = f"view, {action_label}, {click_url}"

    try:
        response = requests.post(
            url,
            data=message.encode("utf-8"),
            headers=headers,
            timeout=10,
        )

        if response.status_code == 200:
            return {
                "success": True,
                "status_code": 200,
                "mode": "live",
                "message": f"Notification delivered to topic: {clean_topic}",
            }
        else:
            return {
                "success": False,
                "status_code": response.status_code,
                "mode": "live",
                "error": f"ntfy.sh returned HTTP {response.status_code}: {response.text.strip()}",
            }

    except requests.exceptions.RequestException as exc:
        logger.error(f"Failed to reach ntfy.sh API: {exc}")
        return {
            "success": False,
            "error": f"Network error contacting ntfy.sh: {exc}",
            "mode": "live",
        }


def send_ntfy_streak_reminder(
    topic: str,
    user,
    submissions_today: int = 0,
    current_streak: int = 0,
    date_utc: str = None,
) -> dict:
    """
    Dispatches an urgent LeetCode streak reminder push notification.
    """
    username = getattr(user, "leetcode_username", "Adventurer") or "Adventurer"
    streak_count = current_streak or 0
    date_str = date_utc or "today"

    message = (
        f"Hey @{username}, your {streak_count}-day streak will reset at UTC midnight!\n"
        f"You have submitted {submissions_today} problems for {date_str} (UTC).\n\n"
        f"Solve at least 1 problem now to protect your streak!"
    )

    return send_ntfy_notification(
        topic=topic,
        message=message,
        title=f"🔥 STREAK AT RISK ({streak_count} Days)",
        priority="5",  # Level 5 = max / urgent (wakes screen & rings)
        tags="warning,fire,rotating_light",
        click_url="https://leetcode.com/problemset/all/",
        action_label="⚡ Solve on LeetCode",
    )


def send_test_ntfy_alert(topic: str, user) -> dict:
    """
    Sends a test push notification to verify the user's device setup.
    """
    username = getattr(user, "leetcode_username", "Adventurer") or "Adventurer"
    streak_count = getattr(user, "current_streak", 0) or 0

    message = (
        f"🎉 Your mobile device is now connected to LeetCode Streak Guardian!\n"
        f"• Account: @{username}\n"
        f"• Current Streak: {streak_count} day(s)\n"
        f"• Status: 24/7 Autonomous Protection Active\n\n"
        f"You will receive loud alerts whenever your streak is at risk before UTC midnight."
    )

    return send_ntfy_notification(
        topic=topic,
        message=message,
        title="🔔 Streak Guardian: Push Alerts Active!",
        priority="4",  # High priority
        tags="white_check_mark,tada",
        click_url="https://leetcode.com/problemset/all/",
        action_label="Open LeetCode",
    )
