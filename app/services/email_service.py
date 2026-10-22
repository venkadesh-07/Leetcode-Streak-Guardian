"""
Secure email delivery service for LeetCode Streak Guardian.
Supports SMTP delivery with TLS or safe local simulation mode when SMTP credentials are unset.
Defends strictly against email header injection.
"""

import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging

logger = logging.getLogger(__name__)


import socket

class IPv4SMTP(smtplib.SMTP):
    """SMTP subclass that prioritizes IPv4 to avoid [Errno 101] Network is unreachable on broken cloud IPv6 stacks."""
    def _get_socket(self, host, port, timeout):
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
            if infos:
                err = None
                for res in infos:
                    af, socktype, proto, canonname, sa = res
                    s = None
                    try:
                        s = socket.socket(af, socktype, proto)
                        s.settimeout(timeout)
                        s.connect(sa)
                        return s
                    except OSError as e:
                        err = e
                        if s:
                            s.close()
                if err:
                    raise err
        except Exception:
            pass
        return socket.create_connection((host, port), timeout)


def validate_header_value(value):
    """
    Prevent email header injection by rejecting carriage return and newline characters.
    """
    if not isinstance(value, str):
        raise ValueError("Header value must be a string.")
    if "\r" in value or "\n" in value:
        raise ValueError("Header injection attempt detected: newlines are not permitted.")
    return value.strip()


def send_email(to_email, subject, body_text, body_html=None):
    """
    Send an email via configured SMTP server, or simulate delivery if unconfigured.

    Returns:
        dict: {"success": bool, "mode": "smtp"|"simulated", "recipient": str}
    """
    to_email = validate_header_value(to_email)
    subject = validate_header_value(subject)

    smtp_host = os.environ.get("SMTP_HOST")
    sender_email = validate_header_value(
        os.environ.get("REMINDER_SENDER_EMAIL", "no-reply@streak-guardian.local")
    )

    # Safe simulation guard: Never dispatch real emails during automated tests,
    # when testing dummy domains (*@example.com), or when SMTP_HOST is unset.
    from flask import current_app, has_app_context
    is_testing = (has_app_context() and current_app.config.get("TESTING")) or os.environ.get("FLASK_ENV") == "testing"
    is_dummy_domain = to_email.lower().endswith("@example.com") or to_email.lower().endswith(".test") or to_email.lower().endswith(".local")

    if is_testing or is_dummy_domain or not smtp_host:
        logger.info(
            f"[EMAIL SIMULATION] Sent to: {to_email} | Subject: '{subject}'"
        )
        return {
            "success": True,
            "mode": "simulated",
            "recipient": to_email,
            "subject": subject,
        }

    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with IPv4SMTP(smtp_host, smtp_port, timeout=10) as server:
            if smtp_use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)

        return {
            "success": True,
            "mode": "smtp",
            "recipient": to_email,
            "subject": subject,
        }
    except Exception as exc:
        logger.error(f"Failed to send email to {to_email}: {exc}")
        return {
            "success": False,
            "mode": "error",
            "error": str(exc),
            "recipient": to_email,
        }


def send_streak_reminder(user, submissions_today, current_streak, date_utc):
    """
    Send a streak risk notification email to the user's configured reminder email.
    """
    recipient = user.reminder_email
    if not recipient:
        raise ValueError("User does not have a configured reminder email.")

    base_url = os.environ.get("APP_BASE_URL", "http://127.0.0.1:5001").rstrip("/")

    subject = f"🔥 Streak Alert: Keep your {current_streak}-day LeetCode streak alive!"

    body_text = f"""Hello,

This is your LeetCode Streak Guardian alert for {date_utc} (UTC).

You currently have a {current_streak}-day streak, but no submissions have been recorded yet today for your account ({user.leetcode_username}).

Solve at least one problem before 23:59 UTC to protect your streak!

Your Dashboard: {base_url}/dashboard

Stay consistent. Keep coding!
LeetCode Streak Guardian
"""

    body_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; margin: 0; }}
        .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 24px; max-width: 540px; margin: 20px auto; }}
        h1 {{ color: #f59e0b; font-size: 24px; margin-top: 0; }}
        .badge {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 8px 12px; border-radius: 6px; font-weight: bold; display: inline-block; margin-bottom: 16px; }}
        .cta {{ display: inline-block; background: #f59e0b; color: #0f172a; font-weight: bold; padding: 12px 20px; border-radius: 6px; text-decoration: none; margin-top: 16px; }}
        footer {{ color: #64748b; font-size: 12px; margin-top: 24px; text-align: center; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>LeetCode Streak Guardian</h1>
        <div class="badge">⚠️ Streak At Risk for {date_utc} (UTC)</div>
        <p>Hello,</p>
        <p>You currently hold a <strong>{current_streak}-day coding streak</strong> on LeetCode (<strong>{user.leetcode_username}</strong>), but no submissions have been detected yet today.</p>
        <p>Make sure to solve and submit at least one problem before the daily reset at <strong>23:59 UTC</strong> to keep your streak intact!</p>
        <a href="https://leetcode.com/problemset/" class="cta">Solve a Problem Now</a>
        <p style="margin-top: 12px;"><a href="{base_url}/dashboard" style="color: #94a3b8; font-size: 13px;">View Your Dashboard</a></p>
        <footer>Stay consistent. Keep coding! &bull; LeetCode Streak Guardian</footer>
    </div>
</body>
</html>
"""

    return send_email(recipient, subject, body_text, body_html)
