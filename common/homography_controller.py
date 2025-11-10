import cv2
import numpy as np
import pandas as pd
import os
import subprocess
from ultralytics import YOLO
from tqdm import tqdm

# --- CONFIGURATION ---
MODEL_PATH = "badminton_court_keypoint.pt" 
CONFIDENCE_THRESHOLD = 0.3
# ----------------------

# --- COURT TEMPLATE (GLOBAL) ---
COURT_TEMPLATE = {
    "baseline_bottom": ((286, 2935), (1379, 2935)),
    "net": ((286, 1748), (1379, 1748)),
    # Outer doubles lines
    "left_outer_line": ((286, 2935), (286, 1748)),
    "right_outer_line": ((1379, 2935), (1379, 1748)),
    # Inner singles lines
    "left_inner_line": ((286 + 82, 2935), (286 + 82, 2935 - 836)),  # (368, 2935) -> (368, 2099)
    "right_inner_line": ((1379 - 84, 2935), (1379 - 84, 2935 - 836)), # (1295, 2935) -> (1295, 2099)
    # Service box lines
    "front_service_line": ((286, 2935 - 836), (1379, 2935 - 836)),  # (286, 2099) -> (1379, 2099)
    "doubles_long_service_line": ((286, 2935 - 135), (1379, 2935 - 135)), # (286, 2800) -> (1379, 2800)
    "center_line": ((833, 2935), (833, 2935 - 836)), # (833, 2935) -> (833, 2099)
}
# --- TEMPLATE POINTS for homography ---
# Order: Top-Left, Top-Right, Bottom-Left, Bottom-Right
TEMPLATE_PTS_HOMOGRAPHY = np.array([
    COURT_TEMPLATE["baseline_bottom"][0],
    COURT_TEMPLATE["baseline_bottom"][1],
    COURT_TEMPLATE["front_service_line"][0],
    COURT_TEMPLATE["front_service_line"][1]
], dtype=np.float32)

# --- 2D IMAGE CONSTANTS ---
W_2D = 1665
H_2D = 3228
PADDING = 100

# --- Utility: Line Intersection ---
def line_intersection(p1, p2, p3, p4):
    """Finds intersection of lines (p1,p2) and (p3,p4). Returns None if parallel."""
    x1, y1 = p1; x2, y2 = p2
    x3, y3 = p3; x4, y4 = p4
    denom = (x1 - x2)*(y3 - y4) - (y1 - y2)*(x3 - x4)
    if denom == 0:
        return None
    px = ((x1*y2 - y1*x2)*(x3 - x4) - (x1 - x2)*(x3*y4 - y3*x4)) / denom
    py = ((x1*y2 - y1*x2)*(y3 - y4) - (y1 - y2)*(x3*y4 - y3*x4)) / denom
    return int(px), int(py)

# --- Utility: Point Inside Polygon ---
def point_in_polygon(point, polygon):
    """Return True if point (x,y) is inside polygon (list of 4 (x,y) tuples)."""
    poly = np.array(polygon, dtype=np.int32).reshape((-1, 2))
    result = cv2.pointPolygonTest(poly, point, False)
    return result >= 0

