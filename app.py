import datetime
import os
import glob
import threading 
import time
import cv2 
import io 
from flask import Flask, render_template, jsonify, url_for, request, send_file, redirect

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
from common import highlights_controller
from common import replay_controller
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
OUTPUT_DIR_HIGHLIGHTS = "static/highlights_inferences"
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
os.makedirs(OUTPUT_DIR_HIGHLIGHTS, exist_ok=True)
initialize_camera()
# --- End Application Startup ---


# --- Thread target function for running inference ---
def run_inference_task(input_video_path, manual_points=None):
    """
    This function runs in a separate thread for the main Line Calling tab.
    It updates the global 'inference_status' variable.
    """
    global inference_status
    start_time = time.time()
    try:
        filesystem_path = os.path.join(os.getcwd(), input_video_path.lstrip('/'))
        
        if not os.path.exists(filesystem_path):
             raise FileNotFoundError(f"File not found at {filesystem_path}")

        print(f"Starting TFLite inference thread for: {filesystem_path}")
        
        # Generate paths upfront
        base_filename = os.path.basename(filesystem_path)
        tflite_csv_path = os.path.join(OUTPUT_DIR_INFERENCES, f"inferred_{os.path.splitext(base_filename)[0]}.csv")
        
        # --- STAGE 1 & 2: Run TFLite and Homography in parallel ---
        stage1_start = time.time()
        stage2_start = time.time()
        
        inference_status["message"] = "Stage 1/2: Running shuttle tracking and court detection in parallel..."
        
        # Start TFLite inference in a thread
        tflite_result = [None, None, None]  # [success, video_path, csv_path]
        tflite_exception = [None]
        
        def run_tflite():
            try:
                success, vid_path, csv_path = inference_controller.run_inference_on_video(
                    filesystem_path, 
                    OUTPUT_DIR_INFERENCES
                )
                tflite_result[0] = success
                tflite_result[1] = vid_path
                tflite_result[2] = csv_path
            except Exception as e:
                tflite_exception[0] = e
        
        tflite_thread = threading.Thread(target=run_tflite, daemon=True)
        tflite_thread.start()
        
        # Start homography processing in parallel (it will wait for CSV)
        homog_result = [None, None, None, None, None]  # [success, video_path, 2d_full, 2d_zoom, replay]
        homog_exception = [None]
        
        def run_homography():
            try:
                # Wait for TFLite to complete first to ensure CSV is fully written and closed
                tflite_thread.join()
                
                # Small delay to ensure file system has flushed
                time.sleep(0.3)
                
                # Verify CSV exists and is readable
                if not os.path.exists(tflite_csv_path):
                    raise FileNotFoundError(f"CSV file not found: {tflite_csv_path}")
                
                # Try to read CSV to verify it's complete
                try:
                    import pandas as pd
                    test_df = pd.read_csv(tflite_csv_path)
                    if len(test_df) == 0:
                        raise ValueError("CSV file is empty")
                except Exception as e:
                    raise ValueError(f"CSV file is not readable or incomplete: {e}")
                
                # Now run homography with complete CSV
                success, vid_path, full_2d, zoom_2d, replay = homography_controller.run_homography_check(
                    filesystem_path,
                    tflite_csv_path,
                    OUTPUT_DIR_INFERENCES,
                    manual_points=manual_points
                )
                homog_result[0] = success
                homog_result[1] = vid_path
                homog_result[2] = full_2d
                homog_result[3] = zoom_2d
                homog_result[4] = replay
            except Exception as e:
                homog_exception[0] = e
        
        homog_thread = threading.Thread(target=run_homography, daemon=True)
        homog_thread.start()
        
        # Wait for both threads to complete
        tflite_thread.join()
        homog_thread.join()
        
        stage1_time = time.time() - stage1_start
        stage2_time = time.time() - stage2_start
        
        # Check TFLite results
        if tflite_exception[0]:
            raise tflite_exception[0]
        
        success_tflite, tflite_vid_path, tflite_csv_path = tflite_result[0], tflite_result[1], tflite_result[2]
        
        if not success_tflite:
            # Create slow-motion video as fallback
            slowmo_video_path = None
            try:
                slowmo_video_path = homography_controller.create_full_slowmotion_video(
                    filesystem_path,
                    OUTPUT_DIR_INFERENCES,
                    base_filename
                )
                if slowmo_video_path:
                    print(f"✅ Created slow-motion fallback video: {slowmo_video_path}")
            except Exception as slowmo_error:
                print(f"❌ Failed to create slow-motion video: {slowmo_error}")
            
            total_time = time.time() - start_time
            minutes = int(total_time // 60)
            seconds = int(total_time % 60)
            runtime_msg = f"Failed after {minutes}m {seconds}s"
            error_message = f"TFLite inference failed: {tflite_vid_path}. {runtime_msg}"
            if slowmo_video_path:
                error_message += " Showing slow-motion video instead."
            
            inference_status = {
                "status": "error",
                "output_url": slowmo_video_path,
                "output_2d_url": None,
                "output_2d_zoom_url": None,
                "output_replay_url": None,
                "message": error_message
            }
            return

        print(f"--- TFLite step complete. CSV at: {tflite_csv_path} ---")
        print(f"--- TFLite runtime: {stage1_time:.2f}s ---")
        
        # Check homography results
        if homog_exception[0]:
            raise homog_exception[0]
        
        success_homog, final_video_path, final_2d_full_path, final_2d_zoom_path, final_replay_path = (
            homog_result[0], homog_result[1], homog_result[2], homog_result[3], homog_result[4]
        )
        
        print(f"--- Homography runtime: {stage2_time:.2f}s ---")

        if not success_homog:
            # Create slow-motion video as fallback
            slowmo_video_path = None
            try:
                base_filename = os.path.basename(filesystem_path)
                slowmo_video_path = homography_controller.create_full_slowmotion_video(
                    filesystem_path,
                    OUTPUT_DIR_INFERENCES,
                    base_filename
                )
                if slowmo_video_path:
                    print(f"✅ Created slow-motion fallback video: {slowmo_video_path}")
            except Exception as slowmo_error:
                print(f"❌ Failed to create slow-motion video: {slowmo_error}")
            
            total_time = time.time() - start_time
            minutes = int(total_time // 60)
            seconds = int(total_time % 60)
            runtime_msg = f"Failed after {minutes}m {seconds}s"
            error_message = f"Homography check failed: {final_video_path}. {runtime_msg}"
            if slowmo_video_path:
                error_message += " Showing slow-motion video instead."
            
            inference_status = {
                "status": "error",
                "output_url": slowmo_video_path,
                "output_2d_url": None,
                "output_2d_zoom_url": None,
                "output_replay_url": None,
                "message": error_message
            }
            return
        
        total_time = time.time() - start_time
        print(f"--- Homography step complete. IN/OUT determined. ---")
        print(f"--- Homography runtime: {stage2_time:.2f}s ---")
        print(f"--- Total inference runtime: {total_time:.2f}s ({total_time/60:.2f} minutes) ---")

        # --- STAGE 3: Set final status ---
        # Use homography video if available, otherwise fall back to TFLite video
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        runtime_msg = f"Total runtime: {minutes}m {seconds}s"
        output_video = final_video_path if final_video_path else tflite_vid_path
        inference_status = {
            "status": "complete",
            "output_url": output_video,
            "output_2d_url": final_2d_full_path, 
            "output_2d_zoom_url": final_2d_zoom_path,
            "output_replay_url": final_replay_path, 
            "message": f"Line calling process complete. {runtime_msg}"
        }
        print(f"Inference thread finished: {inference_status['status']}")

    except Exception as e:
        total_time = time.time() - start_time
        print(f"❌ Inference thread failed with exception: {e}")
        print(f"--- Failed after {total_time:.2f}s ---")
        
        # Create slow-motion video as fallback (if we have a valid video path)
        slowmo_video_path = None
        try:
            # Check if filesystem_path was defined and file exists
            if 'filesystem_path' in locals() and os.path.exists(filesystem_path):
                base_filename = os.path.basename(filesystem_path)
                slowmo_video_path = homography_controller.create_full_slowmotion_video(
                    filesystem_path,
                    OUTPUT_DIR_INFERENCES,
                    base_filename
                )
                if slowmo_video_path:
                    print(f"✅ Created slow-motion fallback video: {slowmo_video_path}")
            else:
                # Try to use input_video_path directly
                try:
                    filesystem_path_alt = os.path.join(os.getcwd(), input_video_path.lstrip('/'))
                    if os.path.exists(filesystem_path_alt):
                        base_filename = os.path.basename(filesystem_path_alt)
                        slowmo_video_path = homography_controller.create_full_slowmotion_video(
                            filesystem_path_alt,
                            OUTPUT_DIR_INFERENCES,
                            base_filename
                        )
                        if slowmo_video_path:
                            print(f"✅ Created slow-motion fallback video: {slowmo_video_path}")
                except:
                    pass
        except Exception as slowmo_error:
            print(f"❌ Failed to create slow-motion video: {slowmo_error}")
        
        minutes = int(total_time // 60)
        seconds = int(total_time % 60)
        runtime_msg = f"Failed after {minutes}m {seconds}s"
        error_message = f"{str(e)}. {runtime_msg}"
        if slowmo_video_path:
            error_message += " Showing slow-motion video instead."
        
        inference_status = {
            "status": "error",
            "output_url": slowmo_video_path,
            "output_2d_url": None, 
            "output_2d_zoom_url": None,
            "output_replay_url": None, 
            "message": error_message
        }


# --- Page Rendering Routes ---
@app.route("/")
def index():
    # Redirect root URL to Record Match page (Making it the main tab)
    return redirect(url_for('record_match_page'))

@app.route("/record_match")
def record_match_page():
    return render_template("record_match.html")

@app.route("/system")
def system_page():
    # Renders the old index.html as the System/Controls page
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
        # Attempt to undistort immediately
        u_success, u_msg, u_path = calibration_controller.undistort_image(filepath)
        if u_success:
            final_filename = os.path.basename(u_path)
            message += " (Undistorted)"
            return jsonify({"success": True, "message": message, "image_url": url_for("static", filename=f"captures/{final_filename}")})
        else:
            message += f" (Distorted - {u_msg})"
            return jsonify({"success": True, "message": message, "image_url": url_for("static", filename=f"captures/{filename}")})
    else:
        return jsonify({"success": False, "message": message}), 500

@app.route("/start_recording", methods=["POST"])
def start_recording_route():
    # Extract JSON data if available
    data = request.get_json(silent=True)
    
    # Base timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Construct filename based on match details
    if data and 'type' in data:
        match_type = data['type'] # 'singles' or 'doubles'
        players = data.get('players', [])
        
        # Sanitize names (replace spaces with underscores, keep only alphanumeric)
        safe_players = ["".join(c for c in p if c.isalnum() or c in (' ', '_')).replace(' ', '_') for p in players]
        
        if match_type == 'singles' and len(safe_players) >= 2:
            filename = f"match_{timestamp}_Singles_{safe_players[0]}_vs_{safe_players[1]}{VIDEO_EXTENSION}"
        elif match_type == 'doubles' and len(safe_players) >= 4:
            filename = f"match_{timestamp}_Doubles_{safe_players[0]}_{safe_players[1]}_vs_{safe_players[2]}_{safe_players[3]}{VIDEO_EXTENSION}"
        else:
            filename = f"match_{timestamp}_{match_type}{VIDEO_EXTENSION}"
    else:
        # Fallback for manual or legacy calls
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
        # Attempt to undistort immediately
        u_success, u_msg, u_filename = calibration_controller.undistort_video(video_path, output_dir=OUTPUT_DIR_VIDEOS)
        if u_success:
            message += " (Undistorted)"
            return jsonify({"success": True, "message": message, "video_url": url_for("static", filename=f"recordings/{u_filename}")})
        else:
            message += f" (Distorted - {u_msg})"
            video_filename = os.path.basename(video_path)
            return jsonify({"success": True, "message": message, "video_url": url_for("static", filename=f"recordings/{video_filename}")})
    else:
        return jsonify({"success": False, "message": message}), 500

@app.route("/create_instant_replay", methods=["POST"])
def create_instant_replay_route():
    # Use the existing 'static/recordings' folder for replays too, or a subfolder
    REPLAY_DIR = "static/recordings/replays"
    
    success, message, replay_path = replay_controller.create_instant_replay(REPLAY_DIR, duration=30)
    
    if success:
        # Convert filesystem path to web URL
        # Path is likely static/recordings/replays/replay_xxxx.mp4
        filename = os.path.basename(replay_path)
        return jsonify({
            "success": True, 
            "message": message, 
            "video_url": url_for('static', filename=f'recordings/replays/{filename}')
        })
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
        video_filename = os.path.basename(video_path)
        return jsonify({"success": True, "message": message, "video_url": url_for("static", filename=f"line_calls/{video_filename}")})
    else:
        return jsonify({"success": False, "message": message}), 500


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

# --- Route to get a specific frame from a video ---
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


# --- Route to run inference (now accepts manual points) ---
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

    inference_status = {"status": "running", "output_url": None, "output_2d_url": None, "output_2d_zoom_url": None, "output_replay_url": None, "message": "Process starting..."}
    # Pass manual_points to the thread
    thread = threading.Thread(target=run_inference_task, args=(input_path, manual_points), daemon=True)
    thread.start()
    
    return jsonify({"success": True, "message": "Inference process started."})

@app.route("/check_inference_status", methods=["GET"])
def check_inference_status_route():
    """Polls for the status of the running inference job."""
    global inference_status
    
    status_copy = inference_status.copy()

    # Convert URLs for both complete and error status (error may have slow-motion fallback video)
    if status_copy["status"] in ["complete", "error"]:
        def normalize_static_url(path):
            if not path:
                return None
            if isinstance(path, str) and (path.startswith("http://") or path.startswith("https://")):
                return path
            normalized = path.lstrip("/") if isinstance(path, str) else path
            if isinstance(normalized, str) and normalized.startswith("static/"):
                normalized = normalized[len("static/"):]
            return url_for("static", filename=normalized)

        if status_copy.get("output_url"):
            status_copy["output_url"] = normalize_static_url(status_copy["output_url"])
        if status_copy.get("output_2d_url"):
            status_copy["output_2d_url"] = normalize_static_url(status_copy["output_2d_url"])
        if status_copy.get("output_2d_zoom_url"):
            status_copy["output_2d_zoom_url"] = normalize_static_url(status_copy["output_2d_zoom_url"])
        if status_copy.get("output_replay_url"):
            status_copy["output_replay_url"] = normalize_static_url(status_copy["output_replay_url"])
            
    return jsonify(status_copy)


# --- NEW: Highlights Processing API (Upload) ---
@app.route("/api/process_highlights", methods=["POST"])
def process_highlights_route():
    if 'video' not in request.files:
        return jsonify({"success": False, "message": "No video uploaded"}), 400
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file"}), 400

    # 1. Save uploaded video
    filename = file.filename
    upload_path = os.path.join(OUTPUT_DIR_UPLOADS, filename)
    file.save(upload_path)

    try:
        # 2. Run TFLite inference (Ball Tracking) to get CSV data
        # We pass OUTPUT_DIR_HIGHLIGHTS so all derived files go there
        success, vid_path, csv_path = inference_controller.run_inference_on_video(
            upload_path, 
            OUTPUT_DIR_HIGHLIGHTS 
        )
        
        if not success:
            return jsonify({"success": False, "message": "Tracking failed: " + vid_path}), 500

        # 3. Generate Highlights using the CSV and Video
        success, files = highlights_controller.generate_highlights(
            upload_path, 
            csv_path, 
            OUTPUT_DIR_HIGHLIGHTS
        )
        
        if not success:
             return jsonify({"success": False, "message": "Highlight generation failed."}), 500

        # Convert file paths to URLs for the frontend
        file_urls = {}
        for key, path in files.items():
            filename = os.path.basename(path)
            # IMPORTANT: We now look in the highlights folder
            file_urls[key] = url_for('static', filename=f'highlights_inferences/{filename}')

        return jsonify({"success": True, "files": file_urls})

    except Exception as e:
        print(f"Error in highlights route: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


# --- NEW: Process Highlights from Existing File (For Record Match Tab) ---
@app.route("/api/process_highlights_from_path", methods=["POST"])
def process_highlights_from_path_route():
    data = request.get_json()
    video_url = data.get('video_path') # This will be the web URL like /static/recordings/...
    
    if not video_url:
        return jsonify({"success": False, "message": "No video path provided"}), 400

    # Convert web URL to filesystem path
    # Remove leading slash and URL prefix to get relative path
    # e.g. "/static/recordings/video.mp4" -> "static/recordings/video.mp4"
    rel_path = video_url.lstrip('/')
    filesystem_path = os.path.join(os.getcwd(), rel_path)
    
    if not os.path.exists(filesystem_path):
        return jsonify({"success": False, "message": f"File not found: {filesystem_path}"}), 404

    try:
        # 1. Run TFLite inference to get CSV data
        success, vid_path, csv_path = inference_controller.run_inference_on_video(
            filesystem_path, 
            OUTPUT_DIR_HIGHLIGHTS 
        )
        
        if not success:
            return jsonify({"success": False, "message": "Tracking failed: " + vid_path}), 500

        # 2. Generate Highlights
        success, files = highlights_controller.generate_highlights(
            filesystem_path, 
            csv_path, 
            OUTPUT_DIR_HIGHLIGHTS
        )
        
        if not success:
             return jsonify({"success": False, "message": "Highlight generation failed."}), 500

        # 3. Return URLs
        file_urls = {}
        for key, path in files.items():
            filename = os.path.basename(path)
            file_urls[key] = url_for('static', filename=f'highlights_inferences/{filename}')

        return jsonify({"success": True, "files": file_urls})

    except Exception as e:
        print(f"Error in highlights route: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


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