import cv2
import numpy as np
import pandas as pd
import os
from ultralytics import YOLO
from tqdm import tqdm

# --- CONFIGURATION ---
MODEL_PATH = "badminton_court_keypoint.pt" 
CONFIDENCE_THRESHOLD = 0.3
# ----------------------

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

# --- Function to draw 2D court map ---
def generate_2d_illustration(court_template, landing_point_2d, in_zone, output_dir, base_filename):
    """
    Draws a 2D top-down illustration of the court, landing zone, and landing point.
    Saves it as an image and returns the web-accessible path.
    """
    try:
        # Define 2D image dimensions with padding
        W_2D = 1665
        H_2D = 3228
        PADDING = 100
        
        # Create a blank white image
        img_2d = np.ones((H_2D + PADDING * 2, W_2D + PADDING * 2, 3), dtype=np.uint8) * 255
        
        # Function to offset points by padding
        def p(point):
            return (int(point[0] + PADDING), int(point[1] + PADDING))

        # Draw all court lines from the template
        for name, (p1, p2) in court_template.items():
            cv2.line(img_2d, p(p1), p(p2), (0, 0, 0), 3) # Black lines

        # Define the "IN" zone polygon from the template coordinates
        in_zone_template = np.array([
            p(court_template["left_inner_line"][0]),
            p(court_template["right_inner_line"][0]),
            p((court_template["right_inner_line"][0][0], court_template["net"][0][1])), 
            p((court_template["left_inner_line"][0][0], court_template["net"][0][1])) 
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
        output_filename = f"yolo_homog_{os.path.splitext(base_filename)[0]}_2d.png"
        output_image_path = os.path.join(output_dir, output_filename)
        cv2.imwrite(output_image_path, img_2d)
        
        # Return the web-accessible path
        web_image_path = os.path.join(os.path.basename(output_dir), output_filename)
        print(f"✅ 2D illustration saved to: {output_image_path}")
        return web_image_path
        
    except Exception as e:
        print(f"❌ Error generating 2D illustration: {e}")
        return None

# --- Step 2: Main Video + YOLO + Homography ---
def run_homography_check(video_path, csv_path, output_dir):
    """
    Runs YOLO homography check on a video using a TFLite CSV.
    Returns (True, web_video_path, web_2d_image_path) on success,
    or (False, error_message, None) on failure.
    """
    web_2d_image_path = None
    try:
        # Get landing point
        landing_point, landing_frame, total_frames = get_landing_point(csv_path)
        if landing_point is None:
            return False, "No valid landing point found in CSV. Cannot determine IN/OUT.", None

        # Load YOLO model
        if not os.path.exists(MODEL_PATH):
            return False, f"YOLO model not found at {MODEL_PATH}. Please place it in the root directory.", None
        model = YOLO(MODEL_PATH)
        print("✅ YOLO model loaded successfully.")

        # --- MODIFIED: Corrected center_line coordinates ---
        court_template = {
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
            # --- THIS IS THE CORRECTED LINE ---
            "center_line": ((833, 2935), (833, 2935 - 836)), # (833, 2935) -> (833, 2099)
        }
        # ----------------------------------------------------

        # Reference pts for homography (we still use the 4 main points)
        template_pts = np.array([
            court_template["baseline_bottom"][0],
            court_template["baseline_bottom"][1],
            court_template["front_service_line"][0],
            court_template["front_service_line"][1]
        ], dtype=np.float32)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False, f"Cannot open video file: {video_path}", None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        base_filename = os.path.basename(video_path)
        output_filename = f"yolo_homog_{base_filename}"
        output_video_path = os.path.join(output_dir, output_filename)
        
        out = cv2.VideoWriter(output_video_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        if not out.isOpened():
             return False, f"Could not create VideoWriter at {output_video_path}", None

        H = None
        H_inv = None 
        intersection_pts = None
        frame_idx = 0
        show_result = False
        in_zone = False

        pbar = tqdm(total=total_frames, desc="YOLO Homography")
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                pbar.update(total_frames - frame_idx) 
                break

            results = model(frame, conf=CONFIDENCE_THRESHOLD, stream=True, verbose=False)
            annotated_frame = frame.copy() 

            for r in results:
                annotated_frame = r.plot() 
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

                    if len(R1) >= 2 and len(R3) >= 2 and H is None:
                        detected_pts = np.array([R1[0][1], R1[1][1], R3[0][1], R3[1][1]], dtype=np.float32)
                        H, _ = cv2.findHomography(template_pts, detected_pts)
                        H_inv = np.linalg.inv(H) 
                        print("✅ Homography computed.")

                        # Map template lines
                        mapped = {}
                        for name, (p1, p2) in court_template.items():
                            line = np.array([[p1, p2]], dtype=np.float32)
                            mapped_line = cv2.perspectiveTransform(line, H)[0]
                            mapped[name] = (tuple(mapped_line[0]), tuple(mapped_line[1]))

                        # Find intersections for "IN" (singles) quadrilateral
                        i1 = line_intersection(*mapped["baseline_bottom"], *mapped["left_inner_line"])
                        i2 = line_intersection(*mapped["baseline_bottom"], *mapped["right_inner_line"])
                        i3 = line_intersection(*mapped["net"], *mapped["left_inner_line"])
                        i4 = line_intersection(*mapped["net"], *mapped["right_inner_line"])
                        if all([i1, i2, i3, i4]):
                            intersection_pts = np.array([i1, i2, i4, i3], dtype=np.int32)
                            print("✅ IN/OUT zone (singles) points:", intersection_pts.tolist())

                # Draw ALL court lines from template
                if H is not None:
                    for name, (p1, p2) in court_template.items():
                        line = np.array([[p1, p2]], dtype=np.float32)
                        dst = cv2.perspectiveTransform(line, H)[0]
                        cv2.line(annotated_frame, tuple(dst[0].astype(int)), tuple(dst[1].astype(int)), (255, 255, 0), 2)

                # Draw red "IN" quadrilateral
                if intersection_pts is not None:
                    cv2.polylines(annotated_frame, [intersection_pts.reshape(-1, 1, 2)], True, (0, 0, 255), 3)

                    # Once the landing frame is reached, compute IN/OUT once
                    if frame_idx >= landing_frame and not show_result:
                        in_zone = point_in_polygon(landing_point, intersection_pts)
                        show_result = True
                        print(f"🏸 Shuttle {'IN' if in_zone else 'OUT'} detected at frame {frame_idx}")
                        
                        if H_inv is not None:
                            lp_array = np.array([[landing_point]], dtype=np.float32)
                            lp_2d_array = cv2.perspectiveTransform(lp_array, H_inv)
                            lp_2d = tuple(lp_2d_array[0][0].astype(int))
                            print(f"✅ Mapped 2D landing point: {lp_2d}")
                            
                            web_2d_image_path = generate_2d_illustration(
                                court_template, lp_2d, in_zone, output_dir, base_filename
                            )

                    # Draw only after landing frame
                    if show_result:
                        text = "Shuttle IN" if in_zone else "Shuttle OUT"
                        color = (0, 255, 0) if in_zone else (0, 0, 255)
                        cv2.putText(annotated_frame, text, (width - 300, 50),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3, cv2.LINE_AA)
                        cv2.circle(annotated_frame, landing_point, 12, (255, 0, 0), -1)

            out.write(annotated_frame)
            frame_idx += 1
            pbar.update(1)

        pbar.close()
        cap.release()
        out.release()
        print(f"✅ Output video saved to: {output_video_path}")
        
        web_video_path = os.path.join(os.path.basename(output_dir), os.path.basename(output_video_path))
        return True, web_video_path, web_2d_image_path 

    except Exception as e:
        print(f"❌ Error during homography processing: {e}")
        if 'cap' in locals() and cap.isOpened(): cap.release()
        if 'out' in locals() and out.isOpened(): out.release()
        if 'pbar' in locals(): pbar.close()
        return False, str(e), None