"""
API endpoints for LeetCode Streak Guardian.
Handles Telegram webhooks & link status polling, automated cron triggers,
desktop companion streak status, and health checks.
"""

from datetime import datetime, timezone, timedelta
import hmac
import os
import time

from flask import current_app, jsonify, request
from flask_login import current_user, login_required

from app.extensions import csrf, db, limiter
from app.models import User
from app.routes import main
from app.services.leetcode_checker import check_daily_activity

ACTIVITY_CHECK_COOLDOWN = 60


@main.route("/api/telegram/check-link-status", methods=["GET"])
def check_telegram_link_status():
    """
    Polled by settings page when user clicks 'Connect with Telegram'.
    Authenticates via active login session OR 'token' / 'X-API-Key' parameter.
    Pulls recent updates from Telegram, checks if user is linked,
    and returns real-time connection status.
    """
    user = None
    if current_user.is_authenticated:
        user = current_user
    else:
        token = request.headers.get("X-API-Key", "").strip() or request.args.get("token", "").strip()
        if token:
            user = db.session.execute(db.select(User).filter_by(api_token=token)).scalar_one_or_none()

    if not user:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    from app.services.telegram_service import sync_telegram_account_links, get_telegram_bot_username
    try:
        sync_telegram_account_links()
        db.session.refresh(user)
    except Exception:
        pass

    bot_username = get_telegram_bot_username()
    is_linked = bool(user.telegram_chat_id and user.notify_telegram)
    linked_count = (
        User.query.filter_by(telegram_chat_id=user.telegram_chat_id).count()
        if user.telegram_chat_id
        else 0
    )
    pin = user.get_or_create_telegram_pin()

    return jsonify({
        "status": "success",
        "linked": is_linked,
        "telegram_chat_id": user.telegram_chat_id or "",
        "bot_username": bot_username,
        "telegram_pin": pin,
        "linked_accounts_count": linked_count,
        "message": "Telegram successfully connected!" if is_linked else "Waiting for bot activation in Telegram...",
    }), 200


@main.route("/api/telegram/refresh-pin", methods=["POST"])
@login_required
def refresh_telegram_pin():
    """Generate a fresh 6-digit pairing PIN for the current user."""
    new_pin = current_user.get_or_create_telegram_pin(force_refresh=True)
    return jsonify({
        "status": "success",
        "pin": new_pin,
        "expires_in": 900,
        "message": "Fresh 6-digit pairing PIN generated."
    }), 200


@main.route("/api/telegram/webhook", methods=["POST"])
@csrf.exempt
def telegram_webhook():
    """Real-time Telegram Webhook endpoint."""
    update = request.get_json(silent=True) or {}
    from app.services.telegram_service import process_telegram_update
    result = process_telegram_update(update)
    return jsonify({"status": "ok", "result": result}), 200


@main.route("/api/cron/check-reminders", methods=["GET", "POST"])
@csrf.exempt
def trigger_cron_reminders():
    """
    Secure webhook endpoint called by external scheduler (e.g. GitHub Actions).
    Requires a secret token via 'secret' query param or 'Bearer <token>' in Authorization header.
    Validates token against CRON_SECRET or SECRET_KEY.
    """
    secret_param = request.args.get("secret", "").strip()
    auth_header = request.headers.get("Authorization", "").strip()
    bearer_token = ""
    if auth_header.startswith("Bearer "):
        bearer_token = auth_header[7:].strip()

    provided_token = secret_param or bearer_token

    expected_secret = os.getenv("CRON_SECRET", "").strip()
    if not expected_secret:
        expected_secret = current_app.config.get("SECRET_KEY", "").strip()

    if not provided_token or not expected_secret or not hmac.compare_digest(provided_token, expected_secret):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    from app.services.reminder_job import run_reminder_check
    stats = run_reminder_check()
    # Return a lightweight summary to stay within cron-job.org's response size limit.
    summary = {
        "checked_date_utc": stats.get("checked_date_utc"),
        "eligible_users": stats.get("eligible_users", 0),
        "reminders_sent": stats.get("reminders_sent", 0),
        "already_protected": stats.get("already_protected", 0),
        "interval_cooldown": stats.get("interval_cooldown", 0),
        "error_count": len(stats.get("errors", [])),
    }
    return jsonify({"status": "success", "results": summary}), 200


