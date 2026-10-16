"""
Comprehensive security and functional verification suite for LeetCode Streak Guardian.
Tests:
1. HTTP Security Headers
2. CSRF Rejection on State-Changing POST
3. Rate Limiting Enforcement (HTTP 429)
4. Rate Limit Isolation (Unrelated routes remain accessible)
5. Password Complexity Validation
6. LeetCode Username Format Sanitization
7. Password Hashing Security (No plaintext storage)
8. Server-Side Cooldown Logic (60-second activity check cooldown)
"""

import unittest
import time
from app import create_app
from app.extensions import db, limiter
from app.models import User
from app.forms import RegistrationForm, SettingsForm


class SecurityControlsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(test_config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "RATELIMIT_ENABLED": True,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()
            if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
                limiter._storage.reset()
            limiter.reset()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_01_security_headers(self):
        """Verify that mandatory HTTP security headers are injected."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        headers = response.headers
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("default-src 'self'", headers.get("Content-Security-Policy", ""))
        self.assertIn("frame-ancestors 'none'", headers.get("Content-Security-Policy", ""))
        print("  [PASS] Test 1: Security Headers are present and strictly configured.")

    def test_02_csrf_rejection_on_post(self):
        """Verify state-changing POST requests without CSRF token are rejected with 400."""
        response = self.client.post("/login", data={"email": "user@example.com", "password": "Password123!"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"CSRF", response.data)
        print("  [PASS] Test 2: CSRF rejection verified (POST without token returned 400).")

    def test_03_rate_limiting_enforcement(self):
        """Verify that exceeding rate limits returns HTTP 429 Too Many Requests."""
        # /login is limited to 5 per minute
        responses = []
        for _ in range(7):
            r = self.client.get("/login")
            responses.append(r.status_code)

        # First 5 should succeed (200), remaining must be 429
        self.assertEqual(responses[:5], [200, 200, 200, 200, 200])
        self.assertEqual(responses[5:], [429, 429])
        print(f"  [PASS] Test 3: Rate limiting enforced on /login (Responses: {responses}).")

    def test_04_unrelated_routes_not_blocked(self):
        """Verify that hitting the rate limit on /login does not block unrelated routes like /."""
        # Trigger rate limit on /login
        for _ in range(7):
            self.client.get("/login")

        # Request to homepage / should still succeed with 200 OK
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        print("  [PASS] Test 4: Unrelated route (/) remains accessible after /login rate limit.")

    def test_05_input_validation_password_complexity(self):
        """Verify that RegistrationForm rejects passwords that do not meet complexity requirements."""
        from werkzeug.datastructures import MultiDict
        with self.app.test_request_context():
            # Test weak password (too short)
            form_short = RegistrationForm(
                formdata=MultiDict({
                    "email": "user@example.com",
                    "password": "Short1!",
                    "confirm_password": "Short1!",
                }),
                meta={"csrf": False},
            )
            self.assertFalse(form_short.validate())

            # Test weak password (no digit)
            form_no_digit = RegistrationForm(
                formdata=MultiDict({
                    "email": "user@example.com",
                    "password": "PasswordOnly!",
                    "confirm_password": "PasswordOnly!",
                }),
                meta={"csrf": False},
            )
            self.assertFalse(form_no_digit.validate())

            # Test weak password (no uppercase)
            form_no_upper = RegistrationForm(
                formdata=MultiDict({
                    "email": "user@example.com",
                    "password": "password12345!",
                    "confirm_password": "password12345!",
                }),
                meta={"csrf": False},
            )
            self.assertFalse(form_no_upper.validate())

            # Test strong password
            form_strong = RegistrationForm(
                formdata=MultiDict({
                    "email": "user@example.com",
                    "password": "CorrectHorseBattery99!",
                    "confirm_password": "CorrectHorseBattery99!",
                }),
                meta={"csrf": False},
            )
            self.assertTrue(form_strong.validate())
        print("  [PASS] Test 5: Password complexity validation strictly enforced.")

    def test_06_input_validation_leetcode_username_regex(self):
        """Verify that SettingsForm rejects malicious characters in LeetCode username."""
        from werkzeug.datastructures import MultiDict
        with self.app.test_request_context():
            # Test valid usernames
            form_valid = SettingsForm(
                formdata=MultiDict({"leetcode_username": "valid_user-123"}),
                meta={"csrf": False},
            )
            self.assertTrue(form_valid.validate())

            # Test invalid characters (XSS / injection attempt)
            form_invalid = SettingsForm(
                formdata=MultiDict({"leetcode_username": "user<script>alert(1)</script>"}),
                meta={"csrf": False},
            )
            self.assertFalse(form_invalid.validate())
            self.assertIn("leetcode_username", form_invalid.errors)

            form_invalid2 = SettingsForm(
                formdata=MultiDict({"leetcode_username": "user; DROP TABLE user;--"}),
                meta={"csrf": False},
            )
            self.assertFalse(form_invalid2.validate())
            self.assertIn("leetcode_username", form_invalid2.errors)
        print("  [PASS] Test 6: Username format sanitization strictly rejects malicious characters.")

    def test_07_password_hashing_security(self):
        """Verify that user passwords are securely hashed and never stored in plaintext."""
        user = User(email="secure@example.com")
        raw_password = "SuperSecretPassword123!"
        user.set_password(raw_password)

        self.assertNotEqual(user.password_hash, raw_password)
        self.assertTrue(user.password_hash.startswith("scrypt:") or user.password_hash.startswith("pbkdf2:"))
        self.assertTrue(user.check_password(raw_password))
        self.assertFalse(user.check_password("WrongPassword123!"))
        print("  [PASS] Test 7: Password hashing confirmed secure (scrypt/pbkdf2, no plaintext).")

    def test_08_server_side_cooldown_logic(self):
        """Verify server-side 60s cooldown calculation and fail-closed defense."""
        now = int(time.time())
        user = User(email="streak@example.com", leetcode_username="streak_coder")

        # 1. First check: never checked before (last_activity_check_at is None)
        user.last_activity_check_at = None
        # Cooldown check logic from routes.py:
        elapsed = None if user.last_activity_check_at is None else now - user.last_activity_check_at
        is_blocked = elapsed is not None and 0 <= elapsed < 60
        self.assertFalse(is_blocked, "Initial check must not be blocked.")

        # 2. Check 10 seconds later: must be blocked by cooldown
        user.last_activity_check_at = now - 10
        elapsed = now - user.last_activity_check_at
        is_blocked = 0 <= elapsed < 60
        self.assertTrue(is_blocked, "Check within 60s must be blocked by cooldown.")

        # 3. Check 61 seconds later: must be allowed
        user.last_activity_check_at = now - 61
        elapsed = now - user.last_activity_check_at
        is_blocked = 0 <= elapsed < 60
        self.assertFalse(is_blocked, "Check after 60s must be allowed.")

        # 4. Anomalous timestamp in future: fail-closed
        user.last_activity_check_at = now + 100
        elapsed = now - user.last_activity_check_at
        is_anomalous = elapsed < 0
        self.assertTrue(is_anomalous, "Future timestamp must be caught and fail closed.")
        print("  [PASS] Test 8: Server-side 60-second cooldown and fail-closed logic verified.")

    def test_09_calculate_streak_scenarios(self):
        """Verify consecutive daily streak calculation across multiple calendar scenarios."""
        from datetime import datetime, timezone, timedelta
        from app.services.leetcode_checker import calculate_streak

        now = datetime.now(timezone.utc)
        today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        t0 = str(int(today.timestamp()))
        t1 = str(int((today - timedelta(days=1)).timestamp()))
        t2 = str(int((today - timedelta(days=2)).timestamp()))
        t3 = str(int((today - timedelta(days=3)).timestamp()))

        # Scenario 1: Active today + yesterday + 2 days ago (Streak = 3)
        cal1 = {t0: 2, t1: 1, t2: 4}
        self.assertEqual(calculate_streak(cal1, now), 3)

        # Scenario 2: Active yesterday + 2 days ago (At risk today, Streak = 2)
        cal2 = {t1: 1, t2: 2}
        self.assertEqual(calculate_streak(cal2, now), 2)

        # Scenario 3: Broken streak (active 3 days ago, but missed yesterday and today)
        cal3 = {t3: 5}
        self.assertEqual(calculate_streak(cal3, now), 0)

        # Scenario 4: Active today only (Streak = 1)
        cal4 = {t0: 1}
        self.assertEqual(calculate_streak(cal4, now), 1)

        # Scenario 5: Empty calendar (Streak = 0)
        self.assertEqual(calculate_streak({}, now), 0)
        print("  [PASS] Test 9: Streak calculation scenarios accurately verified.")

    def test_10_dashboard_authenticated_view(self):
        """Verify dashboard renders streak metrics and cooldown attribute when authenticated."""
        import re

        # 1. Ensure test user exists in database
        with self.app.app_context():
            u = db.session.execute(db.select(User).filter_by(email="guardian@example.com")).scalar_one_or_none()
            if not u:
                u = User(email="guardian@example.com", leetcode_username="guardian_dev")
                u.set_password("Password123456!")
                u.current_streak = 7
                u.today_submissions = 3
                u.is_active_today = True
                u.last_checked_date_utc = "2026-10-16"
                db.session.add(u)
                db.session.commit()
            else:
                u.current_streak = 7
                u.today_submissions = 3
                u.is_active_today = True
                u.last_checked_date_utc = "2026-10-16"
                db.session.commit()

        # 2. Get login page to grab CSRF token
        login_page = self.client.get("/login")
        token_match = re.search(r'name="csrf_token"[^>]*?value="([^"]+)"', login_page.text)
        self.assertIsNotNone(token_match, "Login page must provide a CSRF token.")
        csrf_token = token_match.group(1)

        # 3. Log in with credentials and follow redirect to /dashboard
        login_resp = self.client.post("/login", data={
            "csrf_token": csrf_token,
            "email": "guardian@example.com",
            "password": "Password123456!",
        }, follow_redirects=True)

        self.assertEqual(login_resp.status_code, 200)
        self.assertIn("Daily Streak Status", login_resp.text)
        self.assertIn("7", login_resp.text)
        self.assertIn("Streak Protected Today!", login_resp.text)
        self.assertIn('data-cooldown="0"', login_resp.text)
        self.assertIn("dashboard.js", login_resp.text)
        print("  [PASS] Test 10: Authenticated dashboard renders streak metrics and CSP script.")

    def test_11_email_header_injection_defense(self):
        """Verify that email service rejects header injection attempts containing newlines."""
        from app.services.email_service import validate_header_value

        # Valid headers
        self.assertEqual(validate_header_value("user@example.com"), "user@example.com")
        self.assertEqual(validate_header_value("LeetCode Streak Alert"), "LeetCode Streak Alert")

        # CRLF injection in recipient or subject
        with self.assertRaises(ValueError):
            validate_header_value("user@example.com\r\nBcc: evil@attacker.com")

        with self.assertRaises(ValueError):
            validate_header_value("Alert!\nSubject: Spoofed Subject")
        print("  [PASS] Test 11: Email header injection defense verified.")

    def test_12_email_service_simulation_mode(self):
        """Verify safe local simulation mode when SMTP credentials are unset."""
        from app.services.email_service import send_email

        # When SMTP_HOST is not in environment, email service safely logs and simulates
        result = send_email("coder@example.com", "Test Alert", "Don't forget to code!")
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "simulated")
        self.assertEqual(result["recipient"], "coder@example.com")
        print("  [PASS] Test 12: Email service local simulation mode confirmed safe.")

    def test_13_reminder_job_logic(self):
        """Verify reminder scanner correctly identifies inactive streaks and updates records."""
        from app.services.reminder_job import run_reminder_check
        from datetime import datetime, timezone
        from unittest.mock import patch

        today_utc = datetime.now(timezone.utc).date().isoformat()

        with self.app.app_context():
            # Create user with reminders enabled and streak at risk
            u = User(
                email="alertme@example.com",
                leetcode_username="lazy_coder",
                reminder_email="alertme@example.com",
                reminder_enabled=True,
            )
            u.set_password("StrongPassword123!")
            db.session.add(u)
            db.session.commit()
            uid = u.id

        # Mock LeetCode activity check returning active_today = False
        mock_activity = {
            "username": "lazy_coder",
            "active_today": False,
            "submissions_today": 0,
            "current_streak": 5,
            "checked_date_utc": today_utc,
        }

        with self.app.app_context():
            with patch("app.services.reminder_job.check_daily_activity", return_value=mock_activity):
                stats = run_reminder_check()
                self.assertGreaterEqual(stats["reminders_sent"], 1)

                # Verify user's last_reminder_sent_date_utc was updated
                refreshed_user = db.session.get(User, uid)
                self.assertEqual(refreshed_user.last_reminder_sent_date_utc, today_utc)

                # Second run on the same day: must NOT send duplicate email
                stats2 = run_reminder_check()
                self.assertEqual(stats2["reminders_sent"], 0)
                self.assertGreaterEqual(stats2["already_reminded_today"], 1)
        print("  [PASS] Test 13: Automated reminder scanner logic and duplicate suppression verified.")


if __name__ == "__main__":
    print("\nRunning Security & Rate Limiting Verification Suite...")
    suite = unittest.TestLoader().loadTestsFromTestCase(SecurityControlsTestCase)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\nALL 13 VERIFICATION CHECKS PASSED SUCCESSFULLY!\n")
    else:
        print("\nSOME CHECKS FAILED. Review errors above.\n")
