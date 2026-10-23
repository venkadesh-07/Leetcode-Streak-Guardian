"""
Settings and notification preference routes for LeetCode Streak Guardian.
Handles profile settings, alert preferences, test alerts, and Telegram disconnect.
"""

from datetime import datetime, timezone
from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, limiter
from app.forms import SettingsForm
from app.models import User
from app.routes import main
from app.services.email_service import send_streak_reminder
from app.services.telegram_service import get_telegram_bot_username, send_telegram_streak_reminder


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
        return redirect(url_for("main.dashboard"))

    # Auto-sync recent Telegram bot authorizations if user has an api_token
    token = current_user.get_or_create_api_token()
    telegram_pin = current_user.get_or_create_telegram_pin()
    db.session.commit()

    import urllib.parse
    bot_username = get_telegram_bot_username()
    telegram_connect_url = f"https://t.me/{bot_username}?start={token}"
    tg_uri = urllib.parse.quote(f"tg://resolve?domain={bot_username}&start={token}")
    telegram_web_url = f"https://web.telegram.org/k/#?tgaddr={tg_uri}"

    linked_accounts_count = (
        User.query.filter_by(telegram_chat_id=current_user.telegram_chat_id).count()
        if current_user.telegram_chat_id
        else 0
    )

    return render_template(
        "settings.html",
        form=form,
        telegram_connect_url=telegram_connect_url,
        telegram_web_url=telegram_web_url,
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
                f"ℹ️ Email delivery was simulated (neither BREVO_API_KEY nor SMTP_HOST is configured). Target: {target_email}.",
                "info",
            )
        else:
            channel_desc = " via Brevo HTTPS" if res.get("mode") == "brevo" else ""
            flash(
                f"Test alert email dispatched successfully{channel_desc} to {target_email}!",
                "success",
            )
    else:
        err_msg = str(res.get("error", ""))
        if "Network is unreachable" in err_msg or "101" in err_msg:
            flash(
                "⚠️ Outbound SMTP ports (587/465) are blocked by Render's free tier ([Errno 101] Network is unreachable). "
                "Add BREVO_API_KEY to your Render Dashboard ➔ Environment to deliver emails over HTTPS (Port 443) without port blocks!",
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
