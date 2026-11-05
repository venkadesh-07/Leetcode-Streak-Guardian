
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
    # Ownership verification: True = user has proved they own this LeetCode username.
    # Grandfathered to True for all existing users who already had a username set.
    leetcode_verified = db.Column(db.Boolean, nullable=False, default=False)
    # Bio challenge token: user pastes this into their LeetCode "About Me" to prove ownership.
    verification_token = db.Column(db.String(20), nullable=True)

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
    api_token = db.Column(
        db.String(64),
        unique=True,
        nullable=True,
        index=True,
    )
    auto_rescue_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )
    _leetcode_session = db.Column(
        "leetcode_session",
        db.Text,
        nullable=True,
    )
    _leetcode_csrf_token = db.Column(
        "leetcode_csrf_token",
        db.Text,
        nullable=True,
    )

    @property
    def leetcode_session(self):
        from app.services.crypto_utils import decrypt_cookie
        return decrypt_cookie(self._leetcode_session)

    @leetcode_session.setter
    def leetcode_session(self, val):
        from app.services.crypto_utils import encrypt_cookie
        self._leetcode_session = encrypt_cookie(val)

    @property
    def leetcode_csrf_token(self):
        from app.services.crypto_utils import decrypt_cookie
        return decrypt_cookie(self._leetcode_csrf_token)

    @leetcode_csrf_token.setter
    def leetcode_csrf_token(self, val):
        from app.services.crypto_utils import encrypt_cookie
        self._leetcode_csrf_token = encrypt_cookie(val)

    rescue_problem_slug = db.Column(
        db.String(100),
        nullable=False,
        default="two-sum",
    )
    rescue_language = db.Column(
        db.String(50),
        nullable=False,
        default="python3",
    )
    rescue_code = db.Column(
        db.Text,
        nullable=True,
    )
    last_rescue_date_utc = db.Column(
        db.String(10),
        nullable=True,
    )
    last_rescue_status = db.Column(
        db.String(100),
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

    def get_or_create_verification_token(self, force_refresh=False):
        """
        Return the current LeetCode bio verification token, or generate a fresh one.
        Format: guardian-XXXXXXXX (8 alphanumeric chars).
        Users paste this into their LeetCode profile 'About Me' to prove ownership.
        """
        import secrets
        import string
        if self.verification_token and not force_refresh:
            return self.verification_token
        alphabet = string.ascii_lowercase + string.digits
        token = "guardian-" + "".join(secrets.choice(alphabet) for _ in range(8))
        self.verification_token = token
        return token


    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"