# --- Step 1: Get Landing Point from CSV ---
def get_landing_point(csv_path):
    if not os.path.exists(csv_path):
        print(f"❌ CSV not found at {csv_path}")
        return None, None, None

    try:
        df = pd.read_csv(csv_path)
        df_visible = df.copy()
        df_visible.loc[df_visible['Visibility'] == 0, ['X', 'Y']] = np.nan

        # Smooth trajectory
        df_visible['X_smooth'] = df_visible['X'].rolling(7, center=True, min_periods=1).mean()
        df_visible['Y_smooth'] = df_visible['Y'].rolling(7, center=True, min_periods=1).mean()

        # Direction change
        df_visible['delta_X'] = df_visible['X_smooth'].diff()
        df_visible['delta_Y'] = df_visible['Y_smooth'].diff()
        
        v1x, v1y = df_visible['delta_X'], df_visible['delta_Y']
        v2x, v2y = df_visible['delta_X'].shift(-1), df_visible['delta_Y'].shift(-1)
        dot = v1x*v2x + v1y*v2y
        norm = np.sqrt(v1x**2 + v1y**2)*np.sqrt(v2x**2 + v2y**2)
        cos_t = np.clip(dot/norm, -1.0, 1.0)
        angle = np.degrees(np.arccos(cos_t))
        df_visible['Direction Change'] = angle

        # Detect large direction change (potential hit)
        hits = df_visible[df_visible['Direction Change'] > 30].index.tolist()
        if not hits:
            print("❌ No hits found.")
            return None, None, None

        # Cluster hits (simple gap threshold)
        clusters = []
        current = [hits[0]]
        for i in range(1, len(hits)):
            if hits[i] - hits[i-1] <= 30:
                current.append(hits[i])
            else:
                clusters.append(current)
                current = [hits[i]]
        clusters.append(current)

        last_cluster = clusters[-1]
        landing_point = None
        landing_frame = None
        for idx in last_cluster:
            if not np.isnan(df_visible.loc[idx, 'X']) and not np.isnan(df_visible.loc[idx, 'Y']):
                landing_point = (int(df_visible.loc[idx, 'X']), int(df_visible.loc[idx, 'Y']))
                landing_frame = idx
                print(f"✅ Landing point found at frame {landing_frame}: {landing_point}")
                break
        
        if landing_point is None:
             print("❌ No landing point found in last cluster.")
             return None, None, None

        return landing_point, landing_frame, len(df_visible)
    except Exception as e:
        print(f"❌ Error processing CSV: {e}")
        return None, None, None

# --- Function to draw FULL 2D court map ---
def generate_2d_illustration_full(landing_point_2d, in_zone, output_dir, base_filename):
    """
    Draws a 2D top-down illustration of the full court and landing point.
    Saves it as an image and returns the web-accessible path.
    """
    try:
        # Create a blank white image
        img_2d = np.ones((H_2D + PADDING * 2, W_2D + PADDING * 2, 3), dtype=np.uint8) * 255
        
        # Function to offset points by padding
        def p(point):
            return (int(point[0] + PADDING), int(point[1] + PADDING))

        # Draw all court lines from the template
        for name, (p1, p2) in COURT_TEMPLATE.items():
            cv2.line(img_2d, p(p1), p(p2), (0, 0, 0), 3) # Black lines

        # Define the "IN" zone polygon
        in_zone_template = np.array([
            p(COURT_TEMPLATE["left_inner_line"][0]),
            p(COURT_TEMPLATE["right_inner_line"][0]),
            p((COURT_TEMPLATE["right_inner_line"][0][0], COURT_TEMPLATE["net"][0][1])), 
            p((COURT_TEMPLATE["left_inner_line"][0][0], COURT_TEMPLATE["net"][0][1])) 
        ], dtype=np.int32)
        
        # Draw the "IN" zone
        cv2.polylines(img_2d, [in_zone_template.reshape(-1, 1, 2)], True, (0, 0, 255), 3) # Red polygon

        # Draw the mapped 2D landing point
        cv2.circle(img_2d, p(landing_point_2d), 20, (255, 0, 0), -1) # Blue circle

        # Add IN/OUT Text
        text = "Shuttle IN" if in_zone else "Shuttle OUT"
        color = (0, 255, 0) if in_zone else (0, 0, 255)
        text_pos = (PADDING, PADDING - 30)
        cv2.putText(img_2d, text, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 2, color, 4, cv2.LINE_AA)

        # Save the image
        output_filename = f"yolo_homog_{os.path.splitext(base_filename)[0]}_2d_full.png"
        output_image_path = os.path.join(output_dir, output_filename)
        cv2.imwrite(output_image_path, img_2d)
        
        # Return the web-accessible path
        web_image_path = os.path.join(os.path.basename(output_dir), output_filename)
        print(f"✅ 2D full illustration saved to: {output_image_path}")
        return web_image_path
        
    except Exception as e:
        print(f"❌ Error generating 2D full illustration: {e}")
        return None

