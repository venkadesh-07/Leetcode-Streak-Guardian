
from datetime import datetime, timezone, timedelta
import hmac
import os
import secrets
import time

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import csrf, db, limiter
from app.forms import LoginForm, RegistrationForm, SettingsForm
from app.models import User
from app.services.leetcode_checker import (
    LeetCodeCheckerError,
    check_daily_activity,
)


main = Blueprint("main", __name__)

ACTIVITY_CHECK_COOLDOWN = 60


@main.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    return render_template("index.html")


@main.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegistrationForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()

        existing_user = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()

        if existing_user:
            flash(
                "An account with this email already exists.",
                "error",
            )
            return render_template("register.html", form=form), 409

        user = User(email=email)
        user.set_password(form.password.data)

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "Registration could not be completed. Please try again.",
                "error",
            )
            return render_template("register.html", form=form), 409

        flash(
            "Account created successfully. You can now log in.",
            "success",
        )
        return redirect(url_for("main.login"))

    return render_template("register.html", form=form)


@main.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()

        user = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()

        if user and user.check_password(form.password.data):
            login_user(user, remember=False, fresh=True)
            return redirect(url_for("main.dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html", form=form)


@main.route("/dashboard")
@login_required
def dashboard():
    if not current_user.api_token:
        current_user.get_or_create_api_token()
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()

    now = int(time.time())
    last_check = current_user.last_activity_check_at
    cooldown_remaining = 0

    if last_check is not None:
        elapsed = now - last_check
        if 0 <= elapsed < ACTIVITY_CHECK_COOLDOWN:
            cooldown_remaining = ACTIVITY_CHECK_COOLDOWN - elapsed

    return render_template(
        "dashboard.html",
        user=current_user,
        cooldown_remaining=cooldown_remaining,
    )


@main.route("/check-activity", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def check_activity():
    if not current_user.leetcode_username:
        flash(
            "Please add your LeetCode username in settings first.",
            "error",
        )
        return redirect(url_for("main.dashboard"))

    now = int(time.time())
    last_check = current_user.last_activity_check_at

    if last_check is not None:
        elapsed = now - last_check

        if 0 <= elapsed < ACTIVITY_CHECK_COOLDOWN:
            remaining = ACTIVITY_CHECK_COOLDOWN - elapsed
            flash(
                f"Please wait {remaining} seconds before checking again.",
                "warning",
            )
            return redirect(url_for("main.dashboard"))

        # If the stored timestamp is unexpectedly in the future,
        # fail closed rather than allowing repeated requests.
        if elapsed < 0:
            flash(
                "Activity checking is temporarily unavailable. "
                "Please try again later.",
                "error",
            )
            return redirect(url_for("main.dashboard"))

    # Commit the timestamp before making the external request.
    # Failed external requests also use up the cooldown.
    current_user.last_activity_check_at = now

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash(
            "Unable to start the activity check. Please try again later.",
            "error",
        )
        return redirect(url_for("main.dashboard"))

    try:
        result = check_daily_activity(
            current_user.leetcode_username
        )
    except LeetCodeCheckerError:
        flash(
            "Unable to check LeetCode activity right now. "
            "Please try again later.",
            "error",
        )
        return redirect(url_for("main.dashboard"))

    # Persist streak and activity statistics to database
    current_user.current_streak = result.get("current_streak", 0)
    current_user.today_submissions = result.get("submissions_today", 0)
    current_user.is_active_today = result.get("active_today", False)
    current_user.last_checked_date_utc = result.get("checked_date_utc")

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()

    if result["active_today"]:
        flash(
            f"Activity detected for {result['checked_date_utc']} "
            f"(UTC): {result['submissions_today']} submission(s). "
            f"Current streak: {result['current_streak']} day(s)!",
            "success",
        )
    else:
        flash(
            f"No activity detected yet for {result['checked_date_utc']} "
            f"(UTC). Streak is at risk! "
            f"Current streak: {result['current_streak']} day(s).",
            "warning",
        )

    return redirect(url_for("main.dashboard"))


@main.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.home"))


@main.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form = SettingsForm(obj=current_user)

    if form.validate_on_submit():
        current_user.leetcode_username = (
            form.leetcode_username.data.strip()
            if form.leetcode_username.data
            else None
        )

        current_user.reminder_email = (
            form.reminder_email.data.strip().lower()
            if form.reminder_email.data
            else None
        )

        current_user.reminder_enabled = bool(
            form.reminder_enabled.data
        )

        current_user.notify_email = bool(
            form.notify_email.data
        )

        current_user.notify_telegram = bool(
            form.notify_telegram.data
        )

        current_user.telegram_chat_id = (
            form.telegram_chat_id.data.strip()
            if form.telegram_chat_id.data
            else None
        )

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash(
                "Settings could not be saved. Please try again.",
                "error",
            )
            return render_template("settings.html", form=form), 500

        flash("Settings saved successfully.", "success")
        return redirect(url_for("main.settings"))

    # Auto-sync recent Telegram bot authorizations if user has an api_token
    token = current_user.get_or_create_api_token()
    telegram_pin = current_user.get_or_create_telegram_pin()
    db.session.commit()

    from app.services.telegram_service import sync_telegram_account_links, get_telegram_bot_username
    # Sync in the background if accessed
    try:
        sync_telegram_account_links()
        db.session.refresh(current_user)
        if current_user.telegram_chat_id and not current_user.notify_telegram:
            current_user.notify_telegram = True
            db.session.commit()
        # Update form in case telegram was just connected
        form.telegram_chat_id.data = current_user.telegram_chat_id
        form.notify_telegram.data = current_user.notify_telegram
    except Exception:
        pass

    bot_username = get_telegram_bot_username()
    telegram_connect_url = f"https://t.me/{bot_username}?start={token}"
    linked_accounts_count = (
        User.query.filter_by(telegram_chat_id=current_user.telegram_chat_id).count()
        if current_user.telegram_chat_id
        else 0
    )

    return render_template(
        "settings.html",
        form=form,
        telegram_connect_url=telegram_connect_url,
        bot_username=bot_username,
        telegram_pin=telegram_pin,
        linked_accounts_count=linked_accounts_count,
    )



@main.route("/settings/test-email", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def send_test_email():
    """Send an instant sample streak reminder email to the user's configured address."""
    target_email = current_user.reminder_email or current_user.email
    if not target_email:
        flash("No email address configured to send a test alert.", "error")
        return redirect(url_for("main.settings"))

    from app.services.email_service import send_streak_reminder
    today_utc = datetime.now(timezone.utc).date().isoformat()
    res = send_streak_reminder(
        user=current_user,
        submissions_today=current_user.today_submissions or 0,
        current_streak=current_user.current_streak or 0,
        date_utc=today_utc,
    )

    if res.get("success"):
        if res.get("mode") == "simulated":
            flash(
                f"ℹ️ Email delivery was simulated (SMTP is not configured on this server). Target: {target_email}.",
                "info",
            )
        else:
            flash(
                f"Test alert email dispatched successfully to {target_email}!",
                "success",
            )
    else:
        err_msg = str(res.get("error", ""))
        if "Network is unreachable" in err_msg or "101" in err_msg:
            flash(
                "⚠️ Outbound SMTP ports (587/465) are blocked by Render's free tier ([Errno 101] Network is unreachable). "
                "Your automated cloud reminders on GitHub Actions and Telegram bot alerts work without restrictions!",
                "warning",
            )
        else:
            flash(
                f"Failed to dispatch test email: {err_msg}",
                "error",
            )

    return redirect(url_for("main.settings"))



@main.route("/settings/test-telegram", methods=["POST"])
@login_required
@limiter.limit("5 per minute")
def send_test_telegram():
    """Send an instant sample streak reminder message to the user's configured Telegram Chat ID."""
    chat_id = current_user.telegram_chat_id
    if not chat_id:
        flash("No Telegram Chat ID configured to send a test alert.", "error")
        return redirect(url_for("main.settings"))

    from app.services.telegram_service import send_telegram_streak_reminder
    today_utc = datetime.now(timezone.utc).date().isoformat()
    res = send_telegram_streak_reminder(
        chat_id=chat_id,
        user=current_user,
        submissions_today=current_user.today_submissions or 0,
        current_streak=current_user.current_streak or 0,
        date_utc=today_utc,
    )

    if res.get("success"):
        if res.get("mode") == "simulated":
            flash(
                "⚠️ TELEGRAM_BOT_TOKEN is missing in your server's environment variables (Render Dashboard). "
                "The alert was only simulated. Add TELEGRAM_BOT_TOKEN in your Render Dashboard ➔ Environment to deliver real Telegram messages.",
                "warning",
            )
        else:
            flash(
                f"🎉 Test Telegram alert sent live to your Telegram app (Chat ID {chat_id})!",
                "success",
            )
    else:
        flash(
            f"Failed to dispatch Telegram alert: {res.get('error')}",
            "error",
        )

    return redirect(url_for("main.settings"))


@main.route("/settings/disconnect-telegram", methods=["POST"])
@login_required
def disconnect_telegram():
    """Allows user to disconnect their Telegram account in 1 click."""
    current_user.telegram_chat_id = None
    current_user.notify_telegram = False
    try:
        db.session.commit()
        flash("Telegram account unlinked successfully.", "info")
    except SQLAlchemyError:
        db.session.rollback()
        flash("Could not unlink Telegram account. Please try again.", "error")
    return redirect(url_for("main.settings"))


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
    # Full error details are already written to server logs via logger.
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
