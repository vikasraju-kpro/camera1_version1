import datetime
import os
import glob
import threading 
import cv2 # <-- NEW
import io # <-- NEW
import time
from flask import Flask, render_template, jsonify, url_for, request, send_file, send_file

from common.camera_controller import (
    initialize_camera,
    capture_image,
    start_recording,
    stop_recording,
    cleanup,
    get_recording_status,
)
from common import calibration_controller
from common import file_manager 
from common import inference_controller
from common import homography_controller 
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
OUTPUT_DIR_LINE_CALLS = "static/line_calls"
OUTPUT_DIR_INFERENCES = "static/line_call_inferences" 
IMAGE_EXTENSION = ".jpg"
VIDEO_EXTENSION = ".mp4"
DELETE_PIN = "kpro" 

# --- Global variable for tracking inference task ---
inference_status = {
    "status": "idle", # "idle", "running", "complete", "error"
    "output_url": None,
    "output_2d_url": None, 
    "output_2d_zoom_url": None,
    "output_replay_url": None, 
    "message": None
}

# --- Application Startup ---
print("--- Initializing Application ---")
os.makedirs(OUTPUT_DIR_IMAGES, exist_ok=True)
os.makedirs(OUTPUT_DIR_VIDEOS, exist_ok=True)
os.makedirs(OUTPUT_DIR_CALIB_IMAGES, exist_ok=True)
os.makedirs(OUTPUT_DIR_UPLOADS, exist_ok=True)
os.makedirs(CALIB_DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR_LINE_CALLS, exist_ok=True)
os.makedirs(OUTPUT_DIR_INFERENCES, exist_ok=True)
initialize_camera()
# --- End Application Startup ---


# --- MODIFIED: Thread target function for running inference ---
def run_inference_task(input_video_path, manual_points=None):
    """
    This function runs in a separate thread.
    It updates the global 'inference_status' variable.
    It now accepts optional manual_points.
    """
    global inference_status
    try:
        start_time = time.time()
        filesystem_path = os.path.join(os.getcwd(), input_video_path.lstrip('/'))
        # Derive a path relative to the Flask static folder so the frontend can render it if needed
        static_relative_input_path = None
        if input_video_path.startswith("/static/"):
            static_relative_input_path = input_video_path[len("/static/"):]
        elif input_video_path.startswith("static/"):
            static_relative_input_path = input_video_path[len("static/"):]
        else:
            try:
                # Best-effort: compute relative path to static directory if possible
                static_dir = os.path.join(os.getcwd(), "static")
                static_relative_input_path = os.path.relpath(filesystem_path, static_dir)
            except Exception:
                static_relative_input_path = None
        
        if not os.path.exists(filesystem_path):
             raise FileNotFoundError(f"File not found at {filesystem_path}")

        print(f"Starting TFLite inference thread for: {filesystem_path}")
        
        # --- STAGE 1: Run TFLite Shuttle Tracking ---
        inference_status["stage"] = 1
        inference_status["stage_name"] = "Running shuttle tracking"
        inference_status["message"] = "Stage 1/2: Running shuttle tracking..."
        success_tflite, tflite_vid_path, tflite_csv_path = inference_controller.run_inference_on_video(
            filesystem_path, 
            OUTPUT_DIR_INFERENCES
        )

        if not success_tflite:
            raise Exception(f"TFLite inference failed: {tflite_vid_path}")

        print(f"--- TFLite step complete. CSV at: {tflite_csv_path} ---")
        print(f"--- Starting YOLO Homography step... ---")
        # Log elapsed so far
        try:
            so_far = time.time() - start_time
            print(f"⏱️ Stage 1/2 time elapsed so far: {so_far:.2f}s")
        except Exception:
            pass
        
        # --- STAGE 2: Run YOLO Homography ---
        inference_status["stage"] = 2
        inference_status["stage_name"] = "Running court detection"
        inference_status["message"] = "Stage 2/2: Running court detection..."
        success_homog, final_video_path, final_2d_full_path, final_2d_zoom_path, final_replay_path = homography_controller.run_homography_check(
            filesystem_path,     
            tflite_csv_path,     
            OUTPUT_DIR_INFERENCES,
            manual_points=manual_points # <-- Pass manual points
        )

        if not success_homog:
            raise Exception(f"Homography check failed: {final_video_path}")
        
        print(f"--- Homography step complete. Final video at: {final_video_path} ---")

        # --- STAGE 3: Set final status ---
        total_time = time.time() - start_time
        print(f"⏱️ Total inference time: {total_time:.2f}s")
        inference_status = {
            "status": "complete",
            "output_url": final_video_path,       
            "output_2d_url": final_2d_full_path, 
            "output_2d_zoom_url": final_2d_zoom_path,
            "output_replay_url": final_replay_path, 
            "message": "Line calling process complete.",
            "run_time_seconds": round(total_time, 2)
        }
        print(f"Inference thread finished: {inference_status['status']}")

    except Exception as e:
        print(f"❌ Inference thread failed with exception: {e}")
        # Fallback behavior: for no-hit / no-landing-point style failures, return the original clip
        err_lower = str(e).lower()
        fallback_phrases = [
            "no hits", 
            "no detections", 
            "homography check failed",
            "no valid landing point",
            "no landing point",
            "cannot determine in/out",
            "cannot determine in / out"
        ]
        should_fallback = any(p in err_lower for p in fallback_phrases)
        if should_fallback and static_relative_input_path:
            total_time = time.time() - start_time
            print("⚠️ No valid result from inference. Falling back to original input clip.")
            print(f"⏱️ Total inference time (fallback): {total_time:.2f}s")
            inference_status = {
                "status": "complete",
                "output_url": static_relative_input_path,
                "output_2d_url": None, 
                "output_2d_zoom_url": None,
                "output_replay_url": None, 
                "message": "No valid result from inference. Showing original clip.",
                "run_time_seconds": round(total_time, 2)
            }
        else:
            total_time = time.time() - start_time
            inference_status = {
                "status": "error",
                "output_url": None,
                "output_2d_url": None, 
                "output_2d_zoom_url": None,
                "output_replay_url": None, 
                "message": str(e),
                "run_time_seconds": round(total_time, 2)
            }


