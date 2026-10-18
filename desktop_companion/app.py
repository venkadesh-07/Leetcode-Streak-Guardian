"""
LeetCode Streak Guardian — Desktop Companion Application.
Runs in the background, triggers native Windows desktop alerts on PC startup,
and provides a clean control panel to configure settings and sync tokens.
"""

import argparse
from datetime import datetime, timezone
import logging
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser

try:
    from desktop_companion.config import load_config, save_config
    from desktop_companion.notifier import show_streak_notification
    from desktop_companion.startup_manager import is_startup_enabled, set_startup_enabled
    from desktop_companion.api_client import fetch_streak_status, APIClientError
except ImportError:
    from config import load_config, save_config
    from notifier import show_streak_notification
    from startup_manager import is_startup_enabled, set_startup_enabled
    from api_client import fetch_streak_status, APIClientError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("GuardianDesktop")


class GuardianDesktopApp:
    def __init__(self, root: tk.Tk, start_hidden: bool = False):
        self.root = root
        self.config = load_config()
        self.running = True
        self.worker_thread = None

        # Apply dark theme styling
        self._setup_styles()
        self._build_ui()

        # Sync startup registry state
        if is_startup_enabled() != self.config.get("run_on_startup", True):
            set_startup_enabled(self.config.get("run_on_startup", True))

        # Start periodic background monitor
        self.worker_thread = threading.Thread(target=self._background_loop, daemon=True)
        self.worker_thread.start()

        if start_hidden:
            self.root.withdraw()
            logger.info("Companion started in background mode.")
            # Trigger immediate startup boot check in a separate thread
            threading.Thread(target=self._run_check_and_notify, args=(True,), daemon=True).start()
        else:
            self.root.deiconify()

    def _setup_styles(self):
        self.root.title("LeetCode Streak Guardian")
        self.root.geometry("520x620")
        self.root.resizable(False, False)
        self.root.configure(bg="#0a0e17")

        # Custom styling for ttk widgets
        style = ttk.Style()
        style.theme_use("clam")

        # Configure dark colors
        style.configure("TFrame", background="#0a0e17")
        style.configure("Card.TFrame", background="#111827", relief="solid", borderwidth=1)
        style.configure("TLabel", background="#0a0e17", foreground="#f8fafc", font=("Segoe UI", 10))
        style.configure("Card.TLabel", background="#111827", foreground="#94a3b8", font=("Segoe UI", 9))
        style.configure("CardHeader.TLabel", background="#111827", foreground="#f8fafc", font=("Segoe UI", 12, "bold"))
        style.configure("Status.TLabel", background="#162032", foreground="#fbbf24", font=("Segoe UI", 10, "bold"), padding=8)

        style.configure(
            "Primary.TButton",
            background="#f59e0b",
            foreground="#000000",
            font=("Segoe UI", 10, "bold"),
            borderwidth=0,
            padding=8,
        )
        style.map("Primary.TButton", background=[("active", "#fbbf24")])

        style.configure(
            "Secondary.TButton",
            background="#1f2937",
            foreground="#f8fafc",
            font=("Segoe UI", 9),
            borderwidth=0,
            padding=6,
        )
        style.map("Secondary.TButton", background=[("active", "#374151")])

        style.configure("TCheckbutton", background="#111827", foreground="#f8fafc", font=("Segoe UI", 10))

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header Title
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))

        title_lbl = tk.Label(
            header_frame,
            text="🛡️ LeetCode Streak Guardian",
            font=("Segoe UI", 16, "bold"),
            bg="#0a0e17",
            fg="#f59e0b",
        )
        title_lbl.pack(anchor=tk.W)

        subtitle_lbl = tk.Label(
            header_frame,
            text="Desktop Startup Notification & Streak Protection",
            font=("Segoe UI", 9),
            bg="#0a0e17",
            fg="#94a3b8",
        )
        subtitle_lbl.pack(anchor=tk.W)

        # Status Banner
        self.status_var = tk.StringVar(value="Status: Ready & Monitoring")
        self.status_box = tk.Label(
            main_frame,
            textvariable=self.status_var,
            bg="#162032",
            fg="#fbbf24",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=8,
            anchor="w",
        )
        self.status_box.pack(fill=tk.X, pady=(0, 15))

        # Settings Card
        card = tk.Frame(main_frame, bg="#111827", highlightbackground="#374151", highlightthickness=1, padx=16, pady=16)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        tk.Label(card, text="⚙️ Connection & Token Settings", font=("Segoe UI", 11, "bold"), bg="#111827", fg="#f8fafc").pack(anchor=tk.W, pady=(0, 12))

        # Server URL
        tk.Label(card, text="Server URL:", font=("Segoe UI", 9), bg="#111827", fg="#94a3b8").pack(anchor=tk.W)
        self.server_url_var = tk.StringVar(value=self.config.get("server_url", "http://127.0.0.1:5000"))
        self.server_entry = tk.Entry(card, textvariable=self.server_url_var, bg="#1e293b", fg="#f8fafc", insertbackground="#f8fafc", relief="flat", font=("Consolas", 10))
        self.server_entry.pack(fill=tk.X, pady=(4, 12), ipady=4)

        # API Token
        tk.Label(card, text="Personal Sync Token (from Web Dashboard):", font=("Segoe UI", 9), bg="#111827", fg="#94a3b8").pack(anchor=tk.W)
        self.token_var = tk.StringVar(value=self.config.get("api_token", ""))
        self.token_entry = tk.Entry(card, textvariable=self.token_var, bg="#1e293b", fg="#f8fafc", insertbackground="#f8fafc", relief="flat", font=("Consolas", 10))
        self.token_entry.pack(fill=tk.X, pady=(4, 12), ipady=4)

        # Startup Checkbox
        self.startup_var = tk.BooleanVar(value=self.config.get("run_on_startup", True))
        self.startup_cb = tk.Checkbutton(
            card,
            text="🚀 Run automatically on Windows startup",
            variable=self.startup_var,
            bg="#111827",
            fg="#f8fafc",
            selectcolor="#1e293b",
            activebackground="#111827",
            activeforeground="#f59e0b",
            font=("Segoe UI", 10),
            command=self._on_startup_toggle,
        )
        self.startup_cb.pack(anchor=tk.W, pady=(4, 12))

        # Check Interval Option
        interval_frame = tk.Frame(card, bg="#111827")
        interval_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(interval_frame, text="Notification Interval:", font=("Segoe UI", 9), bg="#111827", fg="#94a3b8").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value=str(self.config.get("check_interval_hours", 2)))
        self.interval_combo = ttk.Combobox(interval_frame, textvariable=self.interval_var, values=["1", "2", "4", "6"], width=6, state="readonly")
        self.interval_combo.pack(side=tk.LEFT, padx=10)
        tk.Label(interval_frame, text="hours", font=("Segoe UI", 9), bg="#111827", fg="#94a3b8").pack(side=tk.LEFT)

        # Action Buttons Grid
        btn_frame = tk.Frame(main_frame, bg="#0a0e17")
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        save_btn = tk.Button(
            btn_frame,
            text="💾 Save Settings",
            command=self._on_save_settings,
            bg="#f59e0b",
            fg="#000000",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=14,
            pady=6,
            cursor="hand2",
        )
        save_btn.pack(side=tk.LEFT, padx=(0, 8))

        test_btn = tk.Button(
            btn_frame,
            text="🔔 Test Desktop Alert",
            command=self._on_test_notification,
            bg="#1f2937",
            fg="#f8fafc",
            font=("Segoe UI", 9),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        )
        test_btn.pack(side=tk.LEFT, padx=(0, 8))

        check_btn = tk.Button(
            btn_frame,
            text="⚡ Check Streak Now",
            command=lambda: threading.Thread(target=self._run_check_and_notify, args=(False,), daemon=True).start(),
            bg="#1f2937",
            fg="#f8fafc",
            font=("Segoe UI", 9),
            relief="flat",
            padx=12,
            pady=6,
            cursor="hand2",
        )
        check_btn.pack(side=tk.LEFT)

        # Footer minimize info
        footer_frame = tk.Frame(main_frame, bg="#0a0e17")
        footer_frame.pack(fill=tk.X, pady=(10, 0))

        hide_btn = tk.Button(
            footer_frame,
            text="Minimize to Background",
            command=self.root.withdraw,
            bg="#111827",
            fg="#94a3b8",
            font=("Segoe UI", 8),
            relief="flat",
            padx=8,
            pady=4,
            cursor="hand2",
        )
        hide_btn.pack(side=tk.RIGHT)

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_save_settings(self):
        server_url = self.server_url_var.get().strip()
        api_token = self.token_var.get().strip()
        try:
            interval = int(self.interval_var.get().strip())
        except ValueError:
            interval = 2

        self.config["server_url"] = server_url
        self.config["api_token"] = api_token
        self.config["check_interval_hours"] = interval
        self.config["run_on_startup"] = self.startup_var.get()

        save_config(self.config)
        set_startup_enabled(self.config["run_on_startup"])

        self.status_var.set("✅ Settings saved successfully.")
        self.status_box.configure(fg="#34d399")
        messagebox.showinfo("Saved", "Configuration has been saved successfully!")

    def _on_startup_toggle(self):
        enabled = self.startup_var.get()
        self.config["run_on_startup"] = enabled
        save_config(self.config)
        set_startup_enabled(enabled)
        state_str = "Enabled" if enabled else "Disabled"
        self.status_var.set(f"Windows Startup Launch: {state_str}")

    def _on_test_notification(self):
        """Trigger an instant sample notification to test sound and visuals."""
        show_streak_notification(
            title="🔥 LeetCode Streak at Risk!",
            message="Test Desktop Alert: Keep your 12-day streak alive! Solve today's challenge.",
            launch_url="https://leetcode.com/problemset/all/",
        )
        self.status_var.set("🔔 Test alert sent to Windows desktop!")

    def _run_check_and_notify(self, is_boot_check: bool = False):
        """Perform streak inquiry and dispatch alert if required."""
        self.status_var.set("Checking LeetCode streak status...")
        self.status_box.configure(fg="#fbbf24")

        server_url = self.config.get("server_url")
        api_token = self.config.get("api_token")

        if not api_token:
            msg = "API Token missing! Please open dashboard and paste your token."
            self.status_var.set(f"⚠️ {msg}")
            if not is_boot_check:
                messagebox.showwarning("Setup Required", msg)
            return

        try:
            data = fetch_streak_status(server_url, api_token, refresh=True)
            streak_info = data.get("streak", {})
            time_info = data.get("time_remaining", {})
            active_today = streak_info.get("active_today", False)
            streak_count = streak_info.get("current_streak", 0)
            today_utc = streak_info.get("last_checked_date_utc", "")
            solve_url = data.get("solve_url", "https://leetcode.com/problemset/all/")

            now_ts = int(time.time())

            if active_today:
                status_text = f"✅ Protected Today! Streak: {streak_count} days ({streak_info.get('submissions_today', 0)} solved)."
                self.status_var.set(status_text)
                self.status_box.configure(fg="#34d399")
            else:
                # Streak at risk!
                status_text = f"⚠️ At Risk! Streak: {streak_count} days. ({time_info.get('formatted', '')})"
                self.status_var.set(status_text)
                self.status_box.configure(fg="#f87171")

                # Show native desktop notification
                title = "🔥 LeetCode Streak at Risk!"
                body = (
                    f"You haven't solved a problem today!\n"
                    f"Keep your {streak_count}-day streak alive! ({time_info.get('formatted', 'Reset approaching')})"
                )
                show_streak_notification(title, body, launch_url=solve_url)

                self.config["last_notified_date_utc"] = today_utc
                self.config["last_notified_ts"] = now_ts
                save_config(self.config)

        except APIClientError as err:
            err_msg = str(err)
            self.status_var.set(f"❌ Error: {err_msg}")
            self.status_box.configure(fg="#f87171")
            if not is_boot_check:
                messagebox.showerror("Check Failed", err_msg)
        except Exception as exc:
            self.status_var.set(f"❌ Unexpected error: {exc}")
            self.status_box.configure(fg="#f87171")

    def _background_loop(self):
        """Background daemon polling streak status periodically."""
        while self.running:
            interval_hours = max(1, self.config.get("check_interval_hours", 2))
            sleep_seconds = interval_hours * 3600

            # Sleep in small slices to remain responsive to shutdown
            for _ in range(int(sleep_seconds // 10)):
                if not self.running:
                    return
                time.sleep(10)

            if self.config.get("api_token"):
                logger.info("Executing periodic background streak check...")
                self._run_check_and_notify(is_boot_check=False)

    def _on_close(self):
        """Handle window close event: minimize or ask to exit."""
        res = messagebox.askyesnocancel(
            "LeetCode Streak Guardian",
            "Would you like to keep Streak Guardian running in the background?\n\n"
            "• Yes: Keep running in background (checks streak on startup)\n"
            "• No: Completely exit application",
        )
        if res is True:
            self.root.withdraw()
        elif res is False:
            self.running = False
            self.root.destroy()
            sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="LeetCode Streak Guardian Desktop Companion")
    parser.add_argument("--background", action="store_true", help="Launch minimized in background (system startup mode)")
    args = parser.parse_args()

    root = tk.Tk()
    app = GuardianDesktopApp(root, start_hidden=args.background)
    root.mainloop()


if __name__ == "__main__":
    main()