# --- Function to draw ZOOMED 2D court map ---
def generate_2d_illustration_zoom(landing_point_2d, in_zone, output_dir, base_filename):
    """
    Draws a zoomed-in "Hawk-Eye" style illustration of the landing point.
    Saves it as a separate image and returns the web-accessible path.
    """
    try:
        # 1. Create the base full-court image (in memory)
        img_base = np.ones((H_2D + PADDING * 2, W_2D + PADDING * 2, 3), dtype=np.uint8) * 255
        def p(point):
            return (int(point[0] + PADDING), int(point[1] + PADDING))
        for name, (p1, p2) in COURT_TEMPLATE.items():
            cv2.line(img_base, p(p1), p(p2), (0, 0, 0), 5) # Thicker lines for zoom

        # 2. Define zoom parameters
        ZOOM_BOX_SIZE = 300 # Pixel radius from landing point to crop
        FINAL_ZOOM_SIZE = (400, 400) # Output size

        # 3. Get padded landing point coordinates
        lp_padded = p(landing_point_2d)

        # 4. Calculate crop region (y1:y2, x1:x2)
        x1 = max(0, lp_padded[0] - ZOOM_BOX_SIZE)
        y1 = max(0, lp_padded[1] - ZOOM_BOX_SIZE)
        x2 = min(img_base.shape[1], lp_padded[0] + ZOOM_BOX_SIZE)
        y2 = min(img_base.shape[0], lp_padded[1] + ZOOM_BOX_SIZE)
        
        zoom_crop = img_base[y1:y2, x1:x2]

        # 5. Resize to final output size
        zoom_resized = cv2.resize(zoom_crop, FINAL_ZOOM_SIZE, interpolation=cv2.INTER_LINEAR)
        
        # 6. Calculate landing point *relative to the resized crop*
        center_x_resized = FINAL_ZOOM_SIZE[0] // 2
        center_y_resized = FINAL_ZOOM_SIZE[1] // 2

        # 7. Draw "Hawk-Eye" style landing mark
        color = (0, 255, 0) if in_zone else (0, 0, 255)
        cv2.ellipse(zoom_resized, (center_x_resized, center_y_resized), (30, 50), 0, 0, 360, color, -1)
        cv2.ellipse(zoom_resized, (center_x_resized, center_y_resized), (30, 50), 0, 0, 360, (255, 255, 255), 3) # White border

        # 8. Save the zoomed image
        output_filename = f"yolo_homog_{os.path.splitext(base_filename)[0]}_2d_zoom.png"
        output_image_path = os.path.join(output_dir, output_filename)
        cv2.imwrite(output_image_path, zoom_resized)
        
        # 9. Return the web-accessible path
        web_image_path = os.path.join(os.path.basename(output_dir), output_filename)
        print(f"✅ 2D zoom illustration saved to: {output_image_path}")
        return web_image_path

    except Exception as e:
        print(f"❌ Error generating 2D zoom illustration: {e}")
        return None

# --- Helper function to re-encode video for web compatibility ---
def _reencode_video_for_web(raw_output_path, web_output_path, video_type="video"):
    """Helper function to re-encode raw video with ffmpeg for web compatibility."""
    try:
        print(f"Re-encoding {video_type} for web...")
        command = [
            'ffmpeg',
            '-y',
            '-i', raw_output_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # Use ultrafast for speed
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',  # Enable fast start for web playback
            web_output_path
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        os.remove(raw_output_path)  # Clean up raw file
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: ffmpeg re-encoding failed for {video_type}.")
        print(f"ffmpeg stderr: {e.stderr}")
        if os.path.exists(raw_output_path):
            os.remove(raw_output_path)
        return False

# --- Function to create full slow-motion video (for error cases) ---
def create_full_slowmotion_video(original_video_path, output_dir, base_filename):
    """
    Creates a slow-motion version of the entire video using ffmpeg (much faster).
    Used when inference fails to at least show the video in slow-motion.
    """
    try:
        web_filename = f"slowmo_{base_filename}"
        web_output_path = os.path.join(output_dir, web_filename)
        SLOWMO_FACTOR = 4  # 4x slower
        
        print(f"--- Creating full slow-motion video using ffmpeg (fast method) ---")
        
        # Use ffmpeg's setpts filter to slow down video - much faster than frame-by-frame
        # setpts=4*PTS means each frame is shown 4x longer (4x slower)
        command = [
            'ffmpeg',
            '-y',
            '-i', original_video_path,
            '-filter:v', f'setpts={SLOWMO_FACTOR}*PTS',
            '-an',  # Remove audio
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-pix_fmt', 'yuv420p',
            web_output_path
        ]
        
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"✅ Full slow-motion video saved to: {web_output_path}")
            # Return web-accessible path
            web_video_path = os.path.join(os.path.basename(output_dir), web_filename)
            return web_video_path
        except subprocess.CalledProcessError as e:
            print(f"❌ ERROR: ffmpeg slow-motion creation failed.")
            print(f"ffmpeg stderr: {e.stderr}")
            return None
        
    except Exception as e:
        print(f"❌ Error creating full slow-motion video: {e}")
        return None

