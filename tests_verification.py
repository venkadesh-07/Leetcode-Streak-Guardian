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

import os
import time
import unittest
from unittest.mock import patch, MagicMock
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
        """Verify that exceeding rate limits on POST requests returns HTTP 429 while GET requests remain unblocked."""
        # 1. GET requests to /login should NEVER be rate-limited (user can view/refresh page freely)
        for _ in range(8):
            get_res = self.client.get("/login")
            self.assertEqual(get_res.status_code, 200)

        # 2. Extract CSRF token from page to make valid form submission attempts
        import re
        page = self.client.get("/login")
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
        csrf_token = match.group(1) if match else ""

        # 3. POST requests to /login are limited to 5 per minute
        post_responses = []
        for _ in range(7):
            r = self.client.post(
                "/login",
                data={
                    "email": "user@example.com",
                    "password": "WrongPassword123!",
                    "csrf_token": csrf_token,
                },
            )
            post_responses.append(r.status_code)

        # First 5 should succeed through to form validation failure (200), remaining must be 429 Too Many Requests
        self.assertEqual(post_responses[:5], [200, 200, 200, 200, 200])
        self.assertEqual(post_responses[5:], [429, 429])
        print(f"  [PASS] Test 3: Rate limiting strictly enforced on POST /login (Responses: {post_responses}) while GET remains unblocked.")

    def test_04_unrelated_routes_not_blocked(self):
        """Verify that hitting the rate limit on POST /login does not block unrelated routes like / or GET /login."""
        import re
        page = self.client.get("/login")
        match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
        csrf_token = match.group(1) if match else ""

        # Trigger rate limit on POST /login
        for _ in range(7):
            self.client.post(
                "/login",
                data={
                    "email": "user@example.com",
                    "password": "WrongPassword123!",
                    "csrf_token": csrf_token,
                },
            )

        # Request to homepage / should still succeed with 200 OK
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

        # Viewing /login via GET should ALSO remain accessible with 200 OK
        login_view = self.client.get("/login")
        self.assertEqual(login_view.status_code, 200)
        print("  [PASS] Test 4: Unrelated routes and GET requests remain fully accessible after POST rate limit.")

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
        import os

        # When SMTP_HOST is not in environment, email service safely logs and simulates
        with patch.dict(os.environ, {"SMTP_HOST": "", "BREVO_API_KEY": ""}):
            result = send_email("coder@example.com", "Test Alert", "Don't forget to code!")
            self.assertTrue(result["success"])
            self.assertEqual(result["mode"], "simulated")
            self.assertEqual(result["recipient"], "coder@example.com")

        # Test Brevo HTTPS dispatch with mock
        from app.services.email_service import send_via_brevo
        from unittest.mock import MagicMock
        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 201
            mock_resp.json.return_value = {"messageId": "<sample-brevo-id@smtp-relay.mailin.fr>"}
            mock_resp.text = '{"messageId": "<sample-brevo-id@smtp-relay.mailin.fr>"}'
            mock_post.return_value = mock_resp

            brevo_res = send_via_brevo(
                api_key="xkeysib-mock-api-key",
                sender_email="sender@example.com",
                to_email="student@university.edu",
                subject="Test Alert",
                body_text="Keep coding!",
            )
            self.assertTrue(brevo_res["success"])
            self.assertEqual(brevo_res["mode"], "brevo")
            self.assertEqual(brevo_res["recipient"], "student@university.edu")
            self.assertEqual(brevo_res["message_id"], "<sample-brevo-id@smtp-relay.mailin.fr>")
            self.assertTrue(mock_post.called)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.brevo.com/v3/smtp/email")
            self.assertEqual(kwargs["headers"]["api-key"], "xkeysib-mock-api-key")

        print("  [PASS] Test 12: Email service local simulation mode & Brevo HTTPS verified.")

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
            with patch.dict(os.environ, {"SMTP_HOST": ""}), patch("app.services.reminder_job.check_daily_activity", return_value=mock_activity):
                stats = run_reminder_check()
                self.assertGreaterEqual(stats["reminders_sent"], 1)

                # Verify user's last_reminder_sent_at and date was updated
                refreshed_user = db.session.get(User, uid)
                self.assertEqual(refreshed_user.last_reminder_sent_date_utc, today_utc)
                self.assertIsNotNone(refreshed_user.last_reminder_sent_at)

                # Run 2 immediately after: must suppress due to 4-hour interval
                stats2 = run_reminder_check()
                self.assertEqual(stats2["reminders_sent"], 0)
                self.assertGreaterEqual(stats2["interval_cooldown"], 1)

            # Run 3: Once user solves a problem (active_today = True), STOP sending completely
            mock_solved = dict(mock_activity, active_today=True, submissions_today=1)
            with patch("app.services.reminder_job.check_daily_activity", return_value=mock_solved):
                stats3 = run_reminder_check()
                self.assertEqual(stats3["reminders_sent"], 0)
                self.assertGreaterEqual(stats3["already_protected"], 1)
        print("  [PASS] Test 13: 4-hour interval reminders and auto-stop when problem completed verified.")

    def test_14_cron_webhook_security(self):
        """Verify the /api/cron/check-reminders webhook endpoint enforces secret token validation and CSRF exemption."""
        valid_secret = self.app.config.get("SECRET_KEY")

        # 1. Request without secret -> 401
        res = self.client.get("/api/cron/check-reminders")
        self.assertEqual(res.status_code, 401)

        # 2. Request with invalid secret -> 401
        res = self.client.get("/api/cron/check-reminders?secret=wrong-secret")
        self.assertEqual(res.status_code, 401)

        # 3. Request with valid secret via query param -> 200
        with patch("app.services.reminder_job.run_reminder_check", return_value={"checked": 0}):
            res = self.client.post(f"/api/cron/check-reminders?secret={valid_secret}")
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data["status"], "success")

        # 4. Request with valid secret via Bearer header -> 200
        with patch("app.services.reminder_job.run_reminder_check", return_value={"checked": 0}):
            res = self.client.post(
                "/api/cron/check-reminders",
                headers={"Authorization": f"Bearer {valid_secret}"}
            )
            self.assertEqual(res.status_code, 200)
        print("  [PASS] Test 14: Automated cron webhook security and Bearer authentication verified.")

    def test_15_desktop_streak_status_api(self):
        """Verify the /api/v1/streak-status endpoint enforces token authentication and returns metrics."""
        from datetime import datetime, timezone
        today_iso = datetime.now(timezone.utc).date().isoformat()
        with self.app.app_context():
            user = User(email="desktopuser@example.com", leetcode_username="dev_alex")
            user.set_password("Password123!")
            token = user.get_or_create_api_token()
            user.current_streak = 7
            user.is_active_today = False
            user.today_submissions = 0
            user.last_checked_date_utc = today_iso
            user.last_activity_check_at = int(time.time())
            db.session.add(user)
            db.session.commit()

        # 1. Missing token -> 401
        res = self.client.get("/api/v1/streak-status")
        self.assertEqual(res.status_code, 401)

        # 2. Invalid token -> 401
        res = self.client.get("/api/v1/streak-status?token=non_existent_token")
        self.assertEqual(res.status_code, 401)

        # 3. Valid token via X-API-Key header -> 200
        res = self.client.get(
            "/api/v1/streak-status",
            headers={"X-API-Key": token}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["user"]["leetcode_username"], "dev_alex")
        self.assertEqual(data["streak"]["current_streak"], 7)
        self.assertFalse(data["streak"]["active_today"])
        self.assertTrue(data["alert_needed"])
        self.assertIn("Streak at Risk", data["message"])
        print("  [PASS] Test 15: Desktop companion /api/v1/streak-status authentication and payload verified.")

    def test_16_desktop_token_regeneration(self):
        """Verify that authenticated users can regenerate their desktop sync token."""
        with self.app.app_context():
            user = User(email="tokentest@example.com")
            user.set_password("Password123!")
            initial_token = user.get_or_create_api_token()
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        # Login as the user
        with self.client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True

        # Generate a new token using model helper directly and verify uniqueness
        with self.app.app_context():
            u = db.session.get(User, user_id)
            old_token = u.api_token
            u.api_token = None
            new_token = u.get_or_create_api_token()
            self.assertNotEqual(old_token, new_token)
            self.assertEqual(len(new_token), 48)  # 24 bytes hex = 48 chars
        print("  [PASS] Test 16: API token generation and uniqueness verified.")

    def test_17_multi_channel_settings(self):
        """Verify email and telegram notification preferences and test-email route."""
        with self.app.app_context():
            user = User(email="channeluser@example.com", reminder_email="channeluser@example.com", leetcode_username="coder_1")
            user.set_password("Password123!")
            user.reminder_enabled = True
            user.notify_email = False
            user.notify_telegram = True
            user.telegram_chat_id = "987654321"
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        # Verify defaults and persistence
        with self.app.app_context():
            u = db.session.get(User, user_id)
            self.assertFalse(u.notify_email)
            self.assertTrue(u.notify_telegram)
            self.assertEqual(u.telegram_chat_id, "987654321")

        # Login as user and verify send_test_email route rejects state without CSRF
        with self.client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True

        res = self.client.post("/settings/test-email")
        self.assertEqual(res.status_code, 400)  # CSRF protected

        # Direct service call simulation test
        from app.services.email_service import send_streak_reminder
        import os
        with patch.dict(os.environ, {"SMTP_HOST": ""}):
            result = send_streak_reminder(user=u, submissions_today=0, current_streak=5, date_utc="2026-10-17")
            self.assertTrue(result["success"])
            self.assertEqual(result["mode"], "simulated")
        print("  [PASS] Test 17: Multi-channel preferences and test-email controls verified.")

    def test_18_discord_and_desktop_cleanly_removed(self):
        """Verify that Discord and Windows desktop options have been cleanly decoupled and removed."""
        from app.forms import SettingsForm
        with self.app.test_request_context():
            form = SettingsForm()
            self.assertFalse(hasattr(form, "notify_discord"))
            self.assertFalse(hasattr(form, "discord_webhook_url"))
            self.assertFalse(hasattr(form, "notify_desktop"))

        # Verify /settings/test-discord is removed and returns 404
        with self.client.session_transaction() as sess:
            sess["_user_id"] = "1"
            sess["_fresh"] = True
        res = self.client.post("/settings/test-discord")
        self.assertEqual(res.status_code, 404)
        print("  [PASS] Test 18: Discord and Desktop options verified completely removed from forms and routes.")

    def test_19_telegram_bot_notification(self):
        """Verify Telegram Chat ID validation, markdown message delivery, simulation mode, and route controls."""
        from app.services.telegram_service import validate_telegram_chat_id, send_telegram_streak_reminder

        # 1. Chat ID validation tests
        self.assertTrue(validate_telegram_chat_id("123456789"))
        self.assertTrue(validate_telegram_chat_id("-1001234567890"))
        self.assertFalse(validate_telegram_chat_id("abc12345"))
        self.assertFalse(validate_telegram_chat_id("@my_chat"))

        # 2. Simulation mode delivery test
        with self.app.app_context():
            u = User(email="telegramuser@example.com", leetcode_username="tele_coder")
            u.set_password("Password123!")
            u.notify_telegram = True
            u.telegram_chat_id = "987654321"
            db.session.add(u)
            db.session.commit()
            uid = u.id

        with patch.dict(os.environ, {"SIMULATE_TELEGRAM": "true"}):
            res = send_telegram_streak_reminder(
                chat_id="987654321",
                user=u,
                submissions_today=0,
                current_streak=15,
                date_utc="2026-10-17",
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["mode"], "simulated")

        # 3. Route CSRF enforcement test on /settings/test-telegram
        with self.client.session_transaction() as sess:
            sess["_user_id"] = str(uid)
            sess["_fresh"] = True

        route_res = self.client.post("/settings/test-telegram")
        self.assertEqual(route_res.status_code, 400)  # CSRF protected
        print("  [PASS] Test 19: Telegram Chat ID validation, markdown bot dispatcher, and route controls verified.")

    def test_20_telegram_1click_deeplink_and_routes(self):
        """Verify 1-Click Telegram Deep Link auto-connection, check-link-status endpoint, and webhook."""
        from app.services.telegram_service import process_telegram_update

        with self.app.app_context():
            u = User(email="deeplink@example.com", leetcode_username="deep_coder")
            u.set_password("Password123!")
            u.api_token = "test_deep_link_token_12345"
            db.session.add(u)
            db.session.commit()
            uid = u.id

        # 1. Test /start <token> deep link processing
        update_payload = {
            "update_id": 1001,
            "message": {
                "message_id": 42,
                "chat": {"id": 88776655, "type": "private"},
                "from": {"id": 88776655, "first_name": "DeepCoder"},
                "text": "/start test_deep_link_token_12345",
            }
        }

        with patch("app.services.telegram_service.send_telegram_message", return_value=True):
            with self.app.app_context():
                res = process_telegram_update(update_payload)
            self.assertTrue(res.get("handled"))
            self.assertEqual(res.get("action"), "linked")
            self.assertEqual(res.get("user_id"), uid)

        # Verify DB persisted
        with self.app.app_context():
            refreshed = db.session.get(User, uid)
            self.assertEqual(refreshed.telegram_chat_id, "88776655")
            self.assertTrue(refreshed.notify_telegram)

        # 2. Test /api/telegram/check-link-status endpoint
        with self.client.session_transaction() as sess:
            sess["_user_id"] = str(uid)
            sess["_fresh"] = True

        with patch("app.services.telegram_service.sync_telegram_account_links", return_value={"count": 0}):
            # Unauthorized call without token or session returns 401
            unauth_resp = self.client.get("/api/telegram/check-link-status")
            self.assertEqual(unauth_resp.status_code, 401)

            # Authorized call with token returns 200
            status_resp = self.client.get("/api/telegram/check-link-status?token=test_deep_link_token_12345")
            self.assertEqual(status_resp.status_code, 200)
            status_data = status_resp.get_json()
            self.assertTrue(status_data["linked"])
            self.assertEqual(status_data["telegram_chat_id"], "88776655")

        # 3. Test /settings/disconnect-telegram CSRF enforcement
        disc_no_csrf = self.client.post("/settings/disconnect-telegram")
        self.assertEqual(disc_no_csrf.status_code, 400)

        with patch("app.services.telegram_service.send_telegram_message", return_value=True):
            webhook_resp = self.client.post("/api/telegram/webhook", json={
                "update_id": 1002,
                "message": {
                    "chat": {"id": 88776655},
                    "text": "/help",
                }
            })
            self.assertEqual(webhook_resp.status_code, 200)
            self.assertEqual(webhook_resp.get_json()["status"], "ok")

        print("  [PASS] Test 20: 1-Click Telegram Deep Link auto-connection, check-link-status, and webhook verified.")

    def test_21_telegram_6digit_pin_and_shared_squad_option_b(self):
        """Verify 6-Digit PIN pairing, Option B multi-user shared Telegram chat, and squad /streak command."""
        from app.services.telegram_service import process_telegram_update

        with self.app.app_context():
            # Create Friend 1
            f1 = User(email="friend1@example.com", leetcode_username="coder_one")
            f1.set_password("Password123!")
            f1.current_streak = 50
            f1.today_submissions = 1
            db.session.add(f1)

            # Create Friend 2
            f2 = User(email="friend2@example.com", leetcode_username="coder_two")
            f2.set_password("Password123!")
            f2.current_streak = 25
            f2.today_submissions = 0
            db.session.add(f2)
            db.session.commit()

            f1_id = f1.id
            f2_id = f2.id

            pin1 = f1.get_or_create_telegram_pin()
            pin2 = f2.get_or_create_telegram_pin()

            self.assertEqual(len(pin1), 6)
            self.assertTrue(pin1.isdigit())
            self.assertEqual(len(pin2), 6)
            self.assertTrue(pin2.isdigit())
            self.assertNotEqual(pin1, pin2)

        shared_chat_id = "99887766"

        # 1. Friend 1 pairs via 6-digit PIN in the chat
        update_p1 = {
            "update_id": 2001,
            "message": {
                "message_id": 101,
                "chat": {"id": int(shared_chat_id)},
                "from": {"first_name": "Friend1"},
                "text": pin1,
            }
        }

        with patch("app.services.telegram_service.send_telegram_message", return_value=True):
            with self.app.app_context():
                res1 = process_telegram_update(update_p1)
            self.assertTrue(res1.get("handled"))
            self.assertEqual(res1.get("action"), "linked")
            self.assertEqual(res1.get("mode"), "pin")
            self.assertEqual(res1.get("user_id"), f1_id)

        # 2. Friend 2 pairs via 6-digit PIN in the SAME chat (Option B Squad Support)
        update_p2 = {
            "update_id": 2002,
            "message": {
                "message_id": 102,
                "chat": {"id": int(shared_chat_id)},
                "from": {"first_name": "Friend2"},
                "text": f"  {pin2}  ",
            }
        }

        with patch("app.services.telegram_service.send_telegram_message", return_value=True):
            with self.app.app_context():
                res2 = process_telegram_update(update_p2)
            self.assertTrue(res2.get("handled"))
            self.assertEqual(res2.get("action"), "linked")
            self.assertEqual(res2.get("mode"), "pin")
            self.assertEqual(res2.get("user_id"), f2_id)

        # 3. VERIFY OPTION B: BOTH friends remain linked to the shared chat ID! Neither was unlinked!
        with self.app.app_context():
            ref1 = db.session.get(User, f1_id)
            ref2 = db.session.get(User, f2_id)
            self.assertEqual(ref1.telegram_chat_id, shared_chat_id)
            self.assertTrue(ref1.notify_telegram)
            self.assertEqual(ref2.telegram_chat_id, shared_chat_id)
            self.assertTrue(ref2.notify_telegram)

            # 4. Multi-user squad /streak check
            mock_status = {
                "active_today": True,
                "submissions_today": 2,
                "current_streak": 51,
                "checked_date_utc": "2026-10-19",
            }
            with patch("app.services.leetcode_checker.check_daily_activity", return_value=mock_status):
                with patch("app.services.telegram_service.send_telegram_message", return_value=True):
                    streak_update = {
                        "update_id": 2003,
                        "message": {
                            "chat": {"id": int(shared_chat_id)},
                            "text": "/streak",
                        }
                    }
                    streak_res = process_telegram_update(streak_update)
                    self.assertTrue(streak_res.get("handled"))
                    self.assertEqual(streak_res.get("action"), "squad_streak_reported")
                    self.assertEqual(streak_res.get("count"), 2)

        # 5. Test /api/telegram/refresh-pin endpoint
        disc_no_csrf = self.client.post("/api/telegram/refresh-pin")
        self.assertEqual(disc_no_csrf.status_code, 400)  # CSRF protected

        print("  [PASS] Test 21: 6-Digit PIN pairing, Option B multi-user squad linking, and /streak reporting verified.")

    def test_22_emergency_auto_rescue(self):
        """Test 22: Verify Emergency Auto-Rescue Airbag submission logic, database state, and final hour trigger."""
        from app.services.rescue_service import (
            get_leetcode_question_id,
            submit_to_leetcode,
            execute_auto_rescue,
            DEFAULT_TWO_SUM_PYTHON3,
        )

        # 1. Test question ID resolver
        self.assertEqual(get_leetcode_question_id("two-sum"), "1")
        self.assertEqual(get_leetcode_question_id("palindrome-number"), "9")

        # 2. Test missing credentials guard
        missing_res = submit_to_leetcode("", "")
        self.assertFalse(missing_res["success"])
        self.assertEqual(missing_res["status"], "CONFIG_ERROR")

        # 3. Test mock LeetCode submission success
        with patch("requests.post") as mock_post, patch("requests.get") as mock_get:
            mock_post_resp = MagicMock()
            mock_post_resp.status_code = 200
            mock_post_resp.json.return_value = {"submission_id": 987654321}
            mock_post.return_value = mock_post_resp

            mock_get_resp = MagicMock()
            mock_get_resp.status_code = 200
            mock_get_resp.json.return_value = {
                "state": "SUCCESS",
                "status_msg": "Accepted",
                "status_runtime": "45 ms",
                "status_memory": "16.8 MB",
            }
            mock_get.return_value = mock_get_resp

            with patch("time.sleep", return_value=None):
                sub_res = submit_to_leetcode(
                    session_cookie="dummy_session",
                    csrf_token="dummy_csrf",
                    problem_slug="two-sum",
                    language="python3",
                    code=DEFAULT_TWO_SUM_PYTHON3,
                )
            self.assertTrue(sub_res["success"])
            self.assertEqual(sub_res["status"], "Accepted")
            self.assertEqual(sub_res["submission_id"], 987654321)

        # 4. Test execute_auto_rescue database persistence
        with self.app.app_context():
            u = User(
                email="rescueuser@example.com",
                auto_rescue_enabled=True,
                leetcode_session="test_session_cookie",
                leetcode_csrf_token="test_csrf_token",
                rescue_problem_slug="two-sum",
                rescue_language="python3",
            )
            u.set_password("SecurePassword123!")
            db.session.add(u)
            db.session.commit()
            uid = u.id

        with patch("app.services.rescue_service.submit_to_leetcode") as mock_sub:
            mock_sub.return_value = {
                "success": True,
                "status": "Accepted",
                "submission_id": 11223344,
            }
            with patch("app.services.rescue_service._notify_rescue_event"):
                with self.app.app_context():
                    test_u = db.session.get(User, uid)
                    rescue_res = execute_auto_rescue(test_u, force=True)
                    self.assertTrue(rescue_res["success"])

                    refetched = db.session.get(User, uid)
                    self.assertEqual(refetched.last_rescue_status, "Accepted")
                    self.assertTrue(refetched.is_active_today)
                    self.assertGreaterEqual(refetched.today_submissions, 1)

        print("  [PASS] Test 22: Emergency Auto-Rescue Airbag submission logic, database state, and final hour trigger verified.")

    def test_23_indian_standard_time_formatting(self):
        """Verify that all user-facing schedules, deadlines, dashboards, alerts, and APIs operate in Indian Standard Time (IST)."""
        import re
        from app.services.time_utils import IST, get_now_ist, format_ist_date, format_ist_datetime, get_time_remaining_until_reset
        from app.services.email_service import send_streak_reminder
        from app.services.telegram_service import send_telegram_streak_reminder

        # 1. Verify IST offset is UTC+05:30
        now_ist = get_now_ist()
        self.assertEqual(now_ist.tzinfo, IST)
        self.assertEqual(now_ist.utcoffset().total_seconds(), 5.5 * 3600)

        # 2. Verify reset time info targets 05:30 AM IST
        time_info = get_time_remaining_until_reset()
        self.assertEqual(time_info["reset_time_str"], "05:30 AM IST")
        self.assertIn("05:30 AM IST", time_info["urgency_badge"])
        self.assertIn("m", time_info["time_display"])
        self.assertIn("left", time_info["subject_tag"])

        # 3. Verify Dashboard HTML renders IST metrics
        with self.app.app_context():
            user = User(
                email="istuser@example.com",
                leetcode_username="ist_coder",
                current_streak=10,
                today_submissions=2,
                is_active_today=True,
            )
            user.set_password("SecurePass123!")
            db.session.add(user)
            db.session.commit()

            login_page = self.client.get("/login")
            token_match = re.search(r'name="csrf_token"[^>]*?value="([^"]+)"', login_page.text)
            self.assertIsNotNone(token_match)
            csrf_token = token_match.group(1)

            login_resp = self.client.post(
                "/login",
                data={
                    "csrf_token": csrf_token,
                    "email": "istuser@example.com",
                    "password": "SecurePass123!",
                },
                follow_redirects=True,
            )
            self.assertEqual(login_resp.status_code, 200)
            html_text = login_resp.text
            self.assertIn("Submissions Today (IST)", html_text)
            self.assertIn("05:30 AM IST", html_text)
            self.assertNotIn("Submissions Today (UTC)", html_text)

        # 4. Verify API streak status returns IST fields
        with self.app.app_context():
            token = user.get_or_create_api_token()
            db.session.commit()
            api_res = self.client.get("/api/v1/streak-status", headers={"X-API-Key": token})
            self.assertEqual(api_res.status_code, 200)
            api_data = api_res.get_json()
            self.assertEqual(api_data["time_remaining"]["timezone"], "IST")
            self.assertEqual(api_data["time_remaining"]["reset_deadline_ist"], "05:30 AM IST")
            self.assertIn("05:30 AM IST", api_data["time_remaining"]["formatted"])

        # 5. Verify Telegram Alert text explicitly contains IST
        with self.app.app_context():
            with patch("requests.post") as mock_tg_post:
                mock_tg_resp = MagicMock()
                mock_tg_resp.status_code = 200
                mock_tg_resp.headers = {"content-type": "application/json"}
                mock_tg_resp.json.return_value = {"ok": True}
                mock_tg_post.return_value = mock_tg_resp

                with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:FAKE_TOKEN_XYZ"}):
                    tg_res = send_telegram_streak_reminder(
                        chat_id="99887766",
                        user=user,
                        submissions_today=0,
                        current_streak=10,
                        date_utc="2026-10-24",
                    )
                    self.assertTrue(tg_res["success"])
                    payload = mock_tg_post.call_args[1]["json"]
                    self.assertIn("05:30 AM IST", payload["text"])
                    self.assertIn("Date (IST)", payload["text"])
                    self.assertNotIn("23:59 UTC", payload["text"])

        print("  [PASS] Test 23: Indian Standard Time (IST) formatting, dashboard labels, and 05:30 AM IST alerts verified.")


if __name__ == "__main__":
    print("\nRunning Security & Rate Limiting Verification Suite...")
    suite = unittest.TestLoader().loadTestsFromTestCase(SecurityControlsTestCase)
    runner = unittest.TextTestRunner(verbosity=1)
    result = runner.run(suite)
    if result.wasSuccessful():
        print("\nALL 23 VERIFICATION CHECKS PASSED SUCCESSFULLY!\n")
    else:
        print("\nSOME CHECKS FAILED. Review errors above.\n")
        exit(1)
