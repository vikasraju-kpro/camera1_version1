import os
import threading
import time
import cv2
import subprocess as sp
from picamera2 import Picamera2

# --- Camera Configuration ---
FISHEYE_CAM_ID = 0
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
# We no longer need a hardcoded VIDEO_FPS, as we get it from the camera.

# --- Global Variables ---
picam = None
actual_video_fps = 30  # A default fallback value
recording_active = False
recording_thread = None
stop_recording_event = threading.Event()
ffmpeg_process = None
output_path = None
lock = threading.Lock()


def get_recording_status():
    """Safely returns the current recording status."""
    with lock:
        return recording_active


def initialize_camera():
    """Initializes and configures the fisheye camera."""
    global picam, actual_video_fps
    print("--- Initializing Fisheye Camera ---")
    try:
        picam = Picamera2(camera_num=FISHEYE_CAM_ID)
        config = picam.create_video_configuration(
            main={"size": (VIDEO_WIDTH, VIDEO_HEIGHT)}
        )
        picam.configure(config)

        # --- FIX: Get the actual framerate from the camera's configuration ---
        try:
            # This extracts the negotiated frame rate from the camera controls
            actual_video_fps = picam.video_configuration['controls']['FrameRate']
            print(f"Camera configured with actual frame rate: {actual_video_fps} FPS")
        except (KeyError, TypeError):
            print(f"Could not determine actual frame rate, falling back to default {actual_video_fps} FPS.")
        # --------------------------------------------------------------------

        picam.start()
        time.sleep(2.0)
        print("Fisheye camera started successfully.")
        return True
    except Exception as e:
        print(f"ERROR: Failed to initialize camera: {e}")
        return False


def capture_image(filepath):
    """Captures a single still image from the camera."""
    global picam
    with lock:
        if recording_active:
            return False, "Recording is currently active."
        if not picam or not picam.started:
            return False, "Camera is not ready."

        try:
            array = picam.capture_array("main")
            if array.shape[2] == 4:
                array = cv2.cvtColor(array, cv2.COLOR_BGRA2BGR)
            cv2.imwrite(filepath, array)
            print(f"Image saved to {filepath}")
            return True, "Image captured successfully."
        except Exception as e:
            print(f"ERROR: Failed to capture image: {e}")
            return False, f"Failed to capture image: {e}"


def _record_video_loop():
    """The thread target function for recording video. It pipes frames to FFmpeg."""
    global picam, ffmpeg_process, stop_recording_event
    print("Recording thread started. Piping frames to FFmpeg...")

    while not stop_recording_event.is_set():
        try:
            array = picam.capture_array("main")
            if array.shape[2] == 4:
                frame_bgr = cv2.cvtColor(array, cv2.COLOR_BGRA2BGR)
                ffmpeg_process.stdin.write(frame_bgr.tobytes())
            else:
                ffmpeg_process.stdin.write(array.tobytes())
        except Exception as e:
            if stop_recording_event.is_set():
                print("Recording stopped, exiting loop.")
                break
            print(f"ERROR in recording loop while writing to FFmpeg pipe: {e}")
            time.sleep(0.5)

    print("Recording thread finished.")


def start_recording(filepath):
    """Starts recording by launching an FFmpeg subprocess and a frame-feeding thread."""
    global recording_active, recording_thread, stop_recording_event
    global ffmpeg_process, output_path, actual_video_fps

    with lock:
        if recording_active:
            return False, "A recording is already in progress."
        if not picam or not picam.started:
            return False, "Camera is not ready."

        try:
            output_path = filepath
            command = [
                'ffmpeg',
                '-y',
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-s', f'{VIDEO_WIDTH}x{VIDEO_HEIGHT}',
                '-r', str(actual_video_fps),  # Use the dynamic frame rate
                '-i', '-',
                '-an',
                '-vcodec', 'libx264',
                '-pix_fmt', 'yuv420p',
                output_path
            ]
            print(f"Starting FFmpeg with command: {' '.join(command)}")
            ffmpeg_process = sp.Popen(command, stdin=sp.PIPE, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            stop_recording_event.clear()
            recording_active = True
            recording_thread = threading.Thread(target=_record_video_loop, daemon=True)
            recording_thread.start()
            print(f"Started recording to {output_path}")
            return True, "Video recording started."
        except Exception as e:
            print(f"ERROR starting FFmpeg recording: {e}")
            return False, f"Failed to start recording: {e}"


def stop_recording():
    """Stops recording by signaling the thread and closing the FFmpeg process."""
    global recording_active, recording_thread, stop_recording_event, ffmpeg_process, output_path

    with lock:
        if not recording_active:
            return False, "No active recording to stop.", None
        print("Stopping recording...")
        stop_recording_event.set()
        recording_active = False

    if recording_thread:
        recording_thread.join(timeout=5)
        if recording_thread.is_alive():
            print("WARN: Frame-feeding thread did not stop cleanly.")

    if ffmpeg_process:
        try:
            ffmpeg_process.stdin.close()
            ffmpeg_process.wait(timeout=10)
            print(f"FFmpeg process finished with code: {ffmpeg_process.returncode}")
        except Exception as e:
            print(f"Error while closing FFmpeg process: {e}")
            ffmpeg_process.kill()

    print(f"Stopped recording. Video saved to {output_path}")
    return True, "Video recording stopped.", output_path


def cleanup():
    """Stops the camera and cleans up resources."""
    global picam
    print("--- Performing cleanup ---")
    if recording_active:
        stop_recording()
    if picam and picam.started:
        picam.stop()
        print("Camera stopped.")