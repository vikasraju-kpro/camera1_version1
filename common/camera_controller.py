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
TARGET_VIDEO_FPS = 30

# --- Global Variables ---
picam = None
actual_video_fps = 30
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
            main={"size": (VIDEO_WIDTH, VIDEO_HEIGHT)},
            controls={"FrameRate": TARGET_VIDEO_FPS}
        )
        picam.configure(config)
        try:
            # Best-effort: apply target FPS to the camera
            picam.set_controls({"FrameRate": TARGET_VIDEO_FPS})
        except Exception as e:
            print(f"WARN: Unable to set camera FrameRate to {TARGET_VIDEO_FPS}: {e}")

        try:
            # Use configured or target FPS for encoding; avoid relying on undefined metadata
            actual_video_fps = picam.video_configuration['controls'].get('FrameRate', TARGET_VIDEO_FPS)
        except Exception:
            actual_video_fps = TARGET_VIDEO_FPS
        print(f"Camera configured target frame rate: {TARGET_VIDEO_FPS} FPS; using {actual_video_fps} FPS for encoding")
        picam.start()
        time.sleep(2.0)
        print("Fisheye camera started successfully.")
        return True
    except Exception as e:
        print(f"ERROR: Failed to initialize camera: {e}")
        return False


def capture_image(filepath):
    """Captures a single still image and saves it with correct RGB colors."""
    global picam
    with lock:
        if recording_active:
            return False, "Recording is currently active."
        if not picam or not picam.started:
            return False, "Camera is not ready."

        try:
            # Picamera2 provides a BGR-based array (often with an alpha channel)
            array_bgra = picam.capture_array("main")
            
            # For saving a standard image file, cv2.imwrite needs a 3-channel BGR array.
            # Convert from BGRA to BGR when needed for correct color order.
            if array_bgra.shape[2] == 4:
                save_array = cv2.cvtColor(array_bgra, cv2.COLOR_BGRA2BGR)
            else:
                save_array = array_bgra # It's already BGR
            
            cv2.imwrite(filepath, save_array)
            print(f"Image saved to {filepath} with correct colors.")
            return True, "Image captured successfully."
        except Exception as e:
            print(f"ERROR: Failed to capture image: {e}")
            return False, f"Failed to capture image: {e}"


def _record_video_loop():
    """The thread target function that pipes BGR frames to FFmpeg."""
    global picam, ffmpeg_process, stop_recording_event
    print("Recording thread started. Piping BGR frames to FFmpeg...")

    while not stop_recording_event.is_set():
        try:
            array_bgra = picam.capture_array("main")
            
            # The most stable method is to give FFmpeg the BGR data
            # it expects based on our command. Convert from 4-channel BGRA to 3-channel BGR.
            if array_bgra.shape[2] == 4:
                frame_bgr = cv2.cvtColor(array_bgra, cv2.COLOR_BGRA2BGR)
            else:
                frame_bgr = array_bgra

            ffmpeg_process.stdin.write(frame_bgr.tobytes())
        except Exception as e:
            if stop_recording_event.is_set():
                print("Recording stopped, exiting loop.")
                break
            print(f"ERROR in recording loop while writing to FFmpeg pipe: {e}")
            time.sleep(0.5)

    print("Recording thread finished.")


def start_recording(filepath):
    """Starts recording by launching an FFmpeg subprocess that expects BGR frames."""
    global recording_active, recording_thread, stop_recording_event
    global ffmpeg_process, output_path, actual_video_fps

    with lock:
        if recording_active:
            return False, "A recording is already in progress."
        if not picam or not picam.started:
            return False, "Camera is not ready."

        try:
            # Measure actual camera FPS briefly to match FFmpeg's input rate
            measured_fps = None
            try:
                sample_frames = 20
                t0 = time.time()
                for _ in range(sample_frames):
                    picam.capture_array("main")
                t1 = time.time()
                if t1 > t0:
                    measured_fps = max(1.0, min(120.0, (sample_frames / (t1 - t0))))
            except Exception as e:
                print(f"WARN: Unable to measure camera FPS: {e}")

            if measured_fps:
                actual_video_fps = round(measured_fps, 2)
            else:
                # Fallback to configured/target FPS
                actual_video_fps = actual_video_fps or TARGET_VIDEO_FPS

            output_path = filepath
            # This command tells FFmpeg to expect BGR data (`bgr24`) and
            # it will correctly handle the conversion to the standard YUV format for MP4,
            # resulting in correct colors in any video player.
            command = [
                'ffmpeg',
                '-y',
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-pix_fmt', 'bgr24',
                '-s', f'{VIDEO_WIDTH}x{VIDEO_HEIGHT}',
                '-r', str(actual_video_fps),
                '-i', '-',
                '-an',
                '-vcodec', 'libx264',
                '-pix_fmt', 'yuv420p', # Standard for video playback compatibility
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