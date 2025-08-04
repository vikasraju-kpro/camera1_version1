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

2.  **Install dependencies:**

    It is recommended to use a virtual environment.

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Run the application:**

    ```bash
    gunicorn --threads 4 --workers 1 --bind 0.0.0.0:5000 app:app
    ```

    Alternatively, for development, you can run:

    ```bash
    python3 app.py
    ```

4.  **Access the web interface:**

    Open a web browser and navigate to `http://<your-raspberry-pi-ip>:5000`.