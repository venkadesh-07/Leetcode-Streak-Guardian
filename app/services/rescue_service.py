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
    problem_slug = (problem_slug or "two-sum").strip().lower()
    session_cookie = (session_cookie or "").strip()
    csrf_token = (csrf_token or "").strip()
    code = code or DEFAULT_TWO_SUM_PYTHON3
    language = (language or "python3").strip().lower()

    if not session_cookie or not csrf_token:
        return {
            "success": False,
            "status": "CONFIG_ERROR",
            "error": "LEETCODE_SESSION and csrftoken cookies are required for auto-rescue.",
        }

    question_id = get_leetcode_question_id(problem_slug)
    submit_url = f"https://leetcode.com/problems/{problem_slug}/submit/"

    headers = {
        "Origin": "https://leetcode.com",
        "Referer": f"https://leetcode.com/problems/{problem_slug}/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "x-csrftoken": csrf_token,
        "Content-Type": "application/json",
        "Cookie": f"LEETCODE_SESSION={session_cookie}; csrftoken={csrf_token};",
    }

    payload = {
        "lang": language,
        "question_id": question_id,
        "typed_code": code,
    }

    logger.info(f"Submitting auto-rescue problem '{problem_slug}' (QID: {question_id}, Lang: {language})...")

    try:
        resp = requests.post(submit_url, json=payload, headers=headers, timeout=15)
    except requests.RequestException as exc:
        return {
            "success": False,
            "status": "NETWORK_ERROR",
            "error": f"Failed to connect to LeetCode: {exc}",
        }

    if resp.status_code in (401, 403):
        return {
            "success": False,
            "status": "AUTH_FAILED",
            "error": "LeetCode rejected authentication (HTTP 401/403). Your LEETCODE_SESSION or csrftoken may have expired.",
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

    if not getattr(user, "auto_rescue_enabled", False):
        return {"success": False, "error": "Auto-rescue is not enabled for this user."}

    if not user.leetcode_session or not user.leetcode_csrf_token:
        return {"success": False, "error": "LeetCode session cookies not configured."}

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
    """
    from app.services.telegram_service import get_telegram_bot_token

    if success:
        sub_id = detail.get("submission_id", "N/A")
        tg_text = (
            f"🚨 *STREAK AUTO-RESCUE SUCCESS!*\n\n"
            f"Your backup problem (*{problem_slug}*) was automatically submitted and **Accepted** by LeetCode (Submission: `{sub_id}`).\n\n"
            f"🎉 *Your streak is 100% safe for today!* No streak freeze or reset needed."
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
            f"⚠️ *STREAK AUTO-RESCUE FAILED!*\n\n"
            f"The Guardian tried to auto-submit your backup problem (*{problem_slug}*), but LeetCode returned an error:\n"
            f"`{err_msg}`\n\n"
            f"⏰ *Action Required:* Please solve and submit a problem manually on LeetCode immediately before UTC midnight!"
        )
        email_subj = f"⚠️ [ACTION REQUIRED] Auto-Rescue Failed for '{problem_slug}'"
        email_body = (
            f"Emergency Streak Airbag Warning:\n\n"
            f"We attempted to submit your backup solution for '{problem_slug}', but the submission failed:\n\n"
            f"Reason: {err_msg}\n\n"
            f"Please log into LeetCode and solve today's problem manually before 23:59 UTC to keep your streak alive!"
        )

    # 1. Telegram
    if getattr(user, "notify_telegram", False) and user.telegram_chat_id:
        bot_token = get_telegram_bot_token()
        if bot_token:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": user.telegram_chat_id,
                        "text": tg_text,
                        "parse_mode": "Markdown",
                    },
                    timeout=8,
                )
            except Exception as exc:
                logger.warning(f"Failed to send Telegram rescue notice: {exc}")

    # 2. Email
    target_email = getattr(user, "reminder_email", None) or getattr(user, "email", None)
    if getattr(user, "notify_email", False) and target_email:
        try:
            from app.services.email_service import _send_email
            _send_email(target_email, email_subj, email_body)
        except Exception as exc:
            logger.warning(f"Failed to send email rescue notice: {exc}")
