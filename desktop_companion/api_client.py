"""
HTTP API client for LeetCode Streak Guardian Desktop Companion.
Fetches real-time streak activity and alert status from the web platform.
"""

import requests
import logging

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    pass


def fetch_streak_status(server_url: str, api_token: str, refresh: bool = False) -> dict:
    """
    Query the streak status API endpoint.
    """
    if not server_url:
        raise APIClientError("Server URL is not configured.")
    if not api_token:
        raise APIClientError("API Token is not configured. Please paste your token from the dashboard.")

    url = server_url.rstrip("/") + "/api/v1/streak-status"
    headers = {
        "X-API-Key": api_token,
        "User-Agent": "LeetCodeStreakGuardian-Desktop/1.0",
    }
    params = {}
    if refresh:
        params["refresh"] = "true"

    try:
        response = requests.get(url, headers=headers, params=params, timeout=12)
        if response.status_code == 401:
            raise APIClientError("Invalid or expired API token. Please check your token in settings.")
        if response.status_code != 200:
            raise APIClientError(f"Server returned status {response.status_code}: {response.text}")

        data = response.json()
        if data.get("status") != "success":
            raise APIClientError(data.get("message", "Unknown error from server."))

        return data
    except requests.RequestException as exc:
        logger.error(f"Network error querying server: {exc}")
        raise APIClientError(f"Could not connect to server ({exc}). Ensure the server is online.")
