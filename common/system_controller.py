import os
import sys

# The name of your systemd service file
SERVICE_NAME = "camera_app.service"

def restart_app():
    """Restarts the application by restarting the systemd service."""
    print(f"--- Restarting Application via systemctl restart {SERVICE_NAME} ---")
    try:
        # Use sudo to run the systemctl command
        os.system(f"sudo systemctl restart {SERVICE_NAME}")
    except Exception as e:
        print(f"ERROR: Failed to restart application service: {e}")


def restart_system():
    """Reboots the Raspberry Pi."""
    print("--- Restarting System ---")
    try:
        os.system("sudo reboot")
    except Exception as e:
        print(f"ERROR: Failed to restart system: {e}")