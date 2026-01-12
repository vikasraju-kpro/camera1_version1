import cv2
import numpy as np
import os
import glob
import subprocess

# --- Configuration ---
CHECKERBOARD_SIZE = (9, 6)
CALIBRATION_DIR = "static/calibration_images"
CAMERA_MATRIX_FILE = "calibration_data/camera_matrix.npy"
DIST_COEFF_FILE = "calibration_data/dist_coeff.npy"
MIN_IMAGES_REQUIRED = 15
FRAME_SIZE = (1920, 1080)

# --- 3D points for the checkerboard object ---
objp = np.zeros((1, CHECKERBOARD_SIZE[0] * CHECKERBOARD_SIZE[1], 3), np.float32)
objp[0, :, :2] = np.mgrid[0:CHECKERBOARD_SIZE[0], 0:CHECKERBOARD_SIZE[1]].T.reshape(-1, 2)


def find_checkerboard_in_image(image_path):
    """
    Finds the checkerboard in a given image.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"ERROR: Failed to load image at {image_path}")
        return False, "Failed to load image.", None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD_SIZE, None)
    if ret:
        dir_name, file_name = os.path.split(image_path)
        preview_filename = file_name.replace('.jpg', '_preview.jpg')
        preview_path = os.path.join(dir_name, preview_filename)
        cv2.drawChessboardCorners(img, CHECKERBOARD_SIZE, corners, ret)
        cv2.imwrite(preview_path, img)
        return True, "Checkerboard found successfully!", preview_path
    else:
        return False, "Checkerboard not found. Please try a different angle or distance.", image_path


def run_calibration_process():
    """
    Performs fisheye camera calibration using the logic from your calibrate.py.
    """
    print("\n--- Starting Fisheye Calibration Process ---")
    objpoints = []
    imgpoints = []
    
    original_images_with_previews = [
        f.replace('_preview.jpg', '.jpg') 
        for f in glob.glob(os.path.join(CALIBRATION_DIR, '*_preview.jpg'))
        if os.path.exists(f.replace('_preview.jpg', '.jpg'))
    ]

    print(f"Found {len(original_images_with_previews)} images with successful checkerboard detection.")

    if len(original_images_with_previews) < MIN_IMAGES_REQUIRED:
        message = f"Not enough valid images. {MIN_IMAGES_REQUIRED} are required, but only {len(original_images_with_previews)} have a detected checkerboard."
        print(f"ERROR: {message}")
        return False, message

    for fname in original_images_with_previews:
        img = cv2.imread(fname)
        if img is None:
            print(f"WARN: Could not read image {fname}, skipping.")
            continue
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, CHECKERBOARD_SIZE, None)
        
        if ret:
            objpoints.append(objp)
            refined_corners = cv2.cornerSubPix(
                gray, corners, (11, 11), (-1, -1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.1)
            )
            imgpoints.append(refined_corners.reshape(1, -1, 2))
        else:
            print(f"WARN: Could not re-find corners in {fname}, skipping.")

    if len(objpoints) < MIN_IMAGES_REQUIRED:
        message = f"Could not extract enough valid corner points. Needed {MIN_IMAGES_REQUIRED}, got {len(objpoints)}."
        print(f"ERROR: {message}")
        return False, message

    print(f"Proceeding to calibrate with {len(objpoints)} valid images.")
    
    try:
        K = np.zeros((3, 3))
        D = np.zeros((4, 1))
        rvecs = [np.zeros((1, 1, 3), dtype=np.float64) for i in range(len(objpoints))]
        tvecs = [np.zeros((1, 1, 3), dtype=np.float64) for i in range(len(objpoints))]
        
        rms, K, D, rvecs, tvecs = cv2.fisheye.calibrate(
            objpoints, imgpoints, FRAME_SIZE, K, D, rvecs, tvecs,
            flags=cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC,
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-6)
        )

        print("\n🎉 Calibration successful!")
        os.makedirs(os.path.dirname(CAMERA_MATRIX_FILE), exist_ok=True)
        np.save(CAMERA_MATRIX_FILE, K)
        np.save(DIST_COEFF_FILE, D)
        
        message = f"✅ Fisheye calibration successful! Saved camera_matrix.npy and dist_coeff.npy"
        print(message)
        return True, message

    except cv2.error as e:
        message = f"Fisheye calibration failed with an OpenCV error: {e}"
        print(f"ERROR: {message}")
        return False, message


def quick_undistort_video(video_path, output_dir="static/uploads"):
    """
    Performs a fast undistortion directly to an MP4 file without re-encoding.
    INCLUDES ROTATION: Rotates output 90 degrees clockwise (Portrait).
    """
    if not os.path.exists(CAMERA_MATRIX_FILE) or not os.path.exists(DIST_COEFF_FILE):
        return False, "Calibration data not found. Please run fisheye calibration first.", None

    K, D = np.load(CAMERA_MATRIX_FILE), np.load(DIST_COEFF_FILE)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Error opening video file.", None

    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    DIM = (width, height)
    
    # SWAP Dimensions for Portrait Output
    OUTPUT_DIM = (height, width)

    output_filename = "quick_undistorted_" + os.path.basename(video_path)
    output_path = os.path.join(output_dir, output_filename)
    
    balance = 0.0
    new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(K, D, DIM, np.eye(3), balance=balance)
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), new_K, DIM, cv2.CV_16SC2)
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, OUTPUT_DIM)

    if not out.isOpened():
        return False, "Failed to initialize VideoWriter for quick process.", None

    while True:
        ret, frame = cap.read()
        if not ret: break
        undistorted_frame = cv2.remap(frame, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        # Rotate 90 degrees Clockwise
        rotated_frame = cv2.rotate(undistorted_frame, cv2.ROTATE_90_CLOCKWISE)
        out.write(rotated_frame)
    
    cap.release()
    out.release()
    
    return True, "Quick video processing complete. Ready for download.", os.path.basename(output_path)


def undistort_video(video_path, output_dir="static/uploads"):
    """
    Undistorts a video file and re-encodes it for web compatibility.
    INCLUDES ROTATION: Rotates output 90 degrees clockwise (Portrait).
    """
    if not os.path.exists(CAMERA_MATRIX_FILE) or not os.path.exists(DIST_COEFF_FILE):
        return False, "Calibration data not found. Please run fisheye calibration first.", None

    K, D = np.load(CAMERA_MATRIX_FILE), np.load(DIST_COEFF_FILE)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False, "Error opening video file.", None

    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    DIM = (width, height)
    
    # SWAP Dimensions for Portrait Output
    OUTPUT_DIM = (height, width)
    
    raw_output_filename = "raw_undistorted_" + os.path.basename(video_path)
    raw_output_path = os.path.join(output_dir, raw_output_filename)

    balance = 0.0
    new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(K, D, DIM, np.eye(3), balance=balance)
    map1, map2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), new_K, DIM, cv2.CV_16SC2)

    fourcc_raw = cv2.VideoWriter_fourcc(*'mp4v') 
    out_raw = cv2.VideoWriter(raw_output_path, fourcc_raw, fps, OUTPUT_DIM)

    if not out_raw.isOpened():
        print("❌ ERROR: Could not initialize the intermediate VideoWriter. Check OpenCV/ffmpeg installation.")
        cap.release()
        return False, "Failed to create intermediate video file.", None

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        undistorted_frame = cv2.remap(frame, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        # Rotate 90 degrees Clockwise
        rotated_frame = cv2.rotate(undistorted_frame, cv2.ROTATE_90_CLOCKWISE)
        out_raw.write(rotated_frame)
    
    cap.release()
    out_raw.release()

    web_output_filename = "web_undistorted_" + os.path.basename(video_path)
    web_output_path = os.path.join(output_dir, web_output_filename)
    
    print(f"Re-encoding for web playback...")
    
    command = [
        'ffmpeg',
        '-y',
        '-i', raw_output_path,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-pix_fmt', 'yuv420p',
        web_output_path
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        print("✅ Web encoding successful!")
        
        os.remove(raw_output_path)

        return True, "Video processed successfully.", os.path.basename(web_output_path)

    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR: ffmpeg re-encoding failed.")
        print(f"ffmpeg stdout: {e.stdout}")
        print(f"ffmpeg stderr: {e.stderr}")
        os.remove(raw_output_path)
        return False, "Video conversion for web playback failed.", None

def undistort_image(image_path):
    """
    Undistorts a single image using the saved calibration matrices.
    INCLUDES ROTATION: Rotates output 90 degrees clockwise (Portrait).
    Returns (Success, Message, Path to new image).
    """
    if not os.path.exists(CAMERA_MATRIX_FILE) or not os.path.exists(DIST_COEFF_FILE):
        return False, "Calibration data not found.", None

    try:
        K = np.load(CAMERA_MATRIX_FILE)
        D = np.load(DIST_COEFF_FILE)
        
        img = cv2.imread(image_path)
        if img is None:
            return False, "Failed to load image for undistortion.", None

        h, w = img.shape[:2]
        DIM = (w, h)
        
        # Estimate new camera matrix
        new_K = cv2.fisheye.estimateNewCameraMatrixForUndistortRectify(K, D, DIM, np.eye(3), balance=0.0)
        map1, map2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), new_K, DIM, cv2.CV_16SC2)
        
        # Remap (undistort)
        undistorted_img = cv2.remap(img, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        
        # Rotate 90 degrees Clockwise
        rotated_img = cv2.rotate(undistorted_img, cv2.ROTATE_90_CLOCKWISE)
        
        # Save output with 'undistorted_' prefix in the same directory
        dir_name, file_name = os.path.split(image_path)
        output_filename = "undistorted_" + file_name
        output_path = os.path.join(dir_name, output_filename)
        
        cv2.imwrite(output_path, rotated_img)
        return True, "Image undistorted successfully.", output_path

    except Exception as e:
        print(f"ERROR in undistort_image: {e}")
        return False, str(e), None