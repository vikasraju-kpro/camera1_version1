import psutil
from .device_info import get_device_uuid # Import the function

def get_health_report():
    """
    Generates a health report of the system, including the device ID.
    """
    try:
        health = {
            "device_id": get_device_uuid(), # Add device_id here
            "cpu_usage_percent": psutil.cpu_percent(interval=1),
            "memory_usage_percent": psutil.virtual_memory().percent,
            "disk_usage_percent": psutil.disk_usage("/").percent,
        }
        return health
    except Exception as e:
        print(f"ERROR: Could not retrieve health report: {e}")
        return {
            "error": "Could not retrieve health information.",
            "details": str(e),
        }