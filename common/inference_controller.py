import cv2
import numpy as np
from tflite_runtime.interpreter import Interpreter
from tqdm import tqdm
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# --- Configuration ---
HEIGHT = 256
WIDTH = 448
SEQ_LEN = 8
IN_CHANNELS = (SEQ_LEN + 1) * 3
BATCH_SIZE = 8
TFLITE_MODEL_PATH = 'tracknet_trained.int8.tflite' # Assumes model is in the root project dir

def get_object_center(heatmap):
    """Calculates the center of the largest contour in a binary heatmap."""
    h_pred = (heatmap > 0.5).astype(np.uint8) * 255
    if np.sum(h_pred) == 0:
        return 0, 0
    cnts, _ = cv2.findContours(h_pred, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return 0, 0
    largest_contour = max(cnts, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(largest_contour)
    cx_pred = int(x + w / 2)
    cy_pred = int(y + h / 2)
    return cx_pred, cy_pred

def _preprocess_sequence(seq, width, height):
    """Preprocess a sequence of frames (resize and concatenate)."""
    frames = [cv2.resize(img, (width, height)) for img in seq]
    concat = np.concatenate(frames, axis=2)
    return concat

def _postprocess_frame(args):
    """Post-process a single frame: find center, draw circle, prepare CSV line."""
    frame, heatmap, frame_idx, ratio = args
    if heatmap is None:
        # Last frame case - no prediction
        return None
    
    img = frame.copy()
    cx_pred, cy_pred = get_object_center(heatmap)
    cx_pred_orig, cy_pred_orig = int(ratio * cx_pred), int(ratio * cy_pred)
    vis = 1 if cx_pred > 0 or cy_pred > 0 else 0
    
    if vis == 1:
        cv2.circle(img, (cx_pred_orig, cy_pred_orig), 5, (0, 0, 255), -1)
    
    csv_line = f'{frame_idx},{vis},{cx_pred_orig},{cy_pred_orig}\n'
    return img, csv_line

def run_inference_on_video(input_video_path, output_dir):
    """
    Runs TFLite inference on a single video file and saves the output.
    Returns (True, output_video_path, output_csv_path) on success,
    or (False, error_message, None) on failure.
    """
    
    # --- 1. Generate Output Paths ---
    base_filename = os.path.basename(input_video_path)
    output_filename = f"inferred_{base_filename}"
    output_video_path = os.path.join(output_dir, output_filename)
    output_csv_path = os.path.join(output_dir, f"inferred_{os.path.splitext(base_filename)[0]}.csv")

    # --- 2. Initialize TFLite Interpreter ---
    try:
        interpreter = Interpreter(model_path=TFLITE_MODEL_PATH)
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        print(f"--- TFLite model loaded: {TFLITE_MODEL_PATH} ---")
    except Exception as e:
        error_msg = f"Error loading TFLite model: {e}. Make sure '{TFLITE_MODEL_PATH}' is in the root directory."
        print(f"❌ {error_msg}")
        return False, error_msg, None # <-- MODIFIED

    # --- 3. Initialize Video Capture and Writer ---
    cap = cv2.VideoCapture(input_video_path)
    if not cap.isOpened():
        error_msg = f"Error: Could not open video file {input_video_path}"
        print(f"❌ {error_msg}")
        return False, error_msg, None # <-- MODIFIED
        
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    original_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    original_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ratio = original_h / HEIGHT
    image_num_frame = SEQ_LEN + 1 # This is 9

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_video_path, fourcc, fps, (original_w, original_h))
    if not out.isOpened():
        error_msg = f"Error: Could not create output video writer at {output_video_path}"
        print(f"❌ {error_msg}")
        cap.release()
        return False, error_msg, None # <-- MODIFIED

    # --- 4. Initialize CSV Output ---
    try:
        with open(output_csv_path, 'w') as f_csv:
            f_csv.write('Frame,Visibility,X,Y\n')
    except Exception as e:
        error_msg = f"Error: Could not write to CSV file {output_csv_path}: {e}"
        print(f"❌ {error_msg}")
        cap.release()
        out.release()
        return False, error_msg, None # <-- MODIFIED

    # --- 5. Main Processing Loop (with parallel processing) ---
    print(f"--- Starting inference on {input_video_path} ---")
    frame_count = 0
    pbar = tqdm(total=total_frames, desc=f"Inferring {base_filename}")
    
    # Determine number of worker threads (use CPU count, but cap at 4 for memory efficiency)
    import multiprocessing
    num_workers = min(4, multiprocessing.cpu_count())
    
    video_ended = False
    try:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            while True:
                frame_queue = []
                if not video_ended:
                    for _ in range(image_num_frame * BATCH_SIZE):
                        success, frame = cap.read()
                        if not success:
                            video_ended = True
                            break
                        frame_queue.append(frame)
                
                if not frame_queue:
                    break 

                num_full_sequences = len(frame_queue) // image_num_frame
                if num_full_sequences == 0:
                    pbar.update(len(frame_queue))
                    break 

                frames_to_process_count = num_full_sequences * image_num_frame
                process_queue = frame_queue[:frames_to_process_count]
                frames_discarded_at_end = len(frame_queue) - frames_to_process_count

                # Parallel preprocessing: resize and concatenate sequences
                sequences = [process_queue[i:i+image_num_frame] 
                           for i in range(0, len(process_queue), image_num_frame)]
                preprocess_func = partial(_preprocess_sequence, width=WIDTH, height=HEIGHT)
                batch_input_list = list(executor.map(preprocess_func, sequences))

                if not batch_input_list:
                    if video_ended:
                        pbar.update(len(frame_queue))
                    break 

                batch_input = np.array(batch_input_list, dtype=np.float32) / 255.0

                # Model inference (keep sequential - TFLite may not be thread-safe)
                interpreter.resize_tensor_input(input_details[0]['index'], batch_input.shape)
                interpreter.allocate_tensors()
                interpreter.set_tensor(input_details[0]['index'], batch_input)
                interpreter.invoke()
                y_pred = interpreter.get_tensor(output_details[0]['index'])
                h_pred = np.transpose(y_pred, (0, 3, 1, 2)).reshape(-1, HEIGHT, WIDTH)
                
                # Prepare post-processing tasks (parallel) - only for frames with predictions
                postprocess_tasks = []
                frame_order = []  # Track order: (frame_idx, is_last_frame, queue_idx)
                
                for b in range(num_full_sequences):
                    # Process frames 0-7 (with predictions)
                    for f in range(SEQ_LEN):
                        pred_idx = b * SEQ_LEN + f
                        frame_idx_in_queue = b * image_num_frame + f
                        frame_idx_global = frame_count + frame_idx_in_queue
                        postprocess_tasks.append((
                            process_queue[frame_idx_in_queue],
                            h_pred[pred_idx],
                            frame_idx_global,
                            ratio
                        ))
                        frame_order.append((frame_idx_global, False, frame_idx_in_queue))
                    
                    # Track last frame (9th frame) - no prediction
                    last_frame_idx_in_queue = b * image_num_frame + SEQ_LEN
                    last_frame_idx_global = frame_count + last_frame_idx_in_queue
                    frame_order.append((last_frame_idx_global, True, last_frame_idx_in_queue))
                
                # Parallel post-processing (only for frames with predictions)
                results = list(executor.map(_postprocess_frame, postprocess_tasks))
                
                # Write results sequentially (maintain order for video/CSV)
                result_idx = 0
                csv_lines = []
                
                for frame_idx_global, is_last_frame, queue_idx in frame_order:
                    if is_last_frame:
                        # Last frame - no prediction
                        img = process_queue[queue_idx].copy()
                        csv_lines.append(f'{frame_idx_global},0,0,0\n')
                        out.write(img)
                    else:
                        # Frame with prediction
                        img, csv_line = results[result_idx]
                        csv_lines.append(csv_line)
                        out.write(img)
                        result_idx += 1
                
                # Write CSV lines in batch (faster than individual writes)
                if csv_lines:
                    with open(output_csv_path, 'a') as f_csv:
                        f_csv.writelines(csv_lines)

                frame_count += len(process_queue)
                pbar.update(len(process_queue))
                if video_ended and frames_discarded_at_end > 0:
                    pbar.update(frames_discarded_at_end)
                if video_ended:
                    break
    
    except Exception as e:
        error_msg = f"Error during inference loop: {e}"
        print(f"❌ {error_msg}")
        pbar.close()
        cap.release()
        out.release()
        return False, error_msg, None # <-- MODIFIED

    # --- 6. Cleanup ---
    pbar.close()
    cap.release()
    out.release()
    print(f"\n--- TFLite Inference Complete ---")
    print(f"Total frames processed: {frame_count}")
    print(f"✅ Output video saved to: {output_video_path}")
    print(f"✅ Output CSV saved to: {output_csv_path}")
    
    # Return the *full filesystem paths*
    return True, output_video_path, output_csv_path # <-- MODIFIED