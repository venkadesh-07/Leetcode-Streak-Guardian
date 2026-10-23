"""
Automated Emergency Streak Rescue Service for LeetCode Streak Guardian.
Provides automated submission of user-configured backup solutions (default: Two Sum in Python 3)
to protect active streaks before the UTC midnight reset.
"""

from datetime import datetime, timezone
import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

DEFAULT_TWO_SUM_PYTHON3 = """class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
        lookup = {}
        for i, val in enumerate(nums):
            diff = target - val
            if diff in lookup:
                return [lookup[diff], i]
            lookup[val] = i
        return []
"""

KNOWN_QUESTION_IDS = {
    "two-sum": "1",
    "palindrome-number": "9",
    "roman-to-integer": "13",
    "valid-parentheses": "20",
    "merge-two-sorted-lists": "21",
}


def get_leetcode_question_id(title_slug: str) -> str:
    """
    Fetch the backend questionId for a problem slug via LeetCode's public GraphQL API.
    Falls back to known mappings or '1' (Two Sum).
    """
    title_slug = (title_slug or "two-sum").strip().lower()
    if title_slug in KNOWN_QUESTION_IDS:
        return KNOWN_QUESTION_IDS[title_slug]

    graphql_url = "https://leetcode.com/graphql"
    query = """
    query getQuestionDetail($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        questionId
      }
    }
    """
    try:
        resp = requests.post(
            graphql_url,
            json={"query": query, "variables": {"titleSlug": title_slug}},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Content-Type": "application/json",
            },
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            qid = data.get("data", {}).get("question", {}).get("questionId")
            if qid:
                return str(qid)
    except Exception as exc:
        logger.warning(f"Failed to query questionId for '{title_slug}' via GraphQL: {exc}")

    return KNOWN_QUESTION_IDS.get(title_slug, "1")


def sanitize_cookie_val(val: str, key_name: str = "") -> str:
    """Strip quotes, whitespace, and accidental key= prefixes when pasting cookies."""
    if not val:
        return ""
    val = val.strip().strip('"').strip("'")
    if "=" in val:
        parts = val.split("=", 1)
        if key_name and parts[0].strip().lower() == key_name.lower():
            val = parts[1].strip()
        elif parts[0].strip().lower() in ("leetcode_session", "csrftoken"):
            val = parts[1].strip()
    return val.strip().strip('"').strip("'")


def sanitize_problem_slug(slug: str) -> str:
    """Extract clean problem slug (e.g. 'https://leetcode.com/problems/two-sum/' -> 'two-sum')."""
    slug = (slug or "two-sum").strip().lower()
    if "leetcode.com/problems/" in slug:
        slug = slug.split("leetcode.com/problems/")[-1]
    elif "problems/" in slug:
        slug = slug.split("problems/")[-1]
    slug = slug.split("?")[0].split("#")[0].strip("/")
    import re
    slug = re.sub(r"\s+", "-", slug)
    return slug or "two-sum"


def submit_to_leetcode(
    session_cookie: str,
    csrf_token: str,
    problem_slug: str = "two-sum",
    language: str = "python3",
    code: str = None,
) -> dict:
    """
    Submits source code to LeetCode's judge endpoint and polls for the execution verdict.
    Returns:
        dict with success (bool), status (str), submission_id (int/str), error (str)
    """
    problem_slug = sanitize_problem_slug(problem_slug)
    session_cookie = sanitize_cookie_val(session_cookie, "LEETCODE_SESSION")
    csrf_token = sanitize_cookie_val(csrf_token, "csrftoken")
    code = code or DEFAULT_TWO_SUM_PYTHON3
    language = (language or "python3").strip().lower()

    if not session_cookie or not csrf_token:
        return {
            "success": False,
            "status": "CONFIG_ERROR",
            "error": "LEETCODE_SESSION and csrftoken cookies are required for auto-rescue. Please paste them in Settings.",
        }

    question_id = get_leetcode_question_id(problem_slug)
    submit_url = f"https://leetcode.com/problems/{problem_slug}/submit/"

    cookie_dict = {
        "LEETCODE_SESSION": session_cookie,
        "csrftoken": csrf_token,
    }

    headers = {
        "Origin": "https://leetcode.com",
        "Referer": f"https://leetcode.com/problems/{problem_slug}/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "x-csrftoken": csrf_token,
        "X-CSRFToken": csrf_token,
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Cookie": f"LEETCODE_SESSION={session_cookie}; csrftoken={csrf_token};",
    }

    payload = {
        "lang": language,
        "question_id": question_id,
        "typed_code": code,
    }

    logger.info(f"Submitting auto-rescue problem '{problem_slug}' (QID: {question_id}, Lang: {language})...")

    try:
        resp = requests.post(
            submit_url,
            json=payload,
            headers=headers,
            cookies=cookie_dict,
            allow_redirects=False,
            timeout=15,
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "status": "NETWORK_ERROR",
            "error": f"Failed to connect to LeetCode: {exc}",
        }

    # Handle redirects (301/302)
    if resp.status_code in (301, 302, 307, 308):
        loc = resp.headers.get("Location", "")
        if "login" in loc.lower() or "accounts" in loc.lower():
            return {
                "success": False,
                "status": "AUTH_FAILED",
                "error": "LeetCode session cookie expired or invalid (redirected to login). Please copy fresh cookies from leetcode.com.",
            }
        # Follow redirect with POST to the canonical location if it's a slash-normalized redirect
        try:
            target_loc = loc if loc.startswith("http") else f"https://leetcode.com{loc}"
            resp = requests.post(
                target_loc,
                json=payload,
                headers=headers,
                cookies=cookie_dict,
                allow_redirects=False,
                timeout=15,
            )
        except Exception as exc:
            logger.warning(f"Failed to follow submission redirect to {loc}: {exc}")

    if resp.status_code in (401, 403):
        return {
            "success": False,
            "status": "AUTH_FAILED",
            "error": "LeetCode rejected authentication (HTTP 401/403). Your LEETCODE_SESSION or csrftoken may have expired.",
        }

    if resp.status_code == 404:
        return {
            "success": False,
            "status": "NOT_FOUND",
            "error": f"LeetCode returned 404 (Page Not Found) for problem '{problem_slug}'. Please ensure the Problem Slug in Settings is set to 'two-sum'.",
        }

    if resp.status_code != 200:
        return {
            "success": False,
            "status": f"HTTP_{resp.status_code}",
            "error": f"LeetCode returned HTTP {resp.status_code}: {resp.text[:200]}",
        }

    try:
        data = resp.json()
    except Exception:
        return {
            "success": False,
            "status": "PARSE_ERROR",
            "error": f"Invalid response from LeetCode: {resp.text[:200]}",
        }

    submission_id = data.get("submission_id")
    if not submission_id:
        error_msg = data.get("error") or data.get("detail") or str(data)
        return {
            "success": False,
            "status": "SUBMISSION_REJECTED",
            "error": f"LeetCode submission rejected: {error_msg}",
        }

    logger.info(f"Auto-rescue submission accepted by LeetCode (ID: {submission_id}). Polling judge...")

    # Poll judge for verdict (up to 6 attempts, 2.5s intervals)
    check_url = f"https://leetcode.com/submissions/detail/{submission_id}/check/"
    for attempt in range(6):
        time.sleep(2.5)
        try:
            check_resp = requests.get(check_url, headers=headers, timeout=10)
            if check_resp.status_code != 200:
                continue
            check_data = check_resp.json()
            state = check_data.get("state")
            if state == "SUCCESS":
                status_msg = check_data.get("status_msg")
                if status_msg == "Accepted":
                    return {
                        "success": True,
                        "status": "Accepted",
                        "submission_id": submission_id,
                        "runtime": check_data.get("status_runtime"),
                        "memory": check_data.get("status_memory"),
                    }
                else:
                    return {
                        "success": False,
                        "status": status_msg,
                        "submission_id": submission_id,
                        "error": f"LeetCode judge returned: {status_msg}",
                    }
        except Exception as exc:
            logger.warning(f"Error polling submission {submission_id}: {exc}")

    # If still pending after polling, report submitted ID
    return {
        "success": True,
        "status": "Submitted",
        "submission_id": submission_id,
        "note": "Submission received by LeetCode judge (status pending).",
    }


def execute_auto_rescue(user, force: bool = False) -> dict:
    """
    Executes emergency auto-rescue for an eligible user.
    Submits predefined problem, verifies verdict, updates streak state,
    and dispatches high-urgency notifications.
    """
    from app.extensions import db

    today_utc = datetime.now(timezone.utc).date().isoformat()

    if not force and not getattr(user, "auto_rescue_enabled", False):
        return {"success": False, "error": "Auto-rescue is not enabled for this user."}

    if not user.leetcode_session or not user.leetcode_csrf_token:
        return {"success": False, "error": "LeetCode session cookies not configured. Please paste your cookies and click 'Save Settings' first."}

    if not force and user.last_rescue_date_utc == today_utc:
        return {"success": False, "error": "Auto-rescue has already been executed today."}

    problem_slug = (user.rescue_problem_slug or "two-sum").strip()
    language = (user.rescue_language or "python3").strip()
    code = user.rescue_code if user.rescue_code and user.rescue_code.strip() else DEFAULT_TWO_SUM_PYTHON3

    logger.info(f"Triggering Auto-Rescue for User {user.id} ({user.email}) on '{problem_slug}'...")

    res = submit_to_leetcode(
        session_cookie=user.leetcode_session,
        csrf_token=user.leetcode_csrf_token,
        problem_slug=problem_slug,
        language=language,
        code=code,
    )

    if res.get("success"):
        user.last_rescue_date_utc = today_utc
        user.last_rescue_status = "Accepted"
        user.is_active_today = True
        user.today_submissions = max(user.today_submissions or 0, 1)

        # Notify Telegram & Email of rescue success
        _notify_rescue_event(user, success=True, problem_slug=problem_slug, detail=res)
    else:
        err = res.get("error", "Unknown error")
        user.last_rescue_status = f"FAILED: {err}"
        _notify_rescue_event(user, success=False, problem_slug=problem_slug, detail=res)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(f"Failed to commit auto-rescue status: {exc}")

    return res


def _notify_rescue_event(user, success: bool, problem_slug: str, detail: dict):
    """
    Sends an immediate high-priority alert to all connected channels (Telegram / Email)
    documenting the result of the emergency auto-rescue run.
    Guarded to never raise exceptions or disrupt caller.
    """
    try:
        if success:
            sub_id = detail.get("submission_id", "N/A")
            tg_text = (
                f"🚨 <b>STREAK AUTO-RESCUE SUCCESS!</b>\n\n"
                f"Your backup problem (<b>{problem_slug}</b>) was automatically submitted and <b>Accepted</b> by LeetCode (Submission: <code>{sub_id}</code>).\n\n"
                f"🎉 <b>Your streak is 100% safe for today!</b> No streak freeze or reset needed."
            )
            email_subj = f"🚨 [Streak Rescued] Your backup solution for '{problem_slug}' was Accepted!"
            email_body = (
                f"Emergency Streak Airbag Activated:\n\n"
                f"We noticed no problems were submitted today. Your predefined solution for '{problem_slug}' "
                f"was automatically submitted to LeetCode and received an ACCEPTED verdict!\n\n"
                f"Submission ID: {sub_id}\nStatus: {detail.get('status', 'Accepted')}\n"
                f"Your daily streak remains protected."
            )
        else:
            err_msg = detail.get("error", "Submission error")
            tg_text = (
                f"⚠️ <b>STREAK AUTO-RESCUE FAILED!</b>\n\n"
                f"The Guardian tried to auto-submit your backup problem (<b>{problem_slug}</b>), but LeetCode returned an error:\n"
                f"<code>{err_msg}</code>\n\n"
                f"⏰ <b>Action Required:</b> Please solve and submit a problem manually on LeetCode immediately before UTC midnight!"
            )
            email_subj = f"⚠️ [ACTION REQUIRED] Auto-Rescue Failed for '{problem_slug}'"
            email_body = (
                f"Emergency Streak Airbag Warning:\n\n"
                f"We attempted to submit your backup solution for '{problem_slug}', but the submission failed:\n\n"
                f"Reason: {err_msg}\n\n"
                f"Please log into LeetCode and solve today's problem manually before 23:59 UTC to keep your streak alive!"
            )

        notifications = {"telegram": "not configured", "email": "not configured"}

        # 1. Telegram
        if user.telegram_chat_id:
            try:
                from app.services.telegram_service import send_telegram_message
                tg_ok = send_telegram_message(str(user.telegram_chat_id), tg_text, parse_mode="HTML")
                notifications["telegram"] = "delivered" if tg_ok else "failed (check bot token or permissions)"
            except Exception as tg_err:
                notifications["telegram"] = f"error: {tg_err}"
                logger.warning(f"Failed to send Telegram rescue notice: {tg_err}")

        # 2. Email
        target_email = getattr(user, "reminder_email", None) or getattr(user, "email", None)
        if target_email:
            try:
                from app.services.email_service import send_email
                mail_res = send_email(target_email, email_subj, email_body)
                notifications["email"] = mail_res.get("mode", "sent" if mail_res.get("success") else "failed")
            except Exception as mail_err:
                notifications["email"] = f"error: {mail_err}"
                logger.warning(f"Failed to send email rescue notice: {mail_err}")

        detail["notifications"] = notifications
        return notifications
    except Exception as exc:
        logger.warning(f"Unexpected error in _notify_rescue_event: {exc}")
        return {"telegram": "error", "email": "error"}
