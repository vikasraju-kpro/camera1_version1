import psutil
from .device_info import get_device_uuid # Import the function

# Path to the file containing the CPU temperature
TEMP_FILE_PATH = "/sys/class/thermal/thermal_zone0/temp"

def get_cpu_temperature():
    """Reads the CPU temperature from the system file and returns it in Celsius."""
    try:
        with open(TEMP_FILE_PATH, 'r') as f:
            # The value is in millidegrees Celsius, so divide by 1000
            temperature_milli_c = int(f.read().strip())
            return round(temperature_milli_c / 1000.0, 1)
    except (IOError, ValueError) as e:
        print(f"WARN: Could not read CPU temperature: {e}")
        return None # Return None if reading fails


def get_health_report():
    """
    Generates a health report of the system, including the device ID and CPU temperature.
    """
    try:
        health = {
            "device_id": get_device_uuid(), # Add device_id here
            "cpu_usage_percent": psutil.cpu_percent(interval=1),
            "memory_usage_percent": psutil.virtual_memory().percent,
            "disk_usage_percent": psutil.disk_usage("/").percent,
            "cpu_temperature_c": get_cpu_temperature(), # Add CPU temperature
        }
        return health
    except Exception as e:
        print(f"ERROR: Could not retrieve health report: {e}")
        return {
            "error": "Could not retrieve health information.",
            "details": str(e),
        }