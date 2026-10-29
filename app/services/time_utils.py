"""
Time utility helpers for LeetCode Streak Guardian.
Standardizes all user-facing schedules, deadlines, timestamps, and alerts exclusively in Indian Standard Time (IST / Asia/Kolkata, UTC+05:30).
"""

from datetime import datetime, timezone, timedelta

# Indian Standard Time (UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def get_now_ist() -> datetime:
    """Return the current datetime in Indian Standard Time."""
    return datetime.now(timezone.utc).astimezone(IST)


def get_now_utc() -> datetime:
    """Return the current datetime in UTC."""
    return datetime.now(timezone.utc)


def format_ist_date(dt: datetime = None) -> str:
    """Format datetime as human-readable IST date, e.g. '24 Oct 2026'."""
    if dt is None:
        dt = get_now_ist()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime("%d %b %Y")


def format_ist_datetime(dt: datetime = None) -> str:
    """Format datetime as human-readable IST datetime, e.g. '24 Oct 2026, 11:45 AM IST'."""
    if dt is None:
        dt = get_now_ist()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime("%d %b %Y, %I:%M %p IST")


def get_time_remaining_until_reset(now: datetime = None) -> dict:
    """
    Calculate hours and minutes remaining until the next LeetCode daily reset.
    LeetCode resets globally at 23:59:59 UTC, which corresponds to 05:29:59 AM IST (05:30 AM IST).

    Returns:
        dict with:
          - hours (int)
          - minutes (int)
          - time_display (str) e.g. '17h 42m' or '45m'
          - reset_time_str (str) e.g. '05:30 AM IST'
          - urgency_level (str): 'critical', 'urgent', or 'warning'
          - urgency_badge (str)
          - badge_style (str)
          - subject_tag (str)
          - date_ist_str (str) e.g. '24 Oct 2026'
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Next UTC reset occurs at 23:59:59 UTC of the current UTC date
    reset_utc = now.replace(hour=23, minute=59, second=59, microsecond=0)
    if now > reset_utc:
        # Wrap to next day if microsecond timing edge case
        reset_utc += timedelta(days=1)

    diff_seconds = max(0, int((reset_utc - now).total_seconds()))
    hours = diff_seconds // 3600
    minutes = (diff_seconds % 3600) // 60

    now_ist = now.astimezone(IST)
    reset_ist = reset_utc.astimezone(IST)
    date_ist_str = now_ist.strftime("%d %b %Y")
    reset_time_str = "05:30 AM IST"

    if hours <= 1:
        urgency_level = "critical"
        time_display = f"{minutes}m" if hours == 0 else f"{hours}h {minutes}m"
        urgency_badge = f"🚨 CRITICAL: Only {time_display} Remaining Before 05:30 AM IST Reset!"
        badge_style = "background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.7);"
        subject_tag = f"🚨 [CRITICAL: {time_display} LEFT]"
    elif hours <= 4:
        urgency_level = "urgent"
        time_display = f"{hours}h {minutes}m"
        urgency_badge = f"⏰ URGENT: Only {time_display} Left Before 05:30 AM IST Reset!"
        badge_style = "background: rgba(245, 158, 11, 0.25); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.7);"
        subject_tag = f"⏰ [URGENT: {time_display} LEFT]"
    else:
        urgency_level = "warning"
        time_display = f"{hours} hours" if minutes == 0 else f"{hours}h {minutes}m"
        urgency_badge = f"⏳ {time_display} Remaining Before 05:30 AM IST Reset"
        badge_style = "background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4);"
        subject_tag = f"🔥 [{hours}h left]"

    return {
        "hours": hours,
        "minutes": minutes,
        "time_display": time_display,
        "reset_time_str": reset_time_str,
        "urgency_level": urgency_level,
        "urgency_badge": urgency_badge,
        "badge_style": badge_style,
        "subject_tag": subject_tag,
        "date_ist_str": date_ist_str,
        # Milliseconds since Unix epoch for the reset moment — used by the client-side live countdown.
        "reset_epoch_ms": int(reset_utc.timestamp() * 1000),
    }
