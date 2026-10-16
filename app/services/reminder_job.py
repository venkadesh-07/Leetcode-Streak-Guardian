"""
Automated streak reminder job for LeetCode Streak Guardian.
Scans eligible users, verifies current day LeetCode activity, and dispatches
reminder notifications for any streaks at risk.
Designed to be executed via Flask CLI command or scheduled background runner.
"""

from datetime import datetime, timezone
import logging
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import User
from app.services.leetcode_checker import check_daily_activity, LeetCodeCheckerError
from app.services.email_service import send_streak_reminder

logger = logging.getLogger(__name__)


def run_reminder_check():
    """
    Check all users with active reminders and dispatch streak risk alerts if inactive.

    Returns:
        dict: Summary statistics of the reminder check.
    """
    today_utc = datetime.now(timezone.utc).date().isoformat()

    eligible_users = db.session.execute(
        db.select(User).filter(
            User.reminder_enabled == True,
            User.reminder_email.isnot(None),
            User.leetcode_username.isnot(None),
        )
    ).scalars().all()

    stats = {
        "checked_date_utc": today_utc,
        "eligible_users": len(eligible_users),
        "reminders_sent": 0,
        "already_protected": 0,
        "already_reminded_today": 0,
        "errors": [],
    }

    for user in eligible_users:
        user_identifier = f"User(id={user.id}, email={user.email})"

        # Avoid spamming the user if a reminder was already dispatched today
        if user.last_reminder_sent_date_utc == today_utc:
            stats["already_reminded_today"] += 1
            logger.info(f"{user_identifier}: Reminder already sent for {today_utc}. Skipping.")
            continue

        try:
            result = check_daily_activity(user.leetcode_username)
        except LeetCodeCheckerError as exc:
            err_msg = f"{user_identifier}: LeetCode check failed ({exc})"
            logger.error(err_msg)
            stats["errors"].append(err_msg)
            continue

        # Update persistent streak stats
        user.current_streak = result.get("current_streak", 0)
        user.today_submissions = result.get("submissions_today", 0)
        user.is_active_today = result.get("active_today", False)
        user.last_checked_date_utc = today_utc

        if result["active_today"]:
            stats["already_protected"] += 1
            logger.info(f"{user_identifier}: Streak protected today ({result['submissions_today']} submissions). No alert needed.")
        else:
            # Dispatch reminder
            send_res = send_streak_reminder(
                user=user,
                submissions_today=result["submissions_today"],
                current_streak=result["current_streak"],
                date_utc=today_utc,
            )

            if send_res.get("success"):
                user.last_reminder_sent_date_utc = today_utc
                stats["reminders_sent"] += 1
                logger.info(f"{user_identifier}: Streak reminder sent successfully (mode: {send_res.get('mode')}).")
            else:
                stats["errors"].append(f"{user_identifier}: Failed to dispatch reminder ({send_res.get('error')})")

        try:
            db.session.commit()
        except SQLAlchemyError as exc:
            db.session.rollback()
            stats["errors"].append(f"{user_identifier}: Database commit failed ({exc})")

    return stats


if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        print(f"Executing Streak Guardian Reminder Job...")
        results = run_reminder_check()
        print(f"Results: {results}")
