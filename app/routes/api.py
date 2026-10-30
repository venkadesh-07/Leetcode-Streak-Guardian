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
@limiter.limit("30 per minute")
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
@limiter.limit("60 per minute")
def telegram_webhook():
    """Real-time Telegram Webhook endpoint."""
    update = request.get_json(silent=True) or {}
    from app.services.telegram_service import process_telegram_update
    result = process_telegram_update(update)
    return jsonify({"status": "ok", "result": result}), 200


@main.route("/api/cron/check-reminders", methods=["GET", "POST"])
@csrf.exempt
@limiter.limit("20 per minute")
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
        "job": "daily-reminders",
        "checked_date_utc": stats.get("checked_date_utc"),
        "eligible_users": stats.get("eligible_users", 0),
        "reminders_sent": stats.get("reminders_sent", 0),
        "already_protected": stats.get("already_protected", 0),
        "interval_cooldown": stats.get("interval_cooldown", 0),
        "auto_rescued": stats.get("auto_rescued", 0),
        "error_count": len(stats.get("errors", [])),
    }
    return jsonify({"status": "success", "results": summary}), 200


@main.route("/api/cron/auto-rescue", methods=["GET", "POST"])
@csrf.exempt
@limiter.limit("20 per minute")
def trigger_cron_auto_rescue():
    """
    Dedicated webhook endpoint specifically for the Emergency Auto-Rescue Airbag.
    Called at 04:10 AM IST by cron-job.org to ensure streaks are protected before the 05:30 AM IST reset.
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

    from app.services.time_utils import get_time_remaining_until_reset
    from app.services.rescue_service import execute_auto_rescue
    from app.services.leetcode_checker import check_daily_activity
    from app.models import User
    from app.extensions import db

    time_left = get_time_remaining_until_reset()
    minutes_left = (time_left.get("hours", 24) * 60) + time_left.get("minutes", 0)
    today_utc = datetime.now(timezone.utc).date().isoformat()
    force = request.args.get("force", "").lower() in ("true", "1", "yes")

    users = db.session.execute(
        db.select(User).filter_by(auto_rescue_enabled=True)
    ).scalars().all()

    rescued = 0
    statuses = []

    for user in users:
        activity = check_daily_activity(user.leetcode_username)
        submissions = activity.get("submissions_today", 0)

        # Trigger if (0 submissions and emergency window <= 85 mins) OR if force test is requested
        should_rescue = (submissions == 0 and minutes_left <= 85 and user.last_rescue_date_utc != today_utc) or force
        if should_rescue:
            if user.leetcode_session and user.leetcode_csrf_token:
                res = execute_auto_rescue(user, force=force)
                if res.get("success"):
                    rescued += 1
                statuses.append({"user": user.leetcode_username, "action": "auto-rescue executed", "result": res})
            else:
                statuses.append({"user": user.leetcode_username, "action": "missing cookies in profile"})
        else:
            if submissions > 0:
                statuses.append({"user": user.leetcode_username, "action": "already protected (submissions > 0)", "submissions_today": submissions})
            else:
                statuses.append({"user": user.leetcode_username, "action": "airbag standing by (not in emergency window)", "minutes_left": minutes_left})

    return jsonify({
        "status": "success",
        "job": "auto-rescue-airbag",
        "time_remaining_until_reset": time_left.get("time_display"),
        "minutes_until_reset": minutes_left,
        "eligible_users": len(users),
        "auto_rescued_count": rescued,
        "details": statuses,
    }), 200


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

    from app.services.time_utils import get_time_remaining_until_reset, format_ist_date
    time_info = get_time_remaining_until_reset()
    hours_left = time_info["hours"]
    minutes_left = time_info["minutes"]
    today_ist = time_info.get("date_ist_str") or format_ist_date()

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
            f"Keep your {streak_count}-day streak alive! ({time_info['time_display']} remaining before 05:30 AM IST reset)"
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
            "date_ist": today_ist,
        },
        "time_remaining": {
            "hours": hours_left,
            "minutes": minutes_left,
            "formatted": f"{time_info['time_display']} left before 05:30 AM IST reset",
            "reset_deadline_ist": "05:30 AM IST",
            "timezone": "IST",
        },
        "alert_needed": alert_needed,
        "message": alert_msg,
        "solve_url": "https://leetcode.com/problemset/all/",
    }), 200


@main.route("/api/validate-username", methods=["GET"])
@login_required
@limiter.limit("10 per minute")
def validate_username():
    """
    Inline LeetCode username validation for the settings page.
    Called via AJAX on blur of the username field.
    Returns whether the username resolves successfully on LeetCode.
    """
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"status": "error", "valid": False, "message": "Username is empty."}), 400

    import re
    if not re.match(r'^[a-zA-Z0-9_\-]{1,50}$', username):
        return jsonify({
            "status": "error",
            "valid": False,
            "message": "Invalid username format. Only letters, numbers, hyphens and underscores are allowed."
        }), 200

    from app.services.leetcode_checker import check_daily_activity, LeetCodeCheckerError
    try:
        result = check_daily_activity(username)
        streak = result.get("current_streak", 0)
        submissions = result.get("submissions_today", 0)
        return jsonify({
            "status": "success",
            "valid": True,
            "username": username,
            "current_streak": streak,
            "submissions_today": submissions,
            "message": f"✅ Found! {streak}-day streak · {submissions} submission(s) today."
        }), 200
    except LeetCodeCheckerError:
        return jsonify({
            "status": "error",
            "valid": False,
            "message": "❌ Username not found or LeetCode is unreachable. Double-check the spelling."
        }), 200


@main.route("/health")
@csrf.exempt
def health():
    return jsonify({"status": "ok", "timestamp": int(time.time())}), 200


@main.route("/api/verify-leetcode-bio", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def verify_leetcode_bio():
    """
    Check if the logged-in user's LeetCode 'About Me' bio contains their
    verification token. On success, marks the user as leetcode_verified.
    """
    username = current_user.leetcode_username
    token = current_user.verification_token

    if not username or not token:
        return jsonify({
            "status": "error",
            "message": "No LeetCode username or verification token found. Please save your username first."
        }), 400

    from app.services.leetcode_checker import check_username_ownership, LeetCodeCheckerError as _LeetCodeCheckerError
    try:
        found = check_username_ownership(username, token)
    except _LeetCodeCheckerError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 200

    if found:
        current_user.leetcode_verified = True
        db.session.commit()
        return jsonify({
            "status": "success",
            "verified": True,
            "message": "✅ Ownership confirmed! Your LeetCode username is now verified."
        }), 200

    return jsonify({
        "status": "success",
        "verified": False,
        "message": "❌ Token not found in your LeetCode About Me. Add it and try again."
    }), 200
