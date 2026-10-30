
import json
import re
from datetime import datetime, timedelta, timezone

import requests


# Fixed HTTPS endpoint. Never accept this URL from user input.
LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,50}$")

QUERY = """
query userSubmissionCalendar($username: String!) {
    matchedUser(username: $username) {
        username
        submissionCalendar
    }
}
"""


class LeetCodeCheckerError(Exception):
    """Raised when LeetCode activity cannot be checked safely."""


def calculate_streak(calendar, now=None):
    """
    Calculate the current consecutive daily streak from a LeetCode submissionCalendar.

    A streak continues if:
    - The user submitted today (day 0) and days prior consecutively, OR
    - The user submitted yesterday (day 1) and days prior consecutively (streak is at risk today).

    Returns:
        current_streak (int): Count of consecutive active days.
    """
    if not isinstance(calendar, dict):
        return 0

    if now is None:
        now = datetime.now(timezone.utc)

    today = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    def get_count_for_day(days_ago):
        target_dt = today - timedelta(days=days_ago)
        target_ts = int(target_dt.timestamp())
        raw_val = calendar.get(str(target_ts), 0)
        return raw_val if isinstance(raw_val, int) and not isinstance(raw_val, bool) and raw_val > 0 else 0

    streak = 0
    today_active = get_count_for_day(0) > 0

    if today_active:
        streak = 1
        day_offset = 1
        while get_count_for_day(day_offset) > 0:
            streak += 1
            day_offset += 1
    elif get_count_for_day(1) > 0:
        streak = 1
        day_offset = 2
        while get_count_for_day(day_offset) > 0:
            streak += 1
            day_offset += 1
    else:
        streak = 0

    return streak


def check_daily_activity(username):
    """
    Check a LeetCode user's public submission calendar.

    Returns:
        A dictionary containing the username, activity status,
        submission count, streak count, and UTC date checked.

    Raises:
        LeetCodeCheckerError if the username, request, or response
        cannot be validated.
    """
    if not isinstance(username, str):
        raise LeetCodeCheckerError("Invalid username.")

    username = username.strip()

    if not USERNAME_PATTERN.fullmatch(username):
        raise LeetCodeCheckerError(
            "Invalid LeetCode username format."
        )

    payload = {
        "query": QUERY,
        "variables": {"username": username},
    }

    try:
        response = requests.post(
            LEETCODE_GRAPHQL_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "LeetCode-Streak-Guardian/1.0",
            },
            timeout=(3.05, 10),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise LeetCodeCheckerError(
            "Could not connect to LeetCode. Please try again later."
        ) from exc

    if response.status_code != 200:
        raise LeetCodeCheckerError(
            "LeetCode did not return a successful response."
        )

    content_type = response.headers.get("Content-Type", "").lower()

    if "application/json" not in content_type:
        raise LeetCodeCheckerError(
            "LeetCode returned an unexpected response format."
        )

    try:
        data = response.json()
    except (ValueError, TypeError) as exc:
        raise LeetCodeCheckerError(
            "LeetCode returned invalid JSON."
        ) from exc

    if not isinstance(data, dict) or data.get("errors"):
        raise LeetCodeCheckerError(
            "LeetCode could not provide the activity data."
        )

    result = data.get("data")

    if not isinstance(result, dict):
        raise LeetCodeCheckerError(
            "Activity data is missing."
        )

    user_data = result.get("matchedUser")

    if not isinstance(user_data, dict):
        raise LeetCodeCheckerError(
            "The LeetCode username was not found or is unavailable."
        )

    calendar_raw = user_data.get("submissionCalendar")

    if not isinstance(calendar_raw, str):
        raise LeetCodeCheckerError(
            "LeetCode returned an invalid submission calendar."
        )

    try:
        calendar = json.loads(calendar_raw)
    except (ValueError, TypeError) as exc:
        raise LeetCodeCheckerError(
            "LeetCode returned an invalid submission calendar."
        ) from exc

    if not isinstance(calendar, dict):
        raise LeetCodeCheckerError(
            "LeetCode returned an invalid submission calendar."
        )

    # Use UTC consistently until the calendar's date boundaries
    # have been verified.
    now = datetime.now(timezone.utc)

    today_timestamp = int(
        datetime(
            now.year,
            now.month,
            now.day,
            tzinfo=timezone.utc,
        ).timestamp()
    )

    raw_count = calendar.get(str(today_timestamp), 0)

    if (
        not isinstance(raw_count, int)
        or isinstance(raw_count, bool)
        or raw_count < 0
    ):
        raise LeetCodeCheckerError(
            "LeetCode returned an invalid submission count."
        )

    streak = calculate_streak(calendar, now)

    return {
        "username": username,
        "active_today": raw_count > 0,
        "submissions_today": raw_count,
        "current_streak": streak,
        "checked_date_utc": now.date().isoformat(),
    }


PROFILE_QUERY = """
query getUserProfile($username: String!) {
  matchedUser(username: $username) {
    profile { aboutMe }
  }
}
"""


def check_username_ownership(username: str, token: str) -> bool:
    """
    Fetch the LeetCode user's 'About Me' bio and check if it contains the
    verification token.

    Returns:
        True if the token is found in the bio, False otherwise.

    Raises:
        LeetCodeCheckerError on network or API failures.
    """
    if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username.strip()):
        raise LeetCodeCheckerError("Invalid LeetCode username format.")

    if not isinstance(token, str) or not token.startswith("guardian-"):
        raise LeetCodeCheckerError("Invalid verification token format.")

    payload = {
        "query": PROFILE_QUERY,
        "variables": {"username": username.strip()},
    }

    try:
        response = requests.post(
            LEETCODE_GRAPHQL_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "LeetCode-Streak-Guardian/1.0",
            },
            timeout=(3.05, 10),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise LeetCodeCheckerError(
            "Could not connect to LeetCode. Please try again later."
        ) from exc

    if response.status_code != 200:
        raise LeetCodeCheckerError(
            "LeetCode did not return a successful response."
        )

    content_type = response.headers.get("Content-Type", "").lower()
    if "application/json" not in content_type:
        raise LeetCodeCheckerError(
            "LeetCode returned an unexpected response format."
        )

    try:
        data = response.json()
    except (ValueError, TypeError) as exc:
        raise LeetCodeCheckerError("LeetCode returned invalid JSON.") from exc

    if not isinstance(data, dict) or data.get("errors"):
        raise LeetCodeCheckerError(
            "LeetCode could not provide the profile data."
        )

    try:
        about_me = data["data"]["matchedUser"]["profile"]["aboutMe"]
    except (KeyError, TypeError):
        raise LeetCodeCheckerError(
            "The LeetCode username was not found or profile is unavailable."
        )

    if not isinstance(about_me, str):
        return False

    return token in about_me
