import os
import time
import datetime
import subprocess

# Matches the framerate in camera_controller.py
FRAMERATE = 47.57 

# CALCULATION:
# Previous test: 60MB = 44 seconds.
# Implies Bitrate = ~1.36 MB/s.
# Target: 30 seconds.
# 30 sec * 1.36 MB/s = ~40.8 MB.
# We set it to 42MB to be safe (approx 31-32 seconds).
BYTES_TO_READ = 42 * 1024 * 1024 

def create_instant_replay(output_dir, video_extension=".mp4", duration=30):
    """
    Extracts the last ~30 seconds from the active .h264 recording
    by reading a calculated byte-chunk from the tail.
    """
    try:
        recordings_dir = "static/recordings"
        temp_tail_path = os.path.join(output_dir, "temp_replay_tail.h264")
        
        # 1. Find the latest active .h264 file
        files = [os.path.join(recordings_dir, f) for f in os.listdir(recordings_dir) if f.endswith(".h264")]
        if not files:
            # Fallback: Check for mp4 if h264 is gone
            files_mp4 = [os.path.join(recordings_dir, f) for f in os.listdir(recordings_dir) if f.endswith(".mp4")]
            if files_mp4:
                 files = files_mp4
            else:
                return False, "No active recording found.", None
            
        latest_file = max(files, key=os.path.getmtime)
        
        # 2. Setup output path
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        replay_filename = f"replay_{timestamp}{video_extension}"
        replay_path = os.path.join(output_dir, replay_filename)
        os.makedirs(output_dir, exist_ok=True)

        print(f"--- Processing replay from source: {latest_file} ---")

        # 3. Handle Raw .h264 (Active Recording)
        if latest_file.endswith(".h264"):
            file_size = os.path.getsize(latest_file)
            
            # Read ONLY the calculated tail bytes (approx 30s)
            with open(latest_file, "rb") as f:
                if file_size > BYTES_TO_READ:
                    f.seek(-BYTES_TO_READ, os.SEEK_END)
                else:
                    f.seek(0)
                tail_data = f.read()
            
            # Write to a temp file
            with open(temp_tail_path, "wb") as temp:
                temp.write(tail_data)
            
            # Convert the tail chunk to MP4
            # We removed '-sseof' because we already sliced the file in Python.
            # We just wrap whatever we grabbed.
            command = [
                'ffmpeg',
                '-y',
                '-r', str(FRAMERATE),      # Force input framerate
                '-i', temp_tail_path,      # Input the ~30s chunk
                '-c:v', 'copy',            # Copy stream (fast)
                replay_path
            ]
            
        # 4. Handle .mp4 (Finished Recording)
        else:
            # For finished files, seeking works perfectly
            command = [
                'ffmpeg',
                '-y',
                '-sseof', f'-{duration}',
                '-i', latest_file,
                '-c', 'copy',
                replay_path
            ]

        # Execute
        result = subprocess.run(command, capture_output=True, text=True)
        
        # Cleanup temp file
        if os.path.exists(temp_tail_path):
            os.remove(temp_tail_path)

        if result.returncode == 0:
            print(f"✅ Replay saved: {replay_path}")
            return True, "Replay created.", replay_path
        else:
            print(f"❌ Replay failed: {result.stderr}")
            return False, f"FFmpeg error: {result.stderr[-200:]}", None

    except Exception as e:
        print(f"❌ Error creating replay: {e}")
        return False, str(e), None