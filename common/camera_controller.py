import os
import threading
import time
import subprocess
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder

# --- Camera Configuration ---
FISHEYE_CAM_ID = 0
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FRAMERATE = 47.57

# --- Global Variables ---
picam = None
recording_active = False
recording_thread = None
stop_recording_event = threading.Event()
output_path = None # Final .mp4 path
temp_raw_path = None # Temporary .h264 path
lock = threading.Lock()


def get_recording_status():
    """Safely returns the current recording status."""
    with lock:
        return recording_active


def initialize_camera():
    """Initializes and configures the fisheye camera with the desired framerate."""
    global picam
    print("--- Initializing Fisheye Camera ---")
    try:
        picam = Picamera2(camera_num=FISHEYE_CAM_ID)
        # Create a configuration with the specified resolution and framerate
        config = picam.create_video_configuration(
            main={"size": (VIDEO_WIDTH, VIDEO_HEIGHT)},
            controls={"FrameRate": VIDEO_FRAMERATE}
        )
        picam.configure(config)
        picam.start()
        time.sleep(2.0)
        print(f"Fisheye camera started successfully at {VIDEO_FRAMERATE} FPS.")
        return True
    except Exception as e:
        print(f"ERROR: Failed to initialize camera: {e}")
        return False


def capture_image(filepath):
    """Captures a single still image and saves it."""
    global picam
    with lock:
        if recording_active:
            return False, "Recording is currently active."
        if not picam or not picam.started:
            return False, "Camera is not ready."

        try:
            # Picamera2 handles the color conversion correctly for still captures.
            picam.capture_file(filepath)
            print(f"Image saved to {filepath}")
            return True, "Image captured successfully."
        except Exception as e:
            print(f"ERROR: Failed to capture image: {e}")
            return False, f"Failed to capture image: {e}"


def _record_video_loop():
    """
    A simple thread target that just waits for the stop signal.
    The actual recording is handled by the Picamera2 encoder in the background.
    """
    print("Recording thread started. Waiting for stop signal...")
    stop_recording_event.wait() # This will block until stop_recording() is called
    print("Recording thread finished.")


def start_recording(filepath):
    """Starts recording a raw H264 stream to a temporary file."""
    global recording_active, recording_thread, stop_recording_event
    global output_path, temp_raw_path

    with lock:
        if recording_active:
            return False, "A recording is already in progress."
        if not picam or not picam.started:
            return False, "Camera is not ready."

        try:
            # Set up file paths
            output_path = filepath
            # Create a temporary filename for the raw stream
            temp_raw_path = filepath.replace('.mp4', '.h264')

            encoder = H264Encoder()
            stop_recording_event.clear()
            
            # Start the encoder. This is a non-blocking call.
            picam.start_encoder(encoder, output=temp_raw_path)
            
            recording_active = True
            recording_thread = threading.Thread(target=_record_video_loop, daemon=True)
            recording_thread.start()
            
            print(f"Started raw recording to {temp_raw_path}")
            return True, "Video recording started."
        except Exception as e:
            print(f"ERROR starting raw recording: {e}")
            return False, f"Failed to start recording: {e}"


def stop_recording():
    """Stops the H264 recording and converts the raw file to a playable MP4."""
    global recording_active, recording_thread, stop_recording_event, output_path, temp_raw_path

    with lock:
        if not recording_active:
            return False, "No active recording to stop.", None
        print("Stopping raw recording...")
        
        # Stop the encoder first
        picam.stop_encoder()
        
        # Signal the waiting thread to exit
        stop_recording_event.set()
        recording_active = False

    if recording_thread:
        recording_thread.join(timeout=2) # Wait for the thread to finish

    print(f"\nConverting {temp_raw_path} to {output_path}...")
    
    # Construct the ffmpeg command to repackage the raw stream into an MP4
    command = [
        'ffmpeg',
        '-y',                         # Overwrite output file if it exists
        '-framerate', str(VIDEO_FRAMERATE), # Tell ffmpeg the input stream's FPS
        '-i', temp_raw_path,
        '-c:v', 'copy',               # Copy the video stream without re-encoding
        '-r', str(VIDEO_FRAMERATE),   # Explicitly set the output file's FPS metadata
        output_path
    ]

    try:
        # Run the ffmpeg command
        subprocess.run(command, check=True)
        print("✅ Conversion successful!")
        
        # --- Clean up the temporary raw file ---
        print(f"Removing temporary file: {temp_raw_path}")
        os.remove(temp_raw_path)

        return True, "Video recording stopped and file converted.", output_path

    except FileNotFoundError:
        print("❌ ERROR: ffmpeg is not installed or not in your PATH.")
        return False, "ffmpeg not found. Cannot convert video.", None
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: ffmpeg conversion failed with error: {e}")
        return False, "Video conversion failed.", None


def cleanup():
    """Stops the camera and cleans up resources."""
    global picam
    print("--- Performing cleanup ---")
    if recording_active:
        stop_recording()
    if picam and picam.started:
        picam.stop()
        print("Camera stopped.")