# --- Page Rendering Routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/calibration")
def calibration_page():
    return render_template("calibration.html")

@app.route("/files")
def file_explorer_page():
    return render_template("file_explorer.html")

@app.route("/line_calling")
def line_calling_page():
    return render_template("line_calling.html")


# --- Camera Control Routes ---
@app.route("/capture_image", methods=["POST"])
def capture_image_route():
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
    success, message, video_path = stop_recording()
    if success:
        video_filename = os.path.basename(video_path)
        return jsonify({"success": True, "message": message, "video_url": url_for("static", filename=f"recordings/{video_filename}")})
    else:
        return jsonify({"success": False, "message": message}), 500

@app.route("/start_line_calling", methods=["POST"])
def start_line_calling_route():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"line_call_{timestamp}{VIDEO_EXTENSION}"
    filepath = os.path.join(OUTPUT_DIR_LINE_CALLS, filename)
    success, message = start_recording(filepath)
    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "message": message}), 500

@app.route("/stop_line_calling", methods=["POST"])
def stop_line_calling_route():
    success, message, video_path = stop_recording()
    if success:
        # Try to undistort the recorded video using existing calibration
        try:
            undist_success, undist_msg, undist_filename = calibration_controller.undistort_video(
                video_path, output_dir=OUTPUT_DIR_LINE_CALLS
            )
            if undist_success and undist_filename:
                return jsonify({
                    "success": True,
                    "message": f"{message} {undist_msg}",
                    "video_url": url_for("static", filename=f"line_calls/{undist_filename}")
                })
            else:
                # Fallback to original if undistortion failed or calibration missing
                video_filename = os.path.basename(video_path)
                return jsonify({
                    "success": True,
                    "message": f"{message} (Undistort skipped: {undist_msg})",
                    "video_url": url_for("static", filename=f"line_calls/{video_filename}")
                })
        except Exception as e:
            # Robust fallback on unexpected errors
            video_filename = os.path.basename(video_path)
            return jsonify({
                "success": True,
                "message": f"{message} (Undistort error: {str(e)})",
                "video_url": url_for("static", filename=f"line_calls/{video_filename}")
            })
    else:
        return jsonify({"success": False, "message": message}), 500