# --- Function to create slow-motion zoom replay ---
def create_slow_zoom_replay(original_video_path, landing_frame, landing_point, output_dir, base_filename, fps):
    """
    Creates a slow-motion, zoomed-in replay clip of the landing.
    Uses ffmpeg for faster processing when possible, falls back to OpenCV if needed.
    """
    try:
        # Define clip parameters
        FRAMES_BEFORE = 15
        FRAMES_AFTER = 15
        SLOWMO_FACTOR = 4
        ZOOM_BOX_SIZE = 200
        FINAL_REPLAY_SIZE = 600

        start_frame = max(0, landing_frame - FRAMES_BEFORE)
        clip_duration_frames = FRAMES_BEFORE + FRAMES_AFTER
        clip_duration_seconds = clip_duration_frames / fps
        
        # Calculate start time in seconds
        start_time_seconds = start_frame / fps
        
        lp_x, lp_y = landing_point
        
        web_filename = f"yolo_homog_{os.path.splitext(base_filename)[0]}_replay.mp4"
        web_output_path = os.path.join(output_dir, web_filename)
        
        # Get video dimensions first
        cap = cv2.VideoCapture(original_video_path)
        if not cap.isOpened():
            print(f"❌ Error: Cannot open original video for replay: {original_video_path}")
            return None
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        
        # Calculate crop region (ffmpeg crop format: width:height:x:y)
        crop_x = max(0, lp_x - ZOOM_BOX_SIZE)
        crop_y = max(0, lp_y - ZOOM_BOX_SIZE)
        crop_w = min(2 * ZOOM_BOX_SIZE, width - crop_x)
        crop_h = min(2 * ZOOM_BOX_SIZE, height - crop_y)
        
        print(f"--- Creating slow-mo replay using ffmpeg (fast method) ---")
        
        # Use ffmpeg to extract, crop, zoom, and slow down in one pass
        command = [
            'ffmpeg',
            '-y',
            '-ss', str(start_time_seconds),  # Seek to start frame
            '-i', original_video_path,
            '-t', str(clip_duration_seconds),  # Duration of clip
            '-filter:v', f'crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={FINAL_REPLAY_SIZE}:{FINAL_REPLAY_SIZE},setpts={SLOWMO_FACTOR}*PTS',
            '-an',  # Remove audio
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            web_output_path
        ]
        
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            print(f"✅ Slow-mo replay saved to: {web_output_path}")
            # Return web-accessible path
            web_video_path = os.path.join(os.path.basename(output_dir), web_filename)
            return web_video_path
        except subprocess.CalledProcessError as e:
            print(f"⚠️  ffmpeg replay failed, falling back to OpenCV method...")
            print(f"ffmpeg stderr: {e.stderr}")
            # Fall back to OpenCV method
            return _create_slow_zoom_replay_opencv(original_video_path, landing_frame, landing_point, output_dir, base_filename, fps)
        
    except Exception as e:
        print(f"❌ Error creating slow-mo replay: {e}")
        # Try OpenCV fallback
        try:
            return _create_slow_zoom_replay_opencv(original_video_path, landing_frame, landing_point, output_dir, base_filename, fps)
        except:
            return None

