import os
import sys


def restart_app():
    """Restarts the current Python application."""
    print("--- Restarting Application ---")
    try:
        python = sys.executable
        os.execl(python, python, *sys.argv)
    except Exception as e:
        print(f"ERROR: Failed to restart application: {e}")


def restart_pi():
    """Reboots the Raspberry Pi."""
    print("--- Restarting Raspberry Pi ---")
    try:
        os.system("sudo reboot")
    except Exception as e:
        print(f"ERROR: Failed to restart Raspberry Pi: {e}")