"""
Windows Startup Manager for LeetCode Streak Guardian.
Manages automatic launch on Windows boot using HKCU Run registry key.
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LeetCodeStreakGuardian"


def get_launch_command() -> str:
    """Returns the executable or python command to launch the app minimized."""
    if getattr(sys, "frozen", False):
        # Compiled executable (.exe)
        exe_path = sys.executable
        return f'"{exe_path}" --background'
    else:
        # Running as python script
        py_exe = sys.executable
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "app.py"))
        return f'"{py_exe}" "{script_path}" --background'


def is_startup_enabled() -> bool:
    """Check if the app is currently configured to run on Windows startup."""
    if os.name != "nt":
        return False

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except Exception as exc:
        logger.error(f"Error checking startup registry: {exc}")
        return False


def set_startup_enabled(enable: bool) -> bool:
    """Enable or disable launch on Windows startup."""
    if os.name != "nt":
        return False

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                cmd = get_launch_command()
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                logger.info("Enabled launch on Windows startup.")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    logger.info("Disabled launch on Windows startup.")
                except FileNotFoundError:
                    pass
        return True
    except Exception as exc:
        logger.error(f"Error modifying startup registry: {exc}")
        return False