# --- Fallback function using OpenCV for slow-motion zoom replay ---
def _create_slow_zoom_replay_opencv(original_video_path, landing_frame, landing_point, output_dir, base_filename, fps):
    """Fallback method using OpenCV if ffmpeg fails."""
    raw_output_path = None
    try:
        cap = cv2.VideoCapture(original_video_path)
        if not cap.isOpened():
            return None

        FRAMES_BEFORE = 15
        FRAMES_AFTER = 15
        CLIP_DURATION = FRAMES_BEFORE + FRAMES_AFTER
        SLOWMO_FACTOR = 4
        ZOOM_BOX_SIZE = 200
        FINAL_REPLAY_SIZE = (600, 600)

        start_frame = max(0, landing_frame - FRAMES_BEFORE)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        raw_filename = f"raw_replay_{os.path.splitext(base_filename)[0]}.mp4"
        raw_output_path = os.path.join(output_dir, raw_filename)
        web_filename = f"yolo_homog_{os.path.splitext(base_filename)[0]}_replay.mp4"
        web_output_path = os.path.join(output_dir, web_filename)
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(raw_output_path, fourcc, fps, FINAL_REPLAY_SIZE)

        if not out.isOpened():
            cap.release()
            return None

        lp_x, lp_y = landing_point

        for _ in range(CLIP_DURATION):
            ret, frame = cap.read()
            if not ret:
                break
            
            x1 = max(0, lp_x - ZOOM_BOX_SIZE)
            y1 = max(0, lp_y - ZOOM_BOX_SIZE)
            x2 = min(frame.shape[1], lp_x + ZOOM_BOX_SIZE)
            y2 = min(frame.shape[0], lp_y + ZOOM_BOX_SIZE)
            
            crop = frame[y1:y2, x1:x2]
            zoomed_frame = cv2.resize(crop, FINAL_REPLAY_SIZE, interpolation=cv2.INTER_LINEAR)
            
            for _ in range(SLOWMO_FACTOR):
                out.write(zoomed_frame)
        
        cap.release()
        out.release()
        
        if _reencode_video_for_web(raw_output_path, web_output_path, "slow-mo replay"):
            web_video_path = os.path.join(os.path.basename(output_dir), web_filename)
            return web_video_path
        else:
            return None
        
    except Exception as e:
        print(f"❌ Error in OpenCV fallback: {e}")
        if 'cap' in locals() and cap.isOpened():
            cap.release()
        if 'out' in locals() and out.isOpened():
            out.release()
        if raw_output_path and os.path.exists(raw_output_path):
            os.remove(raw_output_path)
        return None

# --- Step 2: Main Video + YOLO + Homography ---
def run_homography_check(video_path, csv_path, output_dir, manual_points=None):
    """
    Runs YOLO homography check on a video using a TFLite CSV.
    Can accept optional manual_points to bypass YOLO detection.
    """
    web_2d_full_path = None
    web_2d_zoom_path = None
    web_replay_path = None
    raw_output_path = None # Initialize
    H = None
    H_inv = None
    
    try:
        # Get landing point
        landing_point, landing_frame, total_frames = get_landing_point(csv_path)
        if landing_point is None:
            return False, "No valid landing point found in CSV. Cannot determine IN/OUT.", None, None, None

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False, f"Cannot open video file: {video_path}", None, None, None

        # Set buffer size to reduce I/O overhead
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        # --- NEW: Handle Homography (Auto vs Semi-Auto) ---
        if manual_points:
            print("✅ Using manual homography points.")
            detected_pts = np.array(manual_points, dtype=np.float32)
            H, _ = cv2.findHomography(TEMPLATE_PTS_HOMOGRAPHY, detected_pts)
            H_inv = np.linalg.inv(H)
        else:
            print("✅ Running automatic YOLO court detection...")
            if not os.path.exists(MODEL_PATH):
                return False, f"YOLO model not found at {MODEL_PATH}. Please place it in the root directory.", None, None, None
            model = YOLO(MODEL_PATH)
            
            # Find homography from the first few frames
            for _ in range(int(fps * 3)): # Try for 3 seconds
                ret, frame = cap.read()
                if not ret:
                    break
                results = model(frame, conf=CONFIDENCE_THRESHOLD, stream=True, verbose=False)
                for r in results:
                    boxes = r.boxes
                    if boxes is not None and len(boxes) > 0:
                        cls = boxes.cls.cpu().numpy().astype(int)
                        conf = boxes.conf.cpu().numpy()
                        xyxy = boxes.xyxy.cpu().numpy()
                        centers = [(int((x1+x2)/2), int((y1+y2)/2)) for x1, y1, x2, y2 in xyxy]

                        R1 = [(c, p) for c, p, cid in zip(conf, centers, cls) if cid == 2]
                        R3 = [(c, p) for c, p, cid in zip(conf, centers, cls) if cid == 3]
                        R1.sort(reverse=True, key=lambda x: x[0])
                        R3.sort(reverse=True, key=lambda x: x[0])

                        if len(R1) >= 2 and len(R3) >= 2:
                            detected_pts = np.array([R1[0][1], R1[1][1], R3[0][1], R3[1][1]], dtype=np.float32)
                            H, _ = cv2.findHomography(TEMPLATE_PTS_HOMOGRAPHY, detected_pts)
                            H_inv = np.linalg.inv(H) 
                            print("✅ Auto-homography computed.")
                            break # Exit loop once H is found
                if H is not None:
                    break
            
            if H is None:
                cap.release()
                return False, "Automatic court detection failed. Try Semi-Auto mode.", None, None, None

        # Reset video capture to frame 0 for processing
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        base_filename = os.path.basename(video_path)
        
        # --- Setup Video Writers - Write directly to H.264 for faster processing ---
        web_filename = f"yolo_homog_{base_filename}"
        web_output_path = os.path.join(output_dir, web_filename)
        
        # Use mp4v codec (most compatible, especially on Raspberry Pi)
        # Hardware H.264 encoders may not be available, so use software codec
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(web_output_path, fourcc, fps, (width, height))
        if not out.isOpened():
            # Try XVID as fallback
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            out = cv2.VideoWriter(web_output_path, fourcc, fps, (width, height))
            if not out.isOpened():
                cap.release()
                return False, f"Could not create VideoWriter at {web_output_path}", None, None, None

        # --- Pre-calculate mapped lines and intersection points ---
        mapped_lines = {}
        for name, (p1, p2) in COURT_TEMPLATE.items():
            line = np.array([[p1, p2]], dtype=np.float32)
            mapped_line = cv2.perspectiveTransform(line, H)[0]
            mapped_lines[name] = (tuple(mapped_line[0]), tuple(mapped_line[1]))

        i1 = line_intersection(*mapped_lines["baseline_bottom"], *mapped_lines["left_inner_line"])
        i2 = line_intersection(*mapped_lines["baseline_bottom"], *mapped_lines["right_inner_line"])
        i3 = line_intersection(*mapped_lines["net"], *mapped_lines["left_inner_line"])
        i4 = line_intersection(*mapped_lines["net"], *mapped_lines["right_inner_line"])
        
        intersection_pts = None
        if all([i1, i2, i3, i4]):
            intersection_pts = np.array([i1, i2, i4, i3], dtype=np.int32)
            print("✅ IN/OUT zone (singles) points:", intersection_pts.tolist())

        # --- Process Video (Optimized) ---
        frame_idx = 0
        show_result = False
        in_zone = False
        
        # Pre-convert intersection points to int32 once
        intersection_pts_int = None
        if intersection_pts is not None:
            intersection_pts_int = intersection_pts.reshape(-1, 1, 2).astype(np.int32)
        
        # Pre-convert line points to int32 tuples for faster drawing
        mapped_lines_int = {}
        for name, (p1, p2) in mapped_lines.items():
            mapped_lines_int[name] = (tuple(np.int32(p1)), tuple(np.int32(p2)))

        pbar = tqdm(total=total_frames, desc="YOLO Homography")
        
        # Pre-create a base overlay image with court lines (draw once, reuse)
        # This avoids redrawing lines on every frame
        base_overlay = np.zeros((height, width, 3), dtype=np.uint8)
        for name, (p1, p2) in mapped_lines_int.items():
            cv2.line(base_overlay, p1, p2, (255, 255, 0), 2)
        if intersection_pts_int is not None:
            cv2.polylines(base_overlay, [intersection_pts_int], True, (0, 0, 255), 3)
        
        # Only draw overlay on frames after landing (before that, just copy frames)
        draw_overlay_start = landing_frame if landing_frame is not None else total_frames
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                pbar.update(total_frames - frame_idx) 
                break

            # Only annotate frames from landing frame onwards (much faster)
            if frame_idx >= draw_overlay_start:
                # Use faster blending - copy frame and add overlay (faster than addWeighted)
                annotated_frame = frame.copy()
                # Use bitwise OR for faster overlay (works for binary-like overlays)
                mask = cv2.cvtColor(base_overlay, cv2.COLOR_BGR2GRAY) > 0
                annotated_frame[mask] = base_overlay[mask]
                
                # Once the landing frame is reached, compute IN/OUT once
                if frame_idx == landing_frame and not show_result:
                    in_zone = point_in_polygon(landing_point, intersection_pts)
                    show_result = True
                    print(f"🏸 Shuttle {'IN' if in_zone else 'OUT'} detected at frame {frame_idx}")
                    
                    if H_inv is not None:
                        lp_array = np.array([[landing_point]], dtype=np.float32)
                        lp_2d_array = cv2.perspectiveTransform(lp_array, H_inv)
                        lp_2d = tuple(lp_2d_array[0][0].astype(int))
                        print(f"✅ Mapped 2D landing point: {lp_2d}")
                        
                        web_2d_full_path = generate_2d_illustration_full(
                            lp_2d, in_zone, output_dir, base_filename
                        )
                        web_2d_zoom_path = generate_2d_illustration_zoom(
                            lp_2d, in_zone, output_dir, base_filename
                        )
                        web_replay_path = create_slow_zoom_replay(
                            video_path, landing_frame, landing_point, output_dir, base_filename, fps
                        )

                # Draw text and circle only after landing frame
                if show_result:
                    text = "Shuttle IN" if in_zone else "Shuttle OUT"
                    color = (0, 255, 0) if in_zone else (0, 0, 255)
                    cv2.putText(annotated_frame, text, (width - 300, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3, cv2.LINE_AA)
                    cv2.circle(annotated_frame, landing_point, 12, (255, 0, 0), -1)
                
                out.write(annotated_frame)
            else:
                # Before landing frame, just write original frame (much faster)
                out.write(frame)

            frame_idx += 1
            pbar.update(1)

        pbar.close()
        cap.release()
        out.release()
        print(f"✅ Annotated video saved to: {web_output_path}")
        
        # Re-encode with ffmpeg for web compatibility (only if needed)
        # Use .mp4 extension for temp file so ffmpeg can detect format
        temp_output = os.path.splitext(web_output_path)[0] + "_temp.mp4"
        command = [
            'ffmpeg',
            '-y',
            '-i', web_output_path,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # Use ultrafast for speed
            '-pix_fmt', 'yuv420p',
            '-f', 'mp4',  # Explicitly specify format
            '-movflags', '+faststart',  # Enable fast start for web playback
            temp_output
        ]
        
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            # Replace original with re-encoded version
            os.replace(temp_output, web_output_path)
            print(f"✅ Web-compatible annotated video saved to: {web_output_path}")
            
            web_video_path = os.path.join(os.path.basename(output_dir), web_filename)
            return True, web_video_path, web_2d_full_path, web_2d_zoom_path, web_replay_path
        
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Warning: ffmpeg re-encoding failed, using original video.")
            print(f"ffmpeg stderr: {e.stderr}")
            if os.path.exists(temp_output):
                os.remove(temp_output)
            # Return the original file anyway - it might still work
            web_video_path = os.path.join(os.path.basename(output_dir), web_filename)
            return True, web_video_path, web_2d_full_path, web_2d_zoom_path, web_replay_path

    except Exception as e:
        print(f"❌ Error during homography processing: {e}")
        if 'cap' in locals() and cap.isOpened(): cap.release()
        if 'out' in locals() and out.isOpened(): out.release()
        if 'pbar' in locals(): pbar.close()
        if 'web_output_path' in locals() and os.path.exists(web_output_path):
             os.remove(web_output_path) # Cleanup on error
        return False, str(e), None, None, None