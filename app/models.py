
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
    telegram_pin = db.Column(
        db.String(6),
        nullable=True,
        index=True,
    )
    telegram_pin_expires_at = db.Column(
        db.BigInteger,
        nullable=True,
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

    def get_or_create_telegram_pin(self, force_refresh=False):
        """
        Generate or return an active 6-digit numeric pairing PIN for Telegram linking.
        Valid for 15 minutes (900 seconds).
        """
        import time
        import secrets
        now = int(time.time())

        if (
            not force_refresh
            and self.telegram_pin
            and self.telegram_pin_expires_at
            and self.telegram_pin_expires_at > now
        ):
            return self.telegram_pin

        # Generate a collision-resistant 6-digit PIN
        for _ in range(10):
            candidate = f"{secrets.randbelow(900000) + 100000}"
            conflict = User.query.filter(
                User.telegram_pin == candidate,
                User.id != self.id,
                User.telegram_pin_expires_at > now,
            ).first()
            if not conflict:
                self.telegram_pin = candidate
                self.telegram_pin_expires_at = now + 900
                db.session.commit()
                return self.telegram_pin

        self.telegram_pin = f"{secrets.randbelow(900000) + 100000}"
        self.telegram_pin_expires_at = now + 900
        db.session.commit()
        return self.telegram_pin

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