# --- NEW: Upload a video and treat it as a recorded line-calling clip ---
@app.route("/upload_line_call", methods=["POST"])
def upload_line_call_route():
    if 'video' not in request.files:
        return jsonify({"success": False, "message": "No video file provided."}), 400
    file = request.files['video']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file."}), 400
    # Save into line_calls directory with a timestamped filename to avoid collisions
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.splitext(file.filename)[0]
    save_name = f"{base_name}_{timestamp}{VIDEO_EXTENSION}" if not file.filename.lower().endswith(VIDEO_EXTENSION) else f"{base_name}_{timestamp}{VIDEO_EXTENSION}"
    save_path = os.path.join(OUTPUT_DIR_LINE_CALLS, save_name)
    file.save(save_path)
    return jsonify({
        "success": True,
        "message": "Video uploaded as recording.",
        "video_url": url_for("static", filename=f"line_calls/{save_name}")
    })


# --- Calibration and Undistortion Routes ---
@app.route("/capture_for_calibration", methods=["POST"])
def capture_for_calibration_route():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"calib_{timestamp}{IMAGE_EXTENSION}"
    filepath = os.path.join(OUTPUT_DIR_CALIB_IMAGES, filename)
    capture_success, message = capture_image(filepath)
    if not capture_success:
        return jsonify({"success": False, "message": message}), 500
    found, message, image_path = calibration_controller.find_checkerboard_in_image(filepath)
    image_filename = os.path.basename(image_path)
    image_url = url_for('static', filename=f'calibration_images/{image_filename}')
    return jsonify({"success": found, "message": message, "preview_url": image_url})

@app.route("/get_calibration_status", methods=["GET"])
def get_calibration_status_route():
    previews = glob.glob(os.path.join(OUTPUT_DIR_CALIB_IMAGES, '*_preview.jpg'))
    image_count = len(previews)
    return jsonify({"image_count": image_count, "min_required": calibration_controller.MIN_IMAGES_REQUIRED, "is_ready": image_count >= calibration_controller.MIN_IMAGES_REQUIRED})

@app.route("/run_calibration", methods=["POST"])
def run_calibration_route():
    success, message = calibration_controller.run_calibration_process()
    return jsonify({"success": success, "message": message})

@app.route("/upload_and_undistort", methods=["POST"])
def upload_and_undistort_route():
    if 'video' not in request.files: return jsonify({"success": False, "message": "No video file provided."}), 400
    file = request.files['video']
    if file.filename == '': return jsonify({"success": False, "message": "No selected file."}), 400
    upload_path = os.path.join(OUTPUT_DIR_UPLOADS, file.filename)
    file.save(upload_path)
    success, message, result_filename = calibration_controller.undistort_video(upload_path)
    if success:
        return jsonify({"success": True, "message": message, "video_url": url_for('static', filename=f'uploads/{result_filename}')})
    else:
        return jsonify({"success": False, "message": message}), 500

@app.route("/quick_undistort_and_download", methods=["POST"])
def quick_undistort_route():
    if 'video' not in request.files: return jsonify({"success": False, "message": "No video file provided."}), 400
    file = request.files['video']
    if file.filename == '': return jsonify({"success": False, "message": "No selected file."}), 400
    upload_path = os.path.join(OUTPUT_DIR_UPLOADS, file.filename)
    file.save(upload_path)
    success, message, result_filename = calibration_controller.quick_undistort_video(upload_path)
    if success:
        return jsonify({"success": True, "message": message, "download_url": url_for('static', filename=f'uploads/{result_filename}')})
    else:
        return jsonify({"success": False, "message": message}), 500


