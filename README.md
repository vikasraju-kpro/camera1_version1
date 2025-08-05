# Fisheye Camera Control (camera1_version1)

This project provides a web interface to control a single fisheye camera on a Raspberry Pi.

## Features

-   Capture still images.
-   Record distorted video.
-   View a system health report (CPU, memory, disk).
-   Restart the web application.
-   Restart the Raspberry Pi.

## Setup

1.  **Clone the repository:**

    ```bash
    git clone <your-repo-url>
    cd camera1_version1
    ```

2.  **Create Virtual Environment and Install Dependencies:**

    Create a virtual environment that has access to the system's site packages. This is useful for accessing system-wide libraries like `picamera2` and `OpenCV` if they are already installed on the Raspberry Pi.

    ```bash
    # Create the virtual environment
    python3 -m venv --system-site-packages venv

    # Activate the virtual environment
    source venv/bin/activate

    # Install any remaining dependencies
    pip install -r requirements.txt
    ```

3.  **Run the Application as a Service:**

    For the application to run on boot and for the restart buttons to work correctly, it should be run as a `systemd` service. Follow the instructions in the "Running as a Service" section below.

4.  **Access the Web Interface:**

    Open a web browser and navigate to `http://<your-raspberry-pi-ip>:5000`.

## Running as a Service (Production)

1.  Ensure the `start.sh` script in the project directory is executable (`chmod +x start.sh`).
2.  Create and enable the `camera_app.service` file as instructed previously.
3.  Start the service:
    ```bash
    sudo systemctl start camera_app.service
    ```
4.  Check its status:
    ```bash
    sudo systemctl status camera_app.service
    ```

## Development Mode

To run the app directly for development or debugging (without using the service):

```bash
# Make sure your virtual environment is active
source venv/bin/activate

# Run the app with Gunicorn
gunicorn --threads 4 --workers 1 --bind 0.0.0.0:5000 app:app