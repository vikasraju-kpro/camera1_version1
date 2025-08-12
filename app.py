import datetime
import os
import glob
from flask import Flask, render_template, jsonify, url_for, request

from common.camera_controller import (
    initialize_camera,
    capture_image,
    start_recording,
    stop_recording,
    cleanup,
    get_recording_status,
)
from common import calibration_controller
from common.system_controller import restart_app, restart_system
from utils.health_check import get_health_report
from utils.device_info import get_device_uuid, get_device_name

app = Flask(__name__)

# --- Configuration ---
OUTPUT_DIR_IMAGES = "static/captures"
OUTPUT_DIR_VIDEOS = "static/recordings"
OUTPUT_DIR_CALIB_IMAGES = "static/calibration_images"
OUTPUT_DIR_UPLOADS = "static/uploads"
CALIB_DATA_DIR = "calibration_data"
IMAGE_EXTENSION = ".jpg"
VIDEO_EXTENSION = ".mp4"

# --- Application Startup ---
print("--- Initializing Application ---")
os.makedirs(OUTPUT_DIR_IMAGES, exist_ok=True)
os.makedirs(OUTPUT_DIR_VIDEOS, exist_ok=True)
os.makedirs(OUTPUT_DIR_CALIB_IMAGES, exist_ok=True)
os.makedirs(OUTPUT_DIR_UPLOADS, exist_ok=True)
os.makedirs(CALIB_DATA_DIR, exist_ok=True)
initialize_camera()
# --- End Application Startup ---


@app.route("/")
def index():
    """Renders the main HTML page."""
    return render_template("index.html")


@app.route("/calibration")
def calibration_page():
    """Renders the calibration HTML page."""
    return render_template("calibration.html")


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


@app.route("/capture_for_calibration", methods=["POST"])
def capture_for_calibration_route():
    """Captures an image, checks for a checkerboard, and returns the result."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"calib_{timestamp}{IMAGE_EXTENSION}"
    filepath = os.path.join(OUTPUT_DIR_CALIB_IMAGES, filename)
    
    capture_success, message = capture_image(filepath)
    if not capture_success:
        return jsonify({"success": False, "message": message}), 500

    found, message, image_path = calibration_controller.find_checkerboard_in_image(filepath)
    
    image_filename = os.path.basename(image_path)
    image_url = url_for('static', filename=f'calibration_images/{image_filename}')

    return jsonify({
        "success": found,
        "message": message,
        "preview_url": image_url
    })


@app.route("/get_calibration_status", methods=["GET"])
def get_calibration_status_route():
    """Returns the number of successfully captured calibration images."""
    previews = glob.glob(os.path.join(OUTPUT_DIR_CALIB_IMAGES, '*_preview.jpg'))
    image_count = len(previews)
    return jsonify({
        "image_count": image_count,
        "min_required": calibration_controller.MIN_IMAGES_REQUIRED,
        "is_ready": image_count >= calibration_controller.MIN_IMAGES_REQUIRED
    })


@app.route("/run_calibration", methods=["POST"])
def run_calibration_route():
    """Triggers the calibration process and returns a JSON response."""
    success, message = calibration_controller.run_calibration_process()
    return jsonify({"success": success, "message": message})


@app.route("/upload_and_undistort", methods=["POST"])
def upload_and_undistort_route():
    """
    Handles video upload, performs full undistortion for web playback, and returns a video URL.
    """
    if 'video' not in request.files:
        return jsonify({"success": False, "message": "No video file provided."}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file."}), 400

    upload_path = os.path.join(OUTPUT_DIR_UPLOADS, file.filename)
    file.save(upload_path)
    
    success, message, result_filename = calibration_controller.undistort_video(upload_path)
    
    if success:
        return jsonify({
            "success": True,
            "message": message,
            "video_url": url_for('static', filename=f'uploads/{result_filename}')
        })
    else:
        return jsonify({"success": False, "message": message}), 500


@app.route("/quick_undistort_and_download", methods=["POST"])
def quick_undistort_route():
    """
    Handles video upload, performs fast undistortion, and returns a download link.
    """
    if 'video' not in request.files:
        return jsonify({"success": False, "message": "No video file provided."}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file."}), 400

    upload_path = os.path.join(OUTPUT_DIR_UPLOADS, file.filename)
    file.save(upload_path)
    
    success, message, result_filename = calibration_controller.quick_undistort_video(upload_path)
    
    if success:
        return jsonify({
            "success": True,
            "message": message,
            "download_url": url_for('static', filename=f'uploads/{result_filename}')
        })
    else:
        return jsonify({"success": False, "message": message}), 500


@app.route("/device_status", methods=["GET"])
def device_status_route():
    """Endpoint to get the current recording status, device name, and device_id."""
    is_recording = get_recording_status()
    if is_recording:
        status_message = "Active: Recording is in progress."
    else:
        status_message = "Idle: Not currently recording."
    
    return jsonify({
        "name": get_device_name(),
        "device_id": get_device_uuid(), 
        "recording": is_recording, 
        "message": status_message
    })


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
    return jsonify({
        "success": True, 
        "message": "System is restarting.",
        "device_id": get_device_uuid() 
    })


if __name__ == "__main__":
    print("--- Running in development mode ---")
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("Keyboard interrupt received, cleaning up.")
    finally:
        cleanup()