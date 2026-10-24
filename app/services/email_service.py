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


import requests


def send_via_brevo(api_key, sender_email, to_email, subject, body_text, body_html=None, sender_name=None):
    """
    Send an email via Brevo's HTTPS REST API (Port 443).
    Bypasses cloud provider SMTP firewall blocks (e.g. Render Free Tier) and works for any recipient.
    """
    sender_name = sender_name or os.environ.get("REMINDER_SENDER_NAME", "LeetCode Streak Guardian")
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body_text,
    }
    if body_html:
        payload["htmlContent"] = body_html

    headers = {
        "api-key": api_key.strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=12,
        )
        if resp.status_code in (200, 201, 202):
            data = resp.json() if resp.text else {}
            message_id = data.get("messageId", "ok")
            logger.info(f"[BREVO EMAIL SUCCESS] Sent to {to_email} | Subject: '{subject}' | MessageID: {message_id}")
            return {
                "success": True,
                "mode": "brevo",
                "recipient": to_email,
                "subject": subject,
                "message_id": message_id,
            }
        else:
            err_msg = f"Brevo API error ({resp.status_code}): {resp.text}"
            logger.error(f"[BREVO EMAIL ERROR] {err_msg}")
            return {
                "success": False,
                "mode": "error",
                "error": err_msg,
                "recipient": to_email,
            }
    except Exception as exc:
        logger.error(f"[BREVO EXCEPTION] Failed to send email to {to_email}: {exc}")
        return {
            "success": False,
            "mode": "error",
            "error": str(exc),
            "recipient": to_email,
        }


def send_email(to_email, subject, body_text, body_html=None):
    """
    Send an email via Brevo HTTPS API, or configured SMTP server, or simulate delivery if unconfigured.

    Returns:
        dict: {"success": bool, "mode": "brevo"|"smtp"|"simulated", "recipient": str}
    """
    to_email = validate_header_value(to_email)
    subject = validate_header_value(subject)

    brevo_api_key = os.environ.get("BREVO_API_KEY", "").strip()
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    sender_email = validate_header_value(
        os.environ.get("REMINDER_SENDER_EMAIL", "no-reply@streak-guardian.local")
    )

    # Safe simulation guard: Never dispatch real emails during automated tests,
    # when testing dummy domains (*@example.com), or when no email provider is configured.
    from flask import current_app, has_app_context
    is_testing = (has_app_context() and current_app.config.get("TESTING")) or os.environ.get("FLASK_ENV") == "testing"
    is_dummy_domain = to_email.lower().endswith("@example.com") or to_email.lower().endswith(".test") or to_email.lower().endswith(".local")

    has_provider = bool(brevo_api_key or smtp_host)

    if is_testing or is_dummy_domain or not has_provider:
        logger.info(
            f"[EMAIL SIMULATION] Sent to: {to_email} | Subject: '{subject}'"
        )
        return {
            "success": True,
            "mode": "simulated",
            "recipient": to_email,
            "subject": subject,
        }

    # 1. Brevo HTTPS API (recommended for Render free tier - bypasses SMTP port blocking)
    if brevo_api_key:
        return send_via_brevo(brevo_api_key, sender_email, to_email, subject, body_text, body_html)

    # 2. SMTP fallback (used by GitHub Actions & local development)
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


from datetime import datetime, timezone


from app.services.time_utils import (
    get_time_remaining_until_reset,
    format_ist_date,
    get_now_ist,
)


def send_streak_reminder(user, submissions_today, current_streak, date_utc):
    """
    Send a streak risk notification email to the user's configured reminder email
    with dynamic time-remaining urgency in Indian Standard Time (IST).
    """
    recipient = user.reminder_email
    if not recipient:
        raise ValueError("User does not have a configured reminder email.")

    base_url = os.environ.get("APP_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
    time_info = get_time_remaining_until_reset()
    date_display_ist = time_info.get("date_ist_str") or format_ist_date()

    subject = f"{time_info['subject_tag']} Keep your {current_streak}-day LeetCode streak alive!"

    sub_count = int(submissions_today) if str(submissions_today).isdigit() else 0
    if sub_count == 0:
        email_status_text = f"You currently hold a {current_streak}-day streak, but no submissions have been recorded yet today for your account ({user.leetcode_username})."
        email_action_text = "Solve at least one problem before 05:30 AM IST to protect your streak!"
        html_p_status = f"You currently hold a <strong>{current_streak}-day coding streak</strong> on LeetCode (<strong>{user.leetcode_username}</strong>), but no submissions have been detected yet today ({date_display_ist} IST)."
        html_p_action = "Solve and submit at least one problem before the daily reset at <strong>05:30 AM IST</strong> to keep your streak intact!"
    else:
        email_status_text = f"You currently hold a {current_streak}-day streak, and you have completed {sub_count}/3 submission(s) today for your account ({user.leetcode_username})."
        email_action_text = f"Keep your momentum going! Complete at least 3 problems today ({sub_count}/3 so far) before the 05:30 AM IST reset!"
        html_p_status = f"You currently hold a <strong>{current_streak}-day coding streak</strong> on LeetCode (<strong>{user.leetcode_username}</strong>). You have logged <strong>{sub_count}/3</strong> submission(s) today ({date_display_ist} IST)."
        html_p_action = f"Daily Goal: Complete at least 3 problems today (currently <strong>{sub_count}/3</strong>) before the reset at <strong>05:30 AM IST</strong>!"

    body_text = f"""Hello,

This is your LeetCode Streak Guardian alert for {date_display_ist} (IST).

⏰ TIME REMAINING: Only {time_info['time_display']} left before the daily reset at 05:30 AM IST!

{email_status_text}

{email_action_text}

Solve Now: https://leetcode.com/problemset/
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
        .badge {{ {time_info['badge_style']} padding: 8px 14px; border-radius: 6px; font-weight: bold; display: inline-block; margin-bottom: 16px; font-size: 14px; }}
        .urgency-box {{ background: rgba(15, 23, 42, 0.7); border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; margin: 16px 0; }}
        .countdown {{ font-size: 18px; font-weight: bold; color: #f59e0b; }}
        .cta {{ display: inline-block; background: #f59e0b; color: #0f172a; font-weight: bold; padding: 12px 20px; border-radius: 6px; text-decoration: none; margin-top: 16px; }}
        footer {{ color: #64748b; font-size: 12px; margin-top: 24px; text-align: center; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>LeetCode Streak Guardian</h1>
        <div class="badge">{time_info['urgency_badge']}</div>

        <div class="urgency-box">
            ⏰ <strong>Time Remaining:</strong> <span class="countdown">{time_info['time_display']}</span> left before reset at <strong>05:30 AM IST</strong>!
        </div>

        <p>Hello,</p>
        <p>{html_p_status}</p>
        <p>{html_p_action}</p>
        <a href="https://leetcode.com/problemset/" class="cta">Solve a Problem Now</a>
        <p style="margin-top: 14px;"><a href="{base_url}/dashboard" style="color: #94a3b8; font-size: 13px;">View Your Dashboard</a></p>
        <footer>Stay consistent. Keep coding! &bull; LeetCode Streak Guardian (IST)</footer>
    </div>
</body>
</html>
"""

    return send_email(recipient, subject, body_text, body_html)
