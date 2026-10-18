
import re

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    EmailField,
    PasswordField,
    StringField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)


class RegistrationForm(FlaskForm):
    email = EmailField(
        "Email address",
        validators=[
            DataRequired(),
            Email(),
            Length(max=254),
        ],
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=12, max=128),
        ],
    )

    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )

    submit = SubmitField("Create account")

    def validate_password(self, field):
        password = field.data or ""

        if not re.search(r"[a-z]", password):
            raise ValidationError(
                "Password must contain a lowercase letter."
            )

        if not re.search(r"[A-Z]", password):
            raise ValidationError(
                "Password must contain an uppercase letter."
            )

        if not re.search(r"\d", password):
            raise ValidationError(
                "Password must contain a number."
            )


class LoginForm(FlaskForm):
    email = EmailField(
        "Email address",
        validators=[
            DataRequired(),
            Email(),
            Length(max=254),
        ],
    )

    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(max=128),
        ],
    )

    submit = SubmitField("Log in")


class SettingsForm(FlaskForm):
    leetcode_username = StringField(
        "LeetCode username",
        validators=[
            Optional(),
            Length(max=50),
            Regexp(
                r"^[A-Za-z0-9_-]+$",
                message=(
                    "Use only letters, numbers, "
                    "underscores, and hyphens."
                ),
            ),
        ],
    )

    reminder_email = EmailField(
        "Reminder email address",
        validators=[
            Optional(),
            Email(),
            Length(max=254),
        ],
    )

    reminder_enabled = BooleanField(
        "Enable Autonomous Streak Guardian Protection"
    )

    notify_email = BooleanField(
        "Send Email Reminders"
    )

    notify_desktop = BooleanField(
        "Enable Windows Desktop App Reminders"
    )

    notify_discord = BooleanField(
        "Enable Discord Channel Alerts"
    )

    discord_webhook_url = StringField(
        "Discord Webhook URL",
        validators=[
            Optional(),
            Length(max=255),
        ],
    )

    notify_telegram = BooleanField(
        "Enable Telegram Bot Private Alerts"
    )

    telegram_chat_id = StringField(
        "Telegram Chat ID",
        validators=[
            Optional(),
            Length(max=64),
        ],
    )

    submit = SubmitField("Save settings")

    def validate_discord_webhook_url(self, field):
        url = (field.data or "").strip()
        if url:
            from app.services.discord_service import validate_discord_webhook_url
            if not validate_discord_webhook_url(url):
                raise ValidationError(
                    "Invalid Discord Webhook URL. It must start with https://discord.com/api/webhooks/..."
                )

    def validate_telegram_chat_id(self, field):
        cid = (field.data or "").strip()
        if cid:
            from app.services.telegram_service import validate_telegram_chat_id
            if not validate_telegram_chat_id(cid):
                raise ValidationError(
                    "Invalid Telegram Chat ID. Chat ID must be numeric (e.g. 123456789)."
                )
