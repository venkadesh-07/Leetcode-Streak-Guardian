
import time

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.extensions import db ,limiter
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
@limiter.limit("5 per hour")
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
@limiter.limit("5 per minute")
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

    return render_template("settings.html", form=form)
