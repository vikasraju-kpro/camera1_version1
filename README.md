````markdown
# Fisheye Camera Control (camera1_version1)

This project provides a web interface to control a single fisheye camera on a Raspberry Pi.

## Features

-   Capture still images.
-   Record distorted video.
-   View a system health report (CPU, memory, disk).
-   Restart the web application.
-   Restart the Raspberry Pi.

---
## Setup

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd camera1_version1
````

### 2\. Create Virtual Environment and Install Dependencies

Create a virtual environment that has access to the system's site packages.

```bash
# Create the virtual environment
python3 -m venv --system-site-packages venv

# Activate the virtual environment
source venv/bin/activate

# Install any remaining dependencies
pip install -r requirements.txt
```

> **Note:** If you encounter a `numpy.dtype size changed` error after this step, please see the **Troubleshooting** section below.

### 3\. Set Up the Application Service

For the application to run on boot, it must be run as a `systemd` service. Follow the detailed instructions in the "Running as a Service (Production)" section below.

### 4\. Access the Web Interface

Once the service is running, open a web browser and navigate to `http://<your-raspberry-pi-ip>:5000`.

-----

## Troubleshooting

### `ValueError: numpy.dtype size changed`

This error can occur after installing dependencies because of a conflict between the system's pre-compiled libraries (like `picamera2`) and the version of `numpy` installed by `pip`.

To fix this, run the following commands inside your activated virtual environment:

```bash
# 1. Uninstall the conflicting libraries to ensure a clean state
pip uninstall picamera2 simplejpeg numpy

# 2. Reinstall picamera2, forcing it to be re-compiled from source
pip install --no-cache-dir --no-binary :all: picamera2
```

This will rebuild the libraries against the correct version of NumPy in your environment, resolving the conflict.

-----

## Running as a Service (Production)

Follow these steps to set up and run the application as a background service that starts on boot.

### Step 1: Create the Startup Script

Create a shell script named `start.sh` in your project's root directory (`/home/sakiv/projects/camera1_version1/`).

**File: `start.sh`**

```bash
#!/bin/bash
cd /home/sakiv/projects/camera1_version1
source veni/bin/activate
exec gunicorn --workers 1 --threads 4 --bind 0.0.0.0:5000 app:app
```

After creating the file, **make it executable**:

```bash
chmod +x start.sh
```

### Step 2: Create the systemd Service File

Create a new service definition file for `systemd`.

**Command:**

```bash
sudo nano /etc/systemd/system/camera_app.service
```

Paste the following content into the editor.

**File: `camera_app.service`**

```ini
[Unit]
Description=Gunicorn instance to serve the Camera Control application
After=network.target

[Service]
User=sakiv
Group=www-data
WorkingDirectory=/home/sakiv/projects/camera1_version1
ExecStart=/home/sakiv/projects/camera1_version1/start.sh
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

### Step 3: Grant Sudo Privileges

To allow the "Restart App" and "Restart System" buttons to work, grant the `sakiv` user passwordless `sudo` access for the required commands.

**Command:**

```bash
sudo visudo
```

Scroll to the bottom of the file and add these two lines:

```
# Allow the sakiv user to restart the camera service and reboot the system without a password
sakiv ALL=(ALL) NOPASSWD: /bin/systemctl restart camera_app.service
sakiv ALL=(ALL) NOPASSWD: /sbin/reboot
```

### Step 4: Enable and Run the Service

Finally, load, enable, and start your new service.

```bash
# Reload the systemd daemon to recognize the new service file
sudo systemctl daemon-reload

# Enable the service to start automatically on boot
sudo systemctl enable camera_app.service

# Start the service now
sudo systemctl start camera_app.service

# Check the status to ensure it's running correctly
sudo systemctl status camera_app.service
```

-----

## Development Mode

To run the app directly for development or debugging:

```bash
# First, ensure the service is stopped
sudo systemctl stop camera_app.service

# Make sure your virtual environment is active
source venv/bin/activate

# Run the app directly with Python's development server
python3 app.py
```

```
```
