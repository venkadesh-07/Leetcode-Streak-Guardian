
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

    notify_whatsapp = BooleanField(
        "Enable WhatsApp Instant Alerts"
    )

    whatsapp_phone = StringField(
        "WhatsApp Phone Number (with Country Code)",
        validators=[
            Optional(),
            Length(max=32),
        ],
    )

    whatsapp_apikey = StringField(
        "CallMeBot WhatsApp API Key",
        validators=[
            Optional(),
            Length(max=64),
        ],
    )

    submit = SubmitField("Save settings")

    def validate_telegram_chat_id(self, field):
        cid = (field.data or "").strip()
        if cid:
            from app.services.telegram_service import validate_telegram_chat_id
            if not validate_telegram_chat_id(cid):
                raise ValidationError(
                    "Invalid Telegram Chat ID. Chat ID must be numeric (e.g. 123456789)."
                )

    def validate_whatsapp_phone(self, field):
        from app.services.whatsapp_service import sanitize_phone_number
        raw_val = (field.data or "").strip()
        if raw_val:
            cleaned = sanitize_phone_number(raw_val)
            digits = re.sub(r"\D", "", cleaned)
            if len(digits) < 7 or len(digits) > 16:
                raise ValidationError(
                    "Please enter a valid international phone number with country code (e.g. +919876543210)."
                )

    def validate_notify_whatsapp(self, field):
        if field.data:
            phone = (self.whatsapp_phone.data or "").strip()
            apikey = (self.whatsapp_apikey.data or "").strip()
            if not phone:
                raise ValidationError(
                    "Please provide your WhatsApp phone number to enable WhatsApp alerts."
                )
            if not apikey:
                raise ValidationError(
                    "Please provide your CallMeBot API Key to enable WhatsApp alerts."
                )
