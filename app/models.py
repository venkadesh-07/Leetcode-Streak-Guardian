
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

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