@main.route("/api/v1/streak-status", methods=["GET"])
@csrf.exempt
@limiter.limit("60 per minute")
def get_streak_status_api():
    """
    Public API endpoint consumed by the Desktop Companion App.
    Authenticates via:
      - 'X-API-Key' header
      - 'Authorization: Bearer <token>' header
      - 'token' query parameter
    """
    token = request.headers.get("X-API-Key", "").strip()
    if not token:
        auth_header = request.headers.get("Authorization", "").strip()
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if not token:
        token = request.args.get("token", "").strip()

    if not token:
        return jsonify({"status": "error", "message": "Missing API token"}), 401

    user = db.session.execute(
        db.select(User).filter_by(api_token=token)
    ).scalar_one_or_none()

    if not user:
        return jsonify({"status": "error", "message": "Invalid API token"}), 401

    now_utc = datetime.now(timezone.utc)
    today_utc = now_utc.date().isoformat()
    now_ts = int(time.time())

    # Calculate hours and minutes remaining before UTC midnight
    midnight_utc = datetime.combine(
        now_utc.date() + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    seconds_left = max(0, int((midnight_utc - now_utc).total_seconds()))
    hours_left = seconds_left // 3600
    minutes_left = (seconds_left % 3600) // 60

    # Auto-refresh if requested or if today hasn't been checked yet
    refresh_requested = request.args.get("refresh", "").lower() in ("true", "1")
    needs_refresh = (
        user.leetcode_username
        and (refresh_requested or user.last_checked_date_utc != today_utc)
        and (not user.last_activity_check_at or (now_ts - user.last_activity_check_at) >= ACTIVITY_CHECK_COOLDOWN)
    )

    if needs_refresh:
        user.last_activity_check_at = now_ts
        try:
            db.session.commit()
            result = check_daily_activity(user.leetcode_username)
            user.current_streak = result.get("current_streak", 0)
            user.today_submissions = result.get("submissions_today", 0)
            user.is_active_today = result.get("active_today", False)
            user.last_checked_date_utc = result.get("checked_date_utc", today_utc)
            db.session.commit()
        except Exception:
            db.session.rollback()

    is_active = bool(user.is_active_today)
    submissions = user.today_submissions or 0
    streak_count = user.current_streak or 0

    if not user.leetcode_username:
        alert_msg = "Please configure your LeetCode username in the web dashboard."
        alert_needed = False
    elif not is_active:
        alert_msg = (
            f"🔥 LeetCode Streak at Risk!\n"
            f"You haven't solved a problem today.\n"
            f"Keep your {streak_count}-day streak alive! ({hours_left}h {minutes_left}m remaining)"
        )
        alert_needed = True
    else:
        alert_msg = (
            f"🎉 Streak Protected!\n"
            f"You solved {submissions} problem(s) today. Current streak: {streak_count} days."
        )
        alert_needed = False

    return jsonify({
        "status": "success",
        "user": {
            "email": user.email,
            "leetcode_username": user.leetcode_username,
        },
        "streak": {
            "current_streak": streak_count,
            "submissions_today": submissions,
            "active_today": is_active,
            "last_checked_date_utc": user.last_checked_date_utc or today_utc,
        },
        "time_remaining": {
            "hours": hours_left,
            "minutes": minutes_left,
            "formatted": f"{hours_left}h {minutes_left}m left today",
        },
        "alert_needed": alert_needed,
        "message": alert_msg,
        "solve_url": "https://leetcode.com/problemset/all/",
    }), 200


@main.route("/health")
@csrf.exempt
def health():
    return jsonify({"status": "ok", "timestamp": int(time.time())}), 200
