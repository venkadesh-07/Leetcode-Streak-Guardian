
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    email = db.Column(
        db.String(254),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )

    leetcode_username = db.Column(db.String(50), nullable=True)
    reminder_email = db.Column(db.String(254), nullable=True)
    last_activity_check_at = db.Column(
        db.Integer,
        nullable=True,
    )
    current_streak = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    today_submissions = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )
    is_active_today = db.Column(
        db.Boolean,
        nullable=True,
        default=None,
    )
    last_checked_date_utc = db.Column(
        db.String(10),
        nullable=True,
    )
    last_reminder_sent_date_utc = db.Column(
        db.String(10),
        nullable=True,
    )
    last_reminder_sent_at = db.Column(
        db.Integer,
        nullable=True,
    )
    reminder_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    notify_email = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    notify_desktop = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )
    notify_discord = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    discord_webhook_url = db.Column(
        db.String(255),
        nullable=True,
    )
    notify_telegram = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    telegram_chat_id = db.Column(
        db.String(64),
        nullable=True,
    )
    api_token = db.Column(
        db.String(64),
        unique=True,
        nullable=True,
        index=True,
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_or_create_api_token(self):
        import secrets
        if not self.api_token:
            self.api_token = secrets.token_hex(24)
        return self.api_token