# --- Routes for TFLite Inference ---
@app.route("/upload_for_inference", methods=["POST"])
def upload_for_inference_route():
    """Handles video upload for inference."""
    if 'video' not in request.files:
        return jsonify({"success": False, "message": "No video file provided."}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file."}), 400

    upload_path = os.path.join(OUTPUT_DIR_UPLOADS, file.filename)
    file.save(upload_path)
    
    input_url = url_for('static', filename=f'uploads/{file.filename}')
    return jsonify({"success": True, "message": "File uploaded.", "input_path": input_url})

# --- NEW: Route to get a specific frame from a video ---
@app.route("/get_video_frame", methods=["POST"])
def get_video_frame_route():
    try:
        data = request.get_json()
        video_path = data.get('video_path')
        frame_number = int(data.get('frame_number', 0))

        if not video_path:
            return jsonify({"success": False, "message": "No video_path provided."}), 400
        
        filesystem_path = os.path.join(os.getcwd(), video_path.lstrip('/'))
        if not os.path.exists(filesystem_path):
            return jsonify({"success": False, "message": "Video file not found."}), 404
        
        cap = cv2.VideoCapture(filesystem_path)
        if not cap.isOpened():
            return jsonify({"success": False, "message": "Could not open video file."}), 500
        
        # Set the frame position
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return jsonify({"success": False, "message": "End of video or invalid frame."}), 404
        
        # Get frame dimensions
        height, width, _ = frame.shape

        # Encode frame as JPEG and send it
        _, buffer = cv2.imencode('.jpg', frame)
        img_io = io.BytesIO(buffer)
        
        # We need to send the image, but also return JSON.
        # The best way is to save a temp frame and return the path.
        frame_filename = f"temp_frame_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S%f')}.jpg"
        frame_fs_path = os.path.join(OUTPUT_DIR_INFERENCES, frame_filename)
        cv2.imwrite(frame_fs_path, frame)
        
        frame_web_path = os.path.join(os.path.basename(OUTPUT_DIR_INFERENCES), frame_filename)
        
        return jsonify({
            "success": True,
            "image_url": url_for('static', filename=frame_web_path),
            "width": width,
            "height": height
        })

    except Exception as e:
        print(f"❌ Error in /get_video_frame: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# --- MODIFIED: Route to run inference (now accepts manual points) ---
@app.route("/run_inference", methods=["POST"])
def run_inference_route():
    """Starts the inference process in a background thread."""
    global inference_status
    if inference_status["status"] == "running":
        return jsonify({"success": False, "message": "An inference job is already running."}), 400

    data = request.get_json()
    input_path = data.get('input_path')
    manual_points = data.get('manual_points') # Will be None if not provided

    if not input_path:
        return jsonify({"success": False, "message": "No input_path provided."}), 400
    
    if manual_points:
        print(f"Received manual points: {manual_points}")
    else:
        print("No manual points, running in Auto-mode.")

    import time as _time
    inference_status = {
        "status": "running",
        "output_url": None,
        "output_2d_url": None,
        "output_2d_zoom_url": None,
        "output_replay_url": None,
        "message": "Process starting...",
        "started_at": _time.time(),
        "stage": 0,
        "stage_name": None,
    }
    # Pass manual_points to the thread
    thread = threading.Thread(target=run_inference_task, args=(input_path, manual_points), daemon=True)
    thread.start()
    
    return jsonify({"success": True, "message": "Inference process started."})

@app.route("/check_inference_status", methods=["GET"])
def check_inference_status_route():
    """Polls for the status of the running inference job."""
    global inference_status
    
    status_copy = inference_status.copy()

    # Live update the stage message to include elapsed seconds so far
    if status_copy.get("status") == "running":
        try:
            import time as _time
            elapsed = None
            if status_copy.get("started_at"):
                elapsed = int(_time.time() - status_copy["started_at"])
            stage = status_copy.get("stage")
            stage_name = status_copy.get("stage_name")
            if stage in (1, 2) and stage_name and elapsed is not None:
                status_copy["message"] = f"Stage {stage}/2: {stage_name}... (elapsed {elapsed}s)"
        except Exception:
            pass

    if status_copy["status"] == "complete":
        if status_copy.get("output_url"):
            status_copy["output_url"] = url_for('static', filename=status_copy["output_url"])
        if status_copy.get("output_2d_url"):
            status_copy["output_2d_url"] = url_for('static', filename=status_copy["output_2d_url"])
        if status_copy.get("output_2d_zoom_url"):
            status_copy["output_2d_zoom_url"] = url_for('static', filename=status_copy["output_2d_zoom_url"])
        if status_copy.get("output_replay_url"):
            status_copy["output_replay_url"] = url_for('static', filename=status_copy["output_replay_url"])
            
    return jsonify(status_copy)


# --- System and Health Routes ---
@app.route("/device_status", methods=["GET"])
def device_status_route():
    is_recording = get_recording_status()
    status_message = "Active: Recording is in progress." if is_recording else "Idle: Not currently recording."
    return jsonify({"name": get_device_name(), "device_id": get_device_uuid(), "recording": is_recording, "message": status_message})

@app.route("/health_report", methods=["GET"])
def health_report_route():
    return jsonify(get_health_report())


# --- API Endpoints for File Explorer ---
@app.route("/api/files", methods=["GET"])
def get_files_route():
    return jsonify(file_manager.get_file_list())

@app.route('/api/download_zip', methods=['GET', 'POST'])
def download_zip_route():
    files_to_zip = []
    zip_filename = "archive.zip"
    all_files_data = file_manager.get_file_list()
    if request.method == 'GET':
        download_type = request.args.get('type')
        if download_type == 'all_images':
            files_to_zip = [f['path'] for f in all_files_data['images']]
            zip_filename = "all_images.zip"
        elif download_type == 'all_videos':
            files_to_zip = [f['path'] for f in all_files_data['videos']]
            zip_filename = "all_videos.zip"
    else: 
        data = request.get_json()
        files_to_zip = data.get('files', [])
        image_count = sum(1 for f in files_to_zip if 'captures' in f)
        video_count = len(files_to_zip) - image_count
        file_type = "images" if image_count > video_count else "videos"
        zip_filename = f"selected_{file_type}.zip"
    if not files_to_zip:
        return jsonify({"success": False, "message": "No files found for zipping."}), 400
    zip_path = file_manager.create_zip_archive(files_to_zip, zip_filename)
    return send_file(zip_path, as_attachment=True)

@app.route('/api/delete_files', methods=['POST'])
def delete_files_route():
    data = request.get_json()
    files_to_delete = data.get('files', [])
    submitted_pin = data.get('pin')
    if submitted_pin != DELETE_PIN:
        return jsonify({"success": False, "message": "❌ Invalid PIN. Deletion denied."}), 403 
    if not files_to_delete:
        return jsonify({"success": False, "message": "No files selected for deletion."}), 400
    deleted_count, errors = file_manager.delete_selected_files(files_to_delete)
    if errors:
        message = f"Completed with errors. Deleted {deleted_count} file(s). Errors: {'; '.join(errors)}"
        return jsonify({"success": False, "message": message}), 500
    return jsonify({"success": True, "message": f"✅ Successfully deleted {deleted_count} file(s)."})


# --- System Control Routes ---
@app.route("/restart_app", methods=["POST"])
def restart_app_route():
    restart_app()
    return jsonify({"success": True, "message": "Application is restarting."})

@app.route("/restart_system", methods=["POST"])
def restart_system_route():
    restart_system()
    return jsonify({"success": True, "message": "System is restarting.", "device_id": get_device_uuid()})


# --- Main Execution ---
if __name__ == "__main__":
    print("--- Running in development mode ---")
    try:
        app.run(host="0.0.0.0", port=5000, debug=True, threaded=True, use_reloader=False)
    except KeyboardInterrupt:
        print("Keyboard interrupt received, cleaning up.")
    finally:
        cleanup()