"""
Native Windows Toast Notification Dispatcher for LeetCode Streak Guardian.
Uses modern Windows WinRT APIs to display interactive, high-priority notifications
in the Windows Notification Action Center.
"""

import logging
import webbrowser

logger = logging.getLogger(__name__)

APP_ID = "LeetCode Streak Guardian"


def show_streak_notification(title: str, message: str, launch_url: str = None) -> bool:
    """
    Display a native Windows Toast notification banner.
    Clicking the banner opens the launch_url in the default web browser.
    """
    try:
        from windows_toasts import InteractableWindowsToaster, Toast

        toaster = InteractableWindowsToaster(APP_ID)
        toast = Toast()
        toast.text_fields = [title, message]

        if launch_url:
            toast.on_activated = lambda _: webbrowser.open(launch_url)

        toaster.show_toast(toast)
        logger.info(f"Native Windows notification shown: {title}")
        return True
    except Exception as exc:
        logger.warning(f"WinRT toast notification failed ({exc}). Falling back...")

    # Fallback to standard WindowsToaster if Interactable fails
    try:
        from windows_toasts import WindowsToaster, Toast

        toaster = WindowsToaster(APP_ID)
        toast = Toast()
        toast.text_fields = [title, message]
        toaster.show_toast(toast)
        return True
    except Exception as fallback_exc:
        logger.error(f"Notification delivery failed completely: {fallback_exc}")
        return False
