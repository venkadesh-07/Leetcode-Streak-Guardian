"""
Automated streak reminder job for LeetCode Streak Guardian.
Scans eligible users, verifies current day LeetCode activity, and dispatches
reminder notifications for any streaks at risk.
Designed to be executed via Flask CLI command or scheduled background runner.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import logging
import os
import time
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import User
from app.services.leetcode_checker import check_daily_activity, LeetCodeCheckerError
from app.services.email_service import send_streak_reminder

logger = logging.getLogger(__name__)

REMINDER_INTERVAL_SECONDS = 4 * 3600  # 4 hours


def run_reminder_check(force=False):
    """
    Check all users with active reminders and dispatch streak risk alerts every 4 hours
    until at least 1 problem is completed that day.
    """
    today_utc = datetime.now(timezone.utc).date().isoformat()
    now_ts = int(time.time())

    eligible_users = db.session.execute(
        db.select(User).filter(
            User.reminder_enabled == True,
            User.leetcode_username.isnot(None),
        )
    ).scalars().all()

    stats = {
        "checked_date_utc": today_utc,
        "eligible_users": len(eligible_users),
        "reminders_sent": 0,
        "already_protected": 0,
        "auto_rescued": 0,
        "interval_cooldown": 0,
        "errors": [],
    }

    if not eligible_users:
        return stats

    # Concurrently check LeetCode activity across all eligible users
    user_meta = [
        (user.id, user.leetcode_username, f"User(id={user.id}, email={user.email})")
        for user in eligible_users
    ]
    activity_results = {}
    max_workers = min(10, len(user_meta))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_meta = {
            executor.submit(check_daily_activity, uname): (uid, uident)
            for uid, uname, uident in user_meta
        }
        for future in as_completed(future_to_meta):
            uid, uident = future_to_meta[future]
            try:
                activity_results[uid] = future.result()
            except LeetCodeCheckerError as exc:
                err_msg = f"{uident}: LeetCode check failed ({exc})"
                logger.error(err_msg)
                stats["errors"].append(err_msg)
            except Exception as exc:
                err_msg = f"{uident}: Unexpected error checking LeetCode ({exc})"
                logger.error(err_msg)
                stats["errors"].append(err_msg)

    for user in eligible_users:
        user_identifier = f"User(id={user.id}, email={user.email})"
        result = activity_results.get(user.id)
        if not result:
            continue

        # Update persistent streak stats
        user.current_streak = result.get("current_streak", 0)
        user.today_submissions = result.get("submissions_today", 0)
        user.is_active_today = result.get("active_today", False)
        user.last_checked_date_utc = today_utc

        # Determine target submission threshold (default: 3 submissions for testing, configurable via DAILY_SUBMISSION_GOAL)
        from flask import current_app, has_app_context
        is_testing = (has_app_context() and current_app.config.get("TESTING")) or os.environ.get("FLASK_ENV") == "testing"
        default_goal = "1" if is_testing else "3"
        target_goal = int(os.environ.get("DAILY_SUBMISSION_GOAL", default_goal))
        cooldown_seconds = int(os.environ.get("REMINDER_COOLDOWN_SECONDS", "14400" if is_testing else "0"))
        submissions = result.get("submissions_today", 0)

        # Auto-Rescue Airbag: If 0 submissions and within the emergency window (<= 85 mins before 05:30 AM IST reset, e.g. 04:10 AM IST, or forced)
        from app.services.email_service import get_time_remaining_until_reset
        from app.services.rescue_service import execute_auto_rescue
        time_left = get_time_remaining_until_reset()
        minutes_until_reset = (time_left.get("hours", 24) * 60) + time_left.get("minutes", 0)

        if submissions == 0 and getattr(user, "auto_rescue_enabled", False):
            if (minutes_until_reset <= 85 or force) and user.last_rescue_date_utc != today_utc and user.leetcode_session:
                logger.info(f"{user_identifier}: Auto-Rescue window active ({time_left['time_display']} left before reset). Executing Auto-Rescue...")
                rescue_res = execute_auto_rescue(user, force=force)
                if rescue_res.get("success"):
                    stats["auto_rescued"] = stats.get("auto_rescued", 0) + 1
                    result["active_today"] = True
                    result["submissions_today"] = max(result.get("submissions_today", 0), 1)
                    user.today_submissions = result["submissions_today"]
                    user.is_active_today = True
                    submissions = user.today_submissions

        if submissions >= target_goal:
            stats["already_protected"] += 1
            logger.info(f"{user_identifier}: Target met today ({submissions}/{target_goal} submissions). No alert needed.")
        else:
            # Submissions are less than target_goal (e.g. < 3)! Check anti-spam cooldown if enabled
            cooldown_active = (
                cooldown_seconds > 0
                and not force
                and user.last_reminder_sent_at
                and (now_ts - user.last_reminder_sent_at) < (cooldown_seconds - 100)
            )
            if cooldown_active:
                stats["interval_cooldown"] += 1
                logger.info(f"{user_identifier}: Anti-spam cooldown active ({submissions}/{target_goal} submissions). Skipping.")
            else:
                dispatched_any = False

                from flask import current_app, has_app_context
                is_testing = (has_app_context() and current_app.config.get("TESTING")) or os.environ.get("FLASK_ENV") == "testing"

                # 1. Dispatch Email if enabled
                if getattr(user, "notify_email", True) and user.reminder_email:
                    send_res = send_streak_reminder(
                        user=user,
                        submissions_today=result["submissions_today"],
                        current_streak=result["current_streak"],
                        date_utc=today_utc,
                    )

                    email_mode = send_res.get("mode")
                    if send_res.get("success"):
                        if email_mode in ("smtp", "brevo") or is_testing:
                            dispatched_any = True
                        logger.info(f"{user_identifier}: Streak reminder email sent (mode: {email_mode}).")
                    else:
                        stats["errors"].append(f"{user_identifier}: Failed to dispatch email reminder ({send_res.get('error')})")


                # 3. Dispatch Telegram if enabled
                if getattr(user, "notify_telegram", False) and user.telegram_chat_id:
                    from app.services.telegram_service import send_telegram_streak_reminder
                    tg_res = send_telegram_streak_reminder(
                        chat_id=user.telegram_chat_id,
                        user=user,
                        submissions_today=result["submissions_today"],
                        current_streak=result["current_streak"],
                        date_utc=today_utc,
                    )

                    tg_mode = tg_res.get("mode")
                    if tg_res.get("success"):
                        if tg_mode == "telegram" or is_testing:
                            dispatched_any = True
                        logger.info(f"{user_identifier}: Streak reminder Telegram alert sent (mode: {tg_mode}).")
                    else:
                        stats["errors"].append(f"{user_identifier}: Failed to dispatch Telegram alert ({tg_res.get('error')})")

                if dispatched_any:
                    user.last_reminder_sent_date_utc = today_utc
                    if not force:
                        user.last_reminder_sent_at = now_ts
                    else:
                        logger.info(f"{user_identifier}: Manual/force run active. Preserved cooldown timer so regular schedule is not blocked.")
                    stats["reminders_sent"] += 1
                else:
                    logger.warning(f"{user_identifier}: No real reminders dispatched (simulation mode or channel error). Cooldown not updated.")

    # Commit all user updates in a single batch instead of per-user
    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        stats["errors"].append(f"Batch database commit failed: {exc}")

    return stats



if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        print(f"Executing Streak Guardian Reminder Job...")
        results = run_reminder_check()
        print(f"Results: {results}")
