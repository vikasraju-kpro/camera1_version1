import psutil


def get_health_report():
    """
    Generates a dictionary containing the system's health status.
    """
    try:
        health = {
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