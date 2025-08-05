import os

# The primary and fallback paths for the machine-id file
MACHINE_ID_PATH = "/etc/machine-id"
MACHINE_ID_FALLBACK_PATH = "/var/lib/dbus/machine-id"

def get_device_uuid():
    """
    Retrieves a unique and stable device ID from the system's machine-id file.
    """
    try:
        path_to_read = ""
        if os.path.exists(MACHINE_ID_PATH):
            path_to_read = MACHINE_ID_PATH
        elif os.path.exists(MACHINE_ID_FALLBACK_PATH):
            path_to_read = MACHINE_ID_FALLBACK_PATH
        else:
            return "unknown_uuid" # Return a default if no ID file is found

        with open(path_to_read, 'r') as f:
            # The file content is a hex string, which is a perfect UUID.
            # .strip() removes any newline characters.
            return f.read().strip()
    except Exception as e:
        print(f"ERROR: Could not read device UUID: {e}")
        return "unknown_uuid_error"

def get_device_name():
    """
    Returns the hardcoded device name.
    """
    return "keye1"