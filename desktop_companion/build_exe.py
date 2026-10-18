"""
Executable Builder for LeetCode Streak Guardian Desktop Companion.
Uses PyInstaller to bundle the application into a standalone Windows .exe
that can run on any Windows 10/11 system without requiring Python.
"""

import os
import subprocess
import sys
from pathlib import Path


def build():
    base_dir = Path(__file__).resolve().parent
    entry_script = base_dir / "app.py"
    dist_dir = base_dir / "dist"
    build_dir = base_dir / "build"

    print("Building LeetCode Streak Guardian Desktop Executable...")
    print(f"Entry script: {entry_script}")

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=LeetCodeStreakGuardian",
        "--onefile",
        "--noconsole",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        f"--specpath={base_dir}",
        "--clean",
        "--collect-all=windows_toasts",
        "--collect-all=winrt",
        str(entry_script),
    ]

    print("Executing PyInstaller command...")
    result = subprocess.run(pyinstaller_cmd)
    if result.returncode == 0:
        exe_path = dist_dir / "LeetCodeStreakGuardian.exe"
        print(f"\n[SUCCESS] Executable built successfully!")
        print(f"File location: {exe_path}")
        print(f"Size: {exe_path.stat().st_size / (1024 * 1024):.2f} MB")
    else:
        print("\n[ERROR] Build failed. See logs above.")
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
