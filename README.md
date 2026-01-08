# Fisheye Camera Control (camera1\_version1)

This project provides a web interface to control a single fisheye camera on a Raspberry Pi. It includes features for standard capture and recording, as well as a comprehensive workflow for calibrating the fisheye lens and undistorting videos.

## Features

  - **Camera Control**:
      - Capture still images.
      - Record distorted video directly from the camera.
  - **Fisheye Calibration**:
      - A dedicated web page to capture images of a (9x6) checkerboard pattern.
      - Real-time feedback shows if the checkerboard was successfully detected.
      - Runs a fisheye-specific calibration process to generate a camera matrix and distortion coefficients.
  - **Video Undistortion**:
      - Upload a distorted video file.
      - **Slow Process & Play**: Re-encodes the video for guaranteed in-browser playback.
      - **Quick Process & Download**: Processes the video without re-encoding for a much faster result, suitable for direct download.
  - **System Utilities**:
      - View a system health report (CPU, memory, disk).
      - Restart the web application.
      - Restart the Raspberry Pi.

-----

## Setup

### 1\. Clone the Repository

```bash
git clone https://github.com/vikasraju-kpro/camera1_version1.git
cd camera1_version1
```

### 2\. Create Virtual Environment and Install Dependencies

Create a virtual environment that has access to the system's site packages, which is important for `picamera2`.

```bash
# Create the virtual environment
python3 -m venv --system-site-packages venv

# Activate the virtual environment
source venv/bin/activate

# Install any remaining dependencies
pip install -r requirements.txt
```

> **Note:** If you encounter a `numpy.dtype size changed` error, please see the **Troubleshooting** section below.

### 3\. Set Up the Application Service

For the application to run automatically on boot, it must be run as a `systemd` service. Follow the detailed instructions in the "Running as a Service (Production)" section below.

### 4\. Access the Web Interface

Once the service is running, open a web browser and navigate to the IP address of your Raspberry Pi at port 5000.

  - **Main Controls**: `http://<your-raspberry-pi-ip>:5000/`
  - **Camera Calibration**: `http://<your-raspberry-pi-ip>:5000/calibration`

-----

## Fisheye Calibration Workflow

To get clean, undistorted videos, you must first calibrate the camera. This only needs to be done once.

**Required Material**: A printed checkerboard pattern with **9x6 internal corners**.

**Steps**:

1.  Navigate to the **Camera Calibration** page (`/calibration`).
2.  **Step 1: Capture Images**
      - Hold the checkerboard in front of the camera.
      - Click the "Capture Image" button. The application will show a preview and confirm if the checkerboard was found.
      - Capture at least **15 successful images** from various angles, distances, and positions in the camera's view.
3.  **Step 2: Run Calibration**
      - Once you have collected at least 15 good images, the "Run Calibration" button will become active.
      - Click it and wait. The process may take a minute.
      - A success message will appear when the calibration files (`camera_matrix.npy` and `dist_coeff.npy`) have been generated and saved in the `calibration_data/` directory.
4.  **Step 3: Test Undistortion**
      - Upload a video that was recorded with the fisheye camera.
      - Use **"Process & Play in Browser"** for a slower process that creates a web-playable video.
      - Use **"Quick Process & Download"** for a much faster process that creates a video file for download (which may not play in the browser).

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

### Undistorted video is blank or won't download

  - **Cause**: The calibration has not been run, or it failed.
  - **Solution**: Ensure you have successfully completed the calibration workflow and that `camera_matrix.npy` and `dist_coeff.npy` exist in the `calibration_data/` directory.

### `ffmpeg` command fails

  - **Cause**: `ffmpeg` is not installed or not available in the system's PATH.
  - **Solution**: Install `ffmpeg` on your Raspberry Pi: `sudo apt update && sudo apt install ffmpeg -y`.

-----

## Running as a Service (Production)

Follow these steps to set up and run the application as a background service that starts on boot.

### Step 1: Create the Startup Script

Create a shell script named `start.sh` in your project's root directory.

**File: `start.sh`**

```bash
#!/bin/bash
cd /home/sakiv/projects/camera1_version1
source venv/bin/activate
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

To allow the "Restart App" and "Restart System" buttons to work, grant the `sakiv` user passwordless `sudo` access.

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