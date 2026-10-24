"""
Dashboard routes for LeetCode Streak Guardian.
Handles user dashboard rendering and manual LeetCode activity check.
"""

import time
from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, limiter
from app.routes import main
from app.services.leetcode_checker import check_daily_activity, LeetCodeCheckerError
from app.services.time_utils import get_time_remaining_until_reset, format_ist_date

ACTIVITY_CHECK_COOLDOWN = 60


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

    time_info = get_time_remaining_until_reset()

    return render_template(
        "dashboard.html",
        user=current_user,
        cooldown_remaining=cooldown_remaining,
        time_info=time_info,
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

    time_info = get_time_remaining_until_reset()
    date_ist_str = time_info.get("date_ist_str") or format_ist_date()

    if result["active_today"]:
        flash(
            f"Activity detected for {date_ist_str} (IST): "
            f"{result['submissions_today']} submission(s). "
            f"Current streak: {result['current_streak']} day(s)!",
            "success",
        )
    else:
        flash(
            f"No activity detected yet for {date_ist_str} (IST). "
            f"Streak is at risk! Solve before 05:30 AM IST to keep your "
            f"{result['current_streak']}-day streak alive.",
            "warning",
        )

    return redirect(url_for("main.dashboard"))
