
import os
from pathlib import Path
import re
import urllib.parse

from dotenv import load_dotenv
from flask import Flask

from app.extensions import csrf, db, limiter, login_manager

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def normalize_database_url(url):
    """
    Safely normalizes database connection strings for Supabase/PostgreSQL:
    - Replaces postgres:// or postgresql:// with postgresql+psycopg2://
    - Detects and handles passwords enclosed in brackets [...]
    - URL-encodes special characters in passwords (such as @, #, :)
    """
    if not url:
        raise RuntimeError(
            "DATABASE_URL is missing from the environment. "
            "Please configure your Supabase connection string in .env."
        )

    url = url.strip()

    # Convert legacy postgres:// to postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Match connection string components: scheme://user:password@host:port/database
    m = re.match(r"^(postgresql(?:\+[^:]+)?://[^:]+:)(?:\[(.*?)\]|(.*?))@([^@]+)$", url)
    if m:
        prefix = m.group(1)
        pwd = m.group(2) if m.group(2) is not None else m.group(3)
        suffix = m.group(4)
        encoded_pwd = urllib.parse.quote_plus(pwd)
        url = f"{prefix}{encoded_pwd}@{suffix}"

    # Explicitly specify psycopg2 driver if not already specified
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

    return url


def create_app(test_config=None):
    app = Flask(__name__)

    secret_key = os.environ.get("SECRET_KEY", "default-dev-secret-key-for-testing")
    if not secret_key and not test_config:
        raise RuntimeError("SECRET_KEY is missing from the environment.")

    is_production = bool(os.environ.get("RENDER")) or os.environ.get("FLASK_ENV") == "production"

    if test_config:
        app.config.update(
            SECRET_KEY=secret_key,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            SESSION_COOKIE_SECURE=False,
            REMEMBER_COOKIE_HTTPONLY=True,
            REMEMBER_COOKIE_SAMESITE="Lax",
            WTF_CSRF_TIME_LIMIT=3600,
        )
        app.config.update(test_config)
    else:
        raw_db_url = os.environ.get("DATABASE_URL")
        database_url = normalize_database_url(raw_db_url)

        app.config.update(
            SECRET_KEY=secret_key,
            SQLALCHEMY_DATABASE_URI=database_url,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            SESSION_COOKIE_SECURE=is_production,
            REMEMBER_COOKIE_HTTPONLY=True,
            REMEMBER_COOKIE_SAMESITE="Lax",
            REMEMBER_COOKIE_SECURE=is_production,
            WTF_CSRF_TIME_LIMIT=3600,
        )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    login_manager.login_view = "main.login"
    login_manager.session_protection = "strong"

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        return response

    from app.routes import main
    app.register_blueprint(main)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    with app.app_context():
        db.create_all()
        try:
            from sqlalchemy import text
            if "postgresql" in str(db.engine.url):
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS api_token VARCHAR(64);'))
                    conn.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_user_api_token ON "user" (api_token);'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS notify_email BOOLEAN NOT NULL DEFAULT TRUE;'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS notify_desktop BOOLEAN NOT NULL DEFAULT TRUE;'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS notify_discord BOOLEAN NOT NULL DEFAULT FALSE;'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS discord_webhook_url VARCHAR(255);'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS notify_telegram BOOLEAN NOT NULL DEFAULT FALSE;'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(64);'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS telegram_pin VARCHAR(6);'))
                    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_user_telegram_pin ON "user" (telegram_pin);'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS telegram_pin_expires_at BIGINT;'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS notify_whatsapp BOOLEAN NOT NULL DEFAULT FALSE;'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS whatsapp_phone VARCHAR(32);'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS whatsapp_apikey VARCHAR(64);'))
                    conn.commit()
        except Exception:
            pass


    @app.cli.command("check-reminders")
    def check_reminders_command():
        """Check all users with active reminders and dispatch streak alerts."""
        import click
        from app.services.reminder_job import run_reminder_check
        click.echo("Running Streak Guardian Reminder Check...")
        stats = run_reminder_check()
        click.echo(f"Checked Date (UTC): {stats['checked_date_utc']}")
        click.echo(f"Eligible Users: {stats['eligible_users']}")
        click.echo(f"Streaks Protected: {stats['already_protected']}")
        click.echo(f"Reminders Sent: {stats['reminders_sent']}")
        click.echo(f"Interval Cooldown (Skipped): {stats.get('interval_cooldown', 0)}")
        if stats["errors"]:
            click.echo(f"Errors encountered: {len(stats['errors'])}")
            for err in stats["errors"]:
                click.echo(f"  - {err}")

    return app
