import datetime
import os
from flask import Flask, render_template, jsonify, url_for
from common.camera_controller import (
    initialize_camera,
    capture_image,
    start_recording,
    stop_recording,
    cleanup,
    get_recording_status,
)
from common.system_controller import restart_app, restart_system
from utils.health_check import get_health_report

app = Flask(__name__)

# --- Configuration ---
OUTPUT_DIR_IMAGES = "static/captures"
OUTPUT_DIR_VIDEOS = "static/recordings"
IMAGE_EXTENSION = ".jpg"
VIDEO_EXTENSION = ".mp4"

# --- Application Startup ---
print("--- Initializing Application ---")
os.makedirs(OUTPUT_DIR_IMAGES, exist_ok=True)
os.makedirs(OUTPUT_DIR_VIDEOS, exist_ok=True)
initialize_camera()
# --- End Application Startup ---


@app.route("/")
def index():
    """Renders the main HTML page."""
    return render_template("index.html")


@app.route("/capture_image", methods=["POST"])
def capture_image_route():
    """Endpoint to capture a still image."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}{IMAGE_EXTENSION}"
    filepath = os.path.join(OUTPUT_DIR_IMAGES, filename)
    success, message = capture_image(filepath)
    if success:
        return jsonify({"success": True, "message": message, "image_url": url_for("static", filename=f"captures/{filename}")})
    else:
        return jsonify({"success": False, "message": message}), 500


@app.route("/start_recording", methods=["POST"])
def start_recording_route():
    """Endpoint to start video recording."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recording_{timestamp}{VIDEO_EXTENSION}"
    filepath = os.path.join(OUTPUT_DIR_VIDEOS, filename)
    success, message = start_recording(filepath)
    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message}), 500


@app.route("/stop_recording", methods=["POST"])
def stop_recording_route():
    """Endpoint to stop video recording."""
    success, message, video_path = stop_recording()
    if success:
        video_filename = os.path.basename(video_path)
        return jsonify({"success": True, "message": message, "video_url": url_for("static", filename=f"recordings/{video_filename}")})
    else:
        return jsonify({"success": False, "message": message}), 500


@app.route("/device_status", methods=["GET"])
def device_status_route():
    """Endpoint to get the current recording status."""
    is_recording = get_recording_status()
    if is_recording:
        status_message = "Active: Recording is in progress."
    else:
        status_message = "Idle: Not currently recording."
    return jsonify({"recording": is_recording, "message": status_message})


@app.route("/health_report", methods=["GET"])
def health_report_route():
    """Endpoint to get a system health report."""
    return jsonify(get_health_report())


@app.route("/restart_app", methods=["POST"])
def restart_app_route():
    """Endpoint to restart the Flask application."""
    restart_app()
    return jsonify({"success": True, "message": "Application is restarting."})


@app.route("/restart_system", methods=["POST"])
def restart_system_route():
    """Endpoint to restart the Raspberry Pi."""
    restart_system()
    return jsonify({"success": True, "message": "System is restarting."})


if __name__ == "__main__":
    print("--- Running in development mode ---")
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("Keyboard interrupt received, cleaning up.")
    finally:
        cleanup()