import cv2
import numpy as np
import pandas as pd
import os
import subprocess
from ultralytics import YOLO

def reencode_for_web(input_path, output_path):
    """
    Converts a video to H.264 format using ffmpeg for browser compatibility.
    """
    try:
        if os.path.exists(output_path):
            os.remove(output_path)
            
        command = [
            'ffmpeg',
            '-y',                 # Overwrite output
            '-i', input_path,     # Input file
            '-vcodec', 'libx264', # Web-compatible video codec
            '-acodec', 'aac',     # Audio codec (standard)
            '-pix_fmt', 'yuv420p',# Pixel format for broad compatibility
            '-movflags', 'faststart', # Optimize for web streaming
            output_path
        ]
        # Run ffmpeg (suppress output to keep logs clean)
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"Error re-encoding video {input_path}: {e}")
        return False

def generate_highlights(video_path, csv_path, output_dir):
    """
    Generates highlight clips from a video using tracking data.
    """
    # Parameters
    min_shortest_rally_duration_seconds = 3
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Names
    base_name = os.path.basename(video_path).split('.')[0]
    
    # Temp paths (OpenCV writes these)
    temp_highlight = os.path.join(output_dir, f"temp_highlights_{base_name}.mp4")
    temp_longest = os.path.join(output_dir, f"temp_longest_{base_name}.mp4")
    temp_shortest = os.path.join(output_dir, f"temp_shortest_{base_name}.mp4")

    # Final Web Paths (FFmpeg writes these)
    final_highlight = os.path.join(output_dir, f"highlights_{base_name}.mp4")
    final_longest = os.path.join(output_dir, f"longest_{base_name}.mp4")
    final_shortest = os.path.join(output_dir, f"shortest_{base_name}.mp4")

    # Load Resources
    device = 'cpu' # Use CPU for Pi
    print(f"Loading YOLOv8 model on {device}...")
    try:
        # Ensure you have the model file, or download yolov8n.pt
        yolo_model = YOLO("yolov8n.pt").to(device)
    except:
        print("Warning: YOLO model not found/loaded. Skipping player speed calculation.")

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return False, None

    # --- Identify Active Sequences ---
    active_sequences = []
    current_sequence = []
    consecutive_zero_frames = 0

    for i, row in df.iterrows():
        if row["Visibility"] > 0:
            current_sequence.append((row["Frame"], row["X"], row["Y"]))
            consecutive_zero_frames = 0
        else:
            consecutive_zero_frames += 1
            if consecutive_zero_frames <= 30:
                current_sequence.append((row["Frame"], row["X"], row["Y"]))
            else:
                if len(current_sequence) >= 5:
                    active_sequences.append(current_sequence)
                current_sequence = []
                consecutive_zero_frames = 0

    if len(current_sequence) >= 5:
        active_sequences.append(current_sequence)

    if not active_sequences:
        return True, {} 

    # Open Video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Could not open input video."
        
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Score Sequences
    highlight_scores = []
    for seq in active_sequences:
        start_frame = seq[0][0]
        end_frame = seq[-1][0]
        
        # Simple ball speed calc
        ball_speeds = [np.linalg.norm(np.array(seq[j][1:]) - np.array(seq[j-1][1:])) for j in range(1, len(seq))]
        avg_ball_speed = np.mean(ball_speeds) if ball_speeds else 0
        
        # Score = Duration * 0.4 + Speed * 0.3
        score = (len(seq) * 0.4) + (avg_ball_speed * 0.3)
        highlight_scores.append((score, start_frame, end_frame))

    # Select top 25%
    highlight_scores.sort(reverse=True, key=lambda x: x[0])
    selected_sequences = highlight_scores[:max(1, len(highlight_scores) // 4)]

    # --- 1. Write Main Highlights (Temp) ---
    print("Writing raw highlights...")
    out = cv2.VideoWriter(temp_highlight, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
    
    final_clips_meta = [] # Store metadata for finding long/short later
    
    for _, start, end in selected_sequences:
        final_clips_meta.append({'start': start, 'end': end})
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        for f_idx in range(int(start), int(end) + 1):
            ret, frame = cap.read()
            if not ret: break
            
            # Draw ball
            row = df[df["Frame"] == f_idx]
            if not row.empty and row['Visibility'].values[0] > 0:
                cv2.circle(frame, (int(row['X'].values[0]), int(row['Y'].values[0])), 7, (0, 0, 255), -1)
            
            out.write(frame)
    out.release()

    # --- 2. Write Individual Clips (Temp) ---
    temp_files = {"highlights": temp_highlight}
    
    if final_clips_meta:
        # Longest
        longest = max(final_clips_meta, key=lambda x: x['end'] - x['start'])
        _write_single_clip(video_path, longest['start'], longest['end'], temp_longest, df)
        temp_files["longest"] = temp_longest

        # Shortest
        min_frames = min_shortest_rally_duration_seconds * fps
        eligible = [c for c in final_clips_meta if (c['end'] - c['start']) >= min_frames]
        if eligible:
            shortest = min(eligible, key=lambda x: x['end'] - x['start'])
            _write_single_clip(video_path, shortest['start'], shortest['end'], temp_shortest, df)
            temp_files["shortest"] = temp_shortest

    cap.release()

    # --- 3. Re-encode All for Web ---
    print("Re-encoding videos for web compatibility...")
    final_files = {}
    
    # Process Highlights
    if reencode_for_web(temp_highlight, final_highlight):
        final_files["highlights"] = final_highlight
        os.remove(temp_highlight) # Clean up raw file

    # Process Longest
    if "longest" in temp_files and reencode_for_web(temp_longest, final_longest):
        final_files["longest"] = final_longest
        os.remove(temp_longest)

    # Process Shortest
    if "shortest" in temp_files and reencode_for_web(temp_shortest, final_shortest):
        final_files["shortest"] = final_shortest
        os.remove(temp_shortest)

    return True, final_files

def _write_single_clip(video_path, start, end, out_path, df):
    """Helper to write a specific frame range to a file."""
    cap = cv2.VideoCapture(video_path)
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    out = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    
    for f_idx in range(int(start), int(end) + 1):
        ret, frame = cap.read()
        if not ret: break
        
        row = df[df["Frame"] == f_idx]
        if not row.empty and row['Visibility'].values[0] > 0:
            cv2.circle(frame, (int(row['X'].values[0]), int(row['Y'].values[0])), 7, (0, 0, 255), -1)
        
        out.write(frame)
    
    cap.release()
    out.release()