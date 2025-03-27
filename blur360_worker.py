#!/usr/bin/env python3
"""
Worker script til baggrundsbehandling af 360° videofiler med ansigts- og nummerpladegenkendelse.
Kører som en separat proces, startet af Flask-applikationen.
Bruger multiprocessing til parallel behandling af videoframes.
"""

import os
import sys
import cv2
import json
import time
import numpy as np
import logging
import argparse
import multiprocessing as mp
from multiprocessing import Pool, cpu_count
from pathlib import Path
import traceback

# Forsøg at importere Ultralytics YOLO
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
    print("Ultralytics YOLO detected and available.")
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    print("Ultralytics YOLO not available. Will use OpenCV DNN if possible.")

# Konfiguration af logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [Worker] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('blur360_worker')

# Standard stier
UPLOAD_FOLDER = "uploads"
PROCESSED_FOLDER = "processed"
MODEL_FOLDER = "models"
STATUS_FOLDER = "status"

# Sikrer at alle nødvendige mapper findes
for folder in [UPLOAD_FOLDER, PROCESSED_FOLDER, MODEL_FOLDER, STATUS_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# Funktion til at opdatere job status
def update_job_status(job_id, progress, message, status="processing"):
    """Opdaterer status for et job ved at skrive til en JSON-fil"""
    status_file = os.path.join(STATUS_FOLDER, f"{job_id}.json")
    status_data = {
        "job_id": job_id,
        "progress": progress,
        "message": message,
        "status": status,
        "timestamp": time.time()
    }
    
    try:
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
        logger.info(f"Job {job_id}: {progress}% - {message}")
    except Exception as e:
        logger.error(f"Error updating job status: {e}")

# Funktion til at håndtere wrap-around detektion for 360° billeder
def wrap_frame_for_detection(frame):
    """
    Tilføjer wrap-around-padding i siderne af et equirectangular 360°-billede.
    Dette forbedrer detektion nær venstre og højre kant.
    """
    height, width = frame.shape[:2]
    pad_w = width // 4  # 25% padding

    left = frame[:, -pad_w:]   # Sidste 25%
    right = frame[:, :pad_w]   # Første 25%
    wrapped = np.hstack([left, frame, right])

    return wrapped, pad_w

def adjust_coords_for_wrapped_detections(detections, pad_w, original_width):
    """
    Justerer koordinater fra wrap'et billede tilbage til originalt koordinatsystem.
    Filtrerer samtidig dem der falder helt uden for det oprindelige billede.
    """
    adjusted = []
    for (x, y, w, h) in detections:
        x -= pad_w  # Justér X-koordinat
        if x + w < 0 or x > original_width:
            continue  # Uden for billedet
        x = max(0, x)
        w = min(original_width - x, w)
        adjusted.append((x, y, w, h))
    return adjusted

def load_dnn_models():
    """Load DNN-based detector models if available"""
    models_dir = Path(MODEL_FOLDER)
    models_dir.mkdir(exist_ok=True)
    
    models = {
        "face_detector": None,          # OpenCV DNN face detector (older)
        "plate_detector": None,         # Not used anymore
        "yolov8_plate_detector": None,  # YOLO license plate detector
        "yolov8_face_detector": None,   # NEW: YOLO face detector
        "detector_types": {
            "face": "None",
            "plate": "None"
        }
    }
    
    # === YOLOv8 Face Detection Model (Primary) ===
    # Check for Ultralytics YOLOv8 model for faces
    yolov8_face_path = models_dir / "yolov8n_face.pt"
    if ULTRALYTICS_AVAILABLE and yolov8_face_path.exists():
        try:
            # Load YOLOv8 face model
            yolo_face_model = YOLO(str(yolov8_face_path))
            models["yolov8_face_detector"] = yolo_face_model
            models["detector_types"]["face"] = "YOLOv8"
            logger.info("Loaded YOLOv8 face detector (Ultralytics)")
        except Exception as e:
            logger.error(f"Failed to load YOLOv8 face detector: {e}")
    
    # === OpenCV DNN Face Detection Model (Fallback) ===
    # Only use if YOLO face detector is not available
    if models["yolov8_face_detector"] is None:
        face_config_path = models_dir / "deploy.prototxt"
        face_model_path = models_dir / "res10_300x300_ssd_iter_140000.caffemodel"
        
        if face_config_path.exists() and face_model_path.exists():
            try:
                face_net = cv2.dnn.readNetFromCaffe(str(face_config_path), str(face_model_path))
                models["face_detector"] = face_net
                models["detector_types"]["face"] = "OpenCV DNN SSD (Fallback)"
                logger.info("Loaded OpenCV DNN face detector as fallback (SSD/Caffe)")
            except Exception as e:
                logger.error(f"Failed to load OpenCV DNN face detector: {e}")
        else:
            logger.warning(f"Neither YOLO nor OpenCV face detection models found in {models_dir}")
            logger.warning("For face detection, download models with: python download_models.py")
    
    # === YOLOv8 License Plate Detection Model ===
    yolov8_model_path = models_dir / "yolov8n_lp.pt"
    if ULTRALYTICS_AVAILABLE and yolov8_model_path.exists():
        try:
            # Load YOLOv8 license plate model
            yolo_model = YOLO(str(yolov8_model_path))
            models["yolov8_plate_detector"] = yolo_model
            models["detector_types"]["plate"] = "YOLOv8"
            logger.info("Loaded YOLOv8 license plate detector (Ultralytics)")
        except Exception as e:
            logger.error(f"Failed to load YOLOv8 license plate detector: {e}")
    
    # Check if license plate detection is available
    if models["yolov8_plate_detector"] is None:
        models["detector_types"]["plate"] = "Not available"
        logger.warning(f"YOLOv8 license plate model not found in {models_dir}")
        logger.warning("For license plate detection, download YOLOv8 model with: python download_models.py")
    
    # Print summary of loaded models
    logger.info("\n=== DETECTION MODELS SUMMARY ===")
    logger.info(f"Face detection: {models['detector_types']['face']}")
    logger.info(f"License plate detection: {models['detector_types']['plate']}")
    logger.info("===============================\n")
        
    return models

def compute_iou(box1, box2):
    """Compute Intersection over Union between two boxes"""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    
    # Calculate intersection coordinates
    xx1 = max(x1, x2)
    yy1 = max(y1, y2)
    xx2 = min(x1 + w1, x2 + w2)
    yy2 = min(y1 + h1, y2 + h2)
    
    # Check if there is an intersection
    if xx2 < xx1 or yy2 < yy1:
        return 0.0
        
    # Calculate areas
    intersection_area = (xx2 - xx1) * (yy2 - yy1)
    box1_area = w1 * h1
    box2_area = w2 * h2
    union_area = box1_area + box2_area - intersection_area
    
    # Return IoU
    return intersection_area / union_area if union_area > 0 else 0.0

def detect_objects(frame, frame_info, models, debug_mode=False):
    """
    Detecterer ansigter og nummerplader i en frame
    
    Args:
        frame: Billedet der skal analyseres
        frame_info: Dict med info om framen (index, width, height)
        models: Loaded detection models
        debug_mode: Om debug-visning skal aktiveres
        
    Returns:
        List af detektioner i format (x, y, w, h)
    """
    all_detections = []
    
    # Tilføj wrap-around padding til billedet for bedre kantdetektion
    wrapped_frame, pad_w = wrap_frame_for_detection(frame)
    original_width = frame.shape[1]
    
    # ANSIGTSDETEKTERING
    
    # Forsøg først med YOLOv8 (bedste metode)
    yolov8_face_detector = models["yolov8_face_detector"]
    
    if yolov8_face_detector is not None:
        try:
            # Kør YOLOv8 på original frame
            results = yolov8_face_detector(frame, conf=0.35, verbose=False)  # Lavere confidence for flere detektioner
            
            for result in results:
                for i, box in enumerate(result.boxes.xyxy.cpu().numpy()):
                    x1, y1, x2, y2 = box[:4]
                    # Konverter til x, y, w, h format
                    x, y, w, h = int(x1), int(y1), int(x2-x1), int(y2-y1)
                    all_detections.append((x, y, w, h))
                    
            # Kør også YOLOv8 på wrapped frame for at fange ansigter ved kanterne
            wrapped_results = yolov8_face_detector(wrapped_frame, conf=0.35, verbose=False)
            wrapped_detections = []
            
            for result in wrapped_results:
                for i, box in enumerate(result.boxes.xyxy.cpu().numpy()):
                    x1, y1, x2, y2 = box[:4]
                    # Konverter til x, y, w, h format
                    x, y, w, h = int(x1), int(y1), int(x2-x1), int(y2-y1)
                    wrapped_detections.append((x, y, w, h))
                    
            # Juster koordinater for wrapped frame detektioner
            adjusted_wrapped_detections = adjust_coords_for_wrapped_detections(
                wrapped_detections, pad_w, original_width
            )
            
            # Tilføj de justerede wrapped detektioner
            all_detections.extend(adjusted_wrapped_detections)
            
        except Exception as e:
            logger.error(f"Error in YOLOv8 face detection: {e}")
            # Fall back to OpenCV DNN face detector if available
            yolov8_face_detector = None
    
    # Fall back to OpenCV DNN if YOLO is not available
    dnn_face_detector = models["face_detector"]
    if yolov8_face_detector is None and dnn_face_detector is not None:
        try:
            # Process at multiple scales for better detection
            scales = [1.0, 0.75, 1.25]
            height, width = frame.shape[:2]
            
            for scale in scales:
                current_height = int(height * scale)
                current_width = int(width * scale)
                
                # Skip invalid scales
                if current_height <= 0 or current_width <= 0:
                    continue
                
                # Resize frame for current scale
                resized_frame = cv2.resize(frame, (current_width, current_height))
                
                # Prepare image for DNN
                blob = cv2.dnn.blobFromImage(
                    cv2.resize(resized_frame, (300, 300)), 
                    1.0, (300, 300), 
                    (104.0, 177.0, 123.0),
                    swapRB=False
                )
                
                dnn_face_detector.setInput(blob)
                detections = dnn_face_detector.forward()
                
                # Process DNN detections
                for i in range(0, detections.shape[2]):
                    confidence = detections[0, 0, i, 2]
                    if confidence > 0.4:  # Confidence threshold
                        box = detections[0, 0, i, 3:7] * np.array([current_width, current_height, current_width, current_height])
                        (startX, startY, endX, endY) = box.astype("int")
                        
                        # Scale back to original dimensions
                        startX = int(startX / scale)
                        startY = int(startY / scale)
                        endX = int(endX / scale)
                        endY = int(endY / scale)
                        
                        # Ensure coordinates are within bounds
                        startX = max(0, startX)
                        startY = max(0, startY)
                        endX = min(width, endX)
                        endY = min(height, endY)
                        
                        # Skip invalid detections
                        if startX >= endX or startY >= endY:
                            continue
                            
                        # Convert to x, y, w, h format
                        x, y, w, h = startX, startY, endX - startX, endY - startY
                        all_detections.append((x, y, w, h))
                
            # Also process wrapped frame
            wrapped_blob = cv2.dnn.blobFromImage(
                cv2.resize(wrapped_frame, (300, 300)), 
                1.0, (300, 300), 
                (104.0, 177.0, 123.0),
                swapRB=False
            )
            
            dnn_face_detector.setInput(wrapped_blob)
            wrapped_detections = dnn_face_detector.forward()
            
            # Process wrapped frame detections
            dnn_wrapped_detections = []
            for i in range(0, wrapped_detections.shape[2]):
                confidence = wrapped_detections[0, 0, i, 2]
                if confidence > 0.4:
                    box = wrapped_detections[0, 0, i, 3:7] * np.array([300, 300, 300, 300])
                    box = box * np.array([wrapped_frame.shape[1]/300, wrapped_frame.shape[0]/300, 
                                         wrapped_frame.shape[1]/300, wrapped_frame.shape[0]/300])
                    
                    (startX, startY, endX, endY) = box.astype("int")
                    x, y, w, h = startX, startY, endX - startX, endY - startY
                    dnn_wrapped_detections.append((x, y, w, h))
            
            # Adjust coordinates for wrapped detections
            adjusted_wrapped_detections = adjust_coords_for_wrapped_detections(
                dnn_wrapped_detections, pad_w, original_width
            )
            
            # Add to all detections
            all_detections.extend(adjusted_wrapped_detections)
            
        except Exception as e:
            logger.error(f"Error in OpenCV DNN face detection: {e}")
    
    # NUMMERPLADEDETEKTION

    # Using YOLOv8-based license plate detection
    yolov8_plate_detector = models["yolov8_plate_detector"]
    if yolov8_plate_detector is not None:
        try:
            # Run YOLOv8 detection on both original and wrapped frames
            yolo_results = yolov8_plate_detector(frame, conf=0.55)  # High confidence for fewer false positives
            
            # Process results from original frame
            for result in yolo_results:
                for box in result.boxes.xyxy.cpu().numpy():
                    x1, y1, x2, y2 = box[:4]
                    # Convert to xywh format
                    x, y, w, h = int(x1), int(y1), int(x2-x1), int(y2-y1)
                    all_detections.append((x, y, w, h))
            
            # Process wrapped frame
            wrapped_yolo_results = yolov8_plate_detector(wrapped_frame, conf=0.55)
            wrapped_yolo_plates = []
            
            for result in wrapped_yolo_results:
                for box in result.boxes.xyxy.cpu().numpy():
                    x1, y1, x2, y2 = box[:4]
                    # Convert to xywh format
                    x, y, w, h = int(x1), int(y1), int(x2-x1), int(y2-y1)
                    wrapped_yolo_plates.append((x, y, w, h))
            
            # Adjust coordinates for wrapped detections
            adjusted_wrapped_plates = adjust_coords_for_wrapped_detections(
                wrapped_yolo_plates, pad_w, original_width
            )
            
            # Add to detections
            all_detections.extend(adjusted_wrapped_plates)
            
        except Exception as e:
            logger.error(f"Error in YOLOv8 license plate detection: {e}")
    
    # Apply Non-Maximum Suppression to merge overlapping detections
    merged_detections = []
    used_indices = set()
    
    for i, detection1 in enumerate(all_detections):
        if i in used_indices:
            continue
            
        x1, y1, w1, h1 = detection1
        merged_box = [x1, y1, w1, h1]
        used_indices.add(i)
        
        for j, detection2 in enumerate(all_detections):
            if j in used_indices or i == j:
                continue
                
            x2, y2, w2, h2 = detection2
            
            # If IoU is high enough, merge the boxes
            iou = compute_iou(detection1, detection2)
            if iou > 0.3:  # Overlap threshold
                # Create a bounding box that includes both detections
                merged_x = min(x1, x2)
                merged_y = min(y1, y2)
                merged_w = max(x1 + w1, x2 + w2) - merged_x
                merged_h = max(y1 + h1, y2 + h2) - merged_y
                
                merged_box = [merged_x, merged_y, merged_w, merged_h]
                used_indices.add(j)
        
        merged_detections.append(tuple(merged_box))
    
    # Debug info
    if len(merged_detections) > 0:
        logger.debug(f"Frame {frame_info['index']}: Found {len(merged_detections)} objects to blur")
    
    return merged_detections

def process_frame(args):
    """
    Processer en enkelt frame med detektion og sløring.
    Designet til at køres i parallelle processer.
    
    Args:
        args: Tuple med (frame_info, input_path, output_path, job_id, models, debug_mode)
        
    Returns:
        Dict med frame index og status
    """
    frame_info, input_path, output_path, job_id, models_data, debug_mode = args
    
    try:
        # Læs model data fra disk (deles ikke direkte mellem processer)
        if isinstance(models_data, str):
            with open(models_data, 'r') as f:
                model_paths = json.load(f)
                
            # Genindlæs modeller i hver proces
            models = load_dnn_models()
        else:
            models = models_data
        
        # Åbn video
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {input_path}")
            
        # Gå til den rette frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_info['index'])
        success, frame = cap.read()
        
        if not success:
            raise IOError(f"Failed to read frame {frame_info['index']} from video")
            
        # Detecter objekter
        detections = detect_objects(frame, frame_info, models, debug_mode)
        
        # Slør detektioner
        for i, (x, y, w, h) in enumerate(detections):
            # Validate detection coordinates
            if x < 0 or y < 0 or w <= 0 or h <= 0:
                continue
                
            # Add padding around detection for better coverage
            padding = int(w * 0.1)  # 10% padding
            x_padded = max(0, x - padding)
            y_padded = max(0, y - padding)
            w_padded = min(frame.shape[1] - x_padded, w + 2*padding)
            h_padded = min(frame.shape[0] - y_padded, h + 2*padding)
            
            # Check if coordinates are valid after padding
            if w_padded <= 0 or h_padded <= 0:
                continue
                
            # Extract region of interest
            try:
                roi = frame[y_padded:y_padded+h_padded, x_padded:x_padded+w_padded]
                if roi.size == 0:  # Skip if ROI is empty
                    continue
                
                # Adjust blur kernel size based on detection size
                kernel_size = max(51, int(min(w_padded, h_padded) * 0.8))
                # Make kernel size odd
                kernel_size = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
                
                # Apply heavy blur with improved algorithm
                try:
                    # Use a combination of Gaussian and median blur for better results
                    if max(w_padded, h_padded) > 100:  # For larger areas
                        # For larger areas, use a stronger blur
                        blur1 = cv2.GaussianBlur(roi, (kernel_size, kernel_size), 30)
                        blur2 = cv2.medianBlur(blur1, min(kernel_size, 99))  # MedianBlur kernel must be <= 99
                        blur = cv2.GaussianBlur(blur2, (kernel_size, kernel_size), 30)
                    else:
                        # For smaller areas, use a simpler blur to avoid artifacts
                        blur = cv2.GaussianBlur(roi, (kernel_size, kernel_size), 30)
                    
                    # Apply blur to the frame
                    frame[y_padded:y_padded+h_padded, x_padded:x_padded+w_padded] = blur
                    
                    # In debug mode, draw a colored box around the detected region
                    if debug_mode:
                        cv2.rectangle(frame, (x_padded, y_padded), 
                                    (x_padded+w_padded, y_padded+h_padded), (0, 0, 255), 2)
                except Exception as e:
                    logger.error(f"Error applying blur: {e}, roi shape: {roi.shape}, kernel: {kernel_size}")
            except Exception as e:
                logger.error(f"Error extracting ROI for detection at ({x},{y}): {e}")
        
        # Gem den behandlede frame
        frame_output_path = os.path.join(output_path, f"frame_{frame_info['index']:06d}.jpg")
        cv2.imwrite(frame_output_path, frame)
        
        # Ryd op
        cap.release()
        
        return {"index": frame_info['index'], "status": "success"}
        
    except Exception as e:
        logger.error(f"Error processing frame {frame_info['index']}: {e}")
        logger.error(traceback.format_exc())
        return {"index": frame_info['index'], "status": "error", "error": str(e)}

def extract_video_info(input_path):
    """Extract video information"""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {input_path}")
        
    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
    
    # Convert fourcc to human-readable format
    fourcc_chars = [chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]
    fourcc_str = ''.join(fourcc_chars)
    
    # Get total duration
    duration_sec = frame_count / fps if fps > 0 else 0
    
    cap.release()
    
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
        "fourcc": fourcc_str,
        "duration": duration_sec,
        "duration_formatted": f"{int(duration_sec // 60)}:{int(duration_sec % 60):02d}"
    }

def process_video(job_id, input_path, output_path, debug_mode=False, use_dnn=True):
    """
    Hovedfunktion til at processere en video med parallel multiprocessing
    
    Args:
        job_id: Unikt job ID
        input_path: Sti til inputvideo
        output_path: Sti til outputvideo
        debug_mode: Om debug-visning skal aktiveres
        use_dnn: Om DNN-modeller skal bruges
    """
    start_time = time.time()
    logger.info(f"Starting job {job_id} - Processing {input_path} to {output_path}")
    update_job_status(job_id, 5, "Analyzing video", "processing")
    
    try:
        # Opret output mappe
        frames_dir = os.path.join(PROCESSED_FOLDER, f"{job_id}_frames")
        os.makedirs(frames_dir, exist_ok=True)
        
        # Hent video information
        video_info = extract_video_info(input_path)
        logger.info(f"Video: {video_info['width']}x{video_info['height']} pixels, {video_info['fps']} FPS, {video_info['frame_count']} frames")
        update_job_status(job_id, 10, f"Video loaded: {video_info['width']}x{video_info['height']}, {video_info['duration_formatted']} duration")
        
        # Indlæs detektionsmodeller
        update_job_status(job_id, 15, "Loading detection models", "processing")
        models = load_dnn_models() if use_dnn else None
        
        # Opret frameliste til parallel processering
        frames = []
        for i in range(video_info['frame_count']):
            frames.append({
                "index": i,
                "width": video_info['width'],
                "height": video_info['height']
            })
            
        # Giv et indledende tidsestimat baseret på videovarighed
        total_frames = video_info['frame_count']
        video_duration = video_info['duration']
        # Estimer omkring 1.5x videolængden til behandling
        estimated_seconds = video_duration * 1.5
        
        if estimated_seconds > 60:
            time_msg = f"{int(estimated_seconds // 60)} min {int(estimated_seconds % 60)} sec remaining"
        else:
            time_msg = f"{int(estimated_seconds)} sec remaining"
            
        # Updater med et indledende estimat
        update_job_status(
            job_id, 
            16,  # Lige efter modellerne er indlæst
            f"Starting processing. Initial estimate: {time_msg}",
            "processing"
        )
        
        # Bestem antal parallelle processer (max 80% af tilgængelige kerner)
        num_cores = cpu_count()
        num_processes = max(1, int(num_cores * 0.8))
        core_info = f"Running with {num_processes} parallel processes (of {num_cores} available cores)"
        logger.info(f"CPU INFO: {core_info}")
        
        # Udskriv fremhævet information til terminal
        print("\n" + "="*60)
        print(f"=== CPU UTILIZATION ===")
        print(f"=== {core_info} ===")
        print("="*60 + "\n")
        
        # Opdel frames i batches for at spare hukommelse og give bedre fremskridtsopdateringer
        batch_size = min(100, max(1, video_info['frame_count'] // 10))  # Højst 10 batches, men mindst 1 pr. frame
        frame_batches = [frames[i:i+batch_size] for i in range(0, len(frames), batch_size)]
        logger.info(f"Split processing into {len(frame_batches)} batches with ~{batch_size} frames each")
        
        # Gennemløb hver batch
        total_processed = 0
        
        for batch_idx, batch in enumerate(frame_batches):
            batch_start = time.time()
            logger.info(f"Processing batch {batch_idx+1}/{len(frame_batches)} ({len(batch)} frames)")
            update_job_status(
                job_id, 
                15 + int(80 * total_processed / video_info['frame_count']),
                f"Processing frames {total_processed+1}-{total_processed+len(batch)} of {video_info['frame_count']}", 
                "processing"
            )
            
            # Opret argumenter til hver process
            process_args = []
            for frame_info in batch:
                process_args.append((frame_info, input_path, frames_dir, job_id, models, debug_mode))
            
            # Kør parallel processering med multiprocessing
            with Pool(processes=num_processes) as pool:
                results = pool.map(process_frame, process_args)
            
            # Tjek resultater
            success_count = sum(1 for r in results if r['status'] == 'success')
            error_count = sum(1 for r in results if r['status'] == 'error')
            logger.info(f"Batch {batch_idx+1} complete: {success_count} successes, {error_count} errors")
            
            # Opdater total
            total_processed += len(batch)
            
            # Beregn tid og fremskridt
            batch_time = time.time() - batch_start
            frames_per_second = len(batch) / batch_time if batch_time > 0 else 0
            progress = int(15 + 80 * total_processed / video_info['frame_count'])
            
            # Estimer resterende tid med større præcision
            elapsed_time = time.time() - start_time
            overall_fps = total_processed / elapsed_time if elapsed_time > 0 else 0
            
            # Brug et glidende gennemsnit af frames per second for mere stabil estimering
            # Vægt nyere målinger højere (75% nuværende batch, 25% globalt gennemsnit)
            weighted_fps = (0.75 * frames_per_second) + (0.25 * overall_fps) if overall_fps > 0 else frames_per_second
            
            remaining_frames = video_info['frame_count'] - total_processed
            estimated_remaining_time = remaining_frames / weighted_fps if weighted_fps > 0 else 0
            
            # Opdater status med tidsestimat
            if estimated_remaining_time > 60:
                time_msg = f"{int(estimated_remaining_time // 60)} min {int(estimated_remaining_time % 60)} sec remaining"
            else:
                time_msg = f"{int(estimated_remaining_time)} sec remaining"
                
            # Log tidsestimatet
            logger.info(f"Processing rate: {frames_per_second:.1f} FPS (batch), {overall_fps:.1f} FPS (avg), {weighted_fps:.1f} FPS (weighted)")
            logger.info(f"Estimated remaining time: {time_msg}")
            
            # Opdater med mere detaljeret status, der inkluderer FPS og ETA
            status_message = f"Processed {total_processed}/{video_info['frame_count']} frames ({frames_per_second:.1f} FPS). {time_msg}"
            
            # Yderligere nøgletal
            status_data = {
                "job_id": job_id,
                "progress": progress,
                "message": status_message,
                "status": "processing",
                "timestamp": time.time(),
                "fps": {
                    "batch": f"{frames_per_second:.1f}",
                    "avg": f"{overall_fps:.1f}",
                    "weighted": f"{weighted_fps:.1f}"
                },
                "batch": {
                    "current": batch_idx + 1,
                    "total": len(frame_batches),
                    "size": len(batch)
                },
                "frames": {
                    "processed": total_processed,
                    "total": video_info['frame_count']
                },
                "time": {
                    "elapsed": elapsed_time,
                    "remaining": estimated_remaining_time,
                    "message": time_msg
                }
            }
            
            # Gem status til fil
            status_file = os.path.join(STATUS_FOLDER, f"{job_id}.json")
            try:
                with open(status_file, 'w') as f:
                    json.dump(status_data, f)
                logger.info(f"Job {job_id}: {progress}% - {status_message}")
            except Exception as e:
                logger.error(f"Error updating job status: {e}")
                
            # Send også til Socket.IO (som tidligere - med enklere format)
            update_job_status(
                job_id, 
                progress,
                status_message,
                "processing"
            )
        
        # Når alle frames er behandlet, samles de til en video
        update_job_status(job_id, 95, "Assembling final video", "processing")
        
        # Definer output codec
        try:
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # H.264 codec
        except:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Fallback codec
            
        # Opret VideoWriter
        out = cv2.VideoWriter(
            output_path, 
            fourcc, 
            video_info['fps'], 
            (video_info['width'], video_info['height'])
        )
        
        # Tilføj hver frame til videoen i rigtig rækkefølge
        for i in range(video_info['frame_count']):
            frame_path = os.path.join(frames_dir, f"frame_{i:06d}.jpg")
            if os.path.exists(frame_path):
                frame = cv2.imread(frame_path)
                if frame is not None:
                    out.write(frame)
            else:
                logger.warning(f"Missing frame {i} - using a blank frame instead")
                # Create a blank frame as placeholder
                blank_frame = np.zeros((video_info['height'], video_info['width'], 3), np.uint8)
                out.write(blank_frame)
                
        # Luk VideoWriter
        out.release()
        
        # Ryd op i midlertidige filer
        import shutil
        shutil.rmtree(frames_dir, ignore_errors=True)
        
        # Beregn total tid
        total_time = time.time() - start_time
        logger.info(f"Job {job_id} completed in {total_time:.2f} seconds")
        
        # Markér job som afsluttet
        update_job_status(
            job_id, 
            100, 
            f"Processing complete! Total time: {int(total_time // 60)} min {int(total_time % 60)} sec", 
            "completed"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        logger.error(traceback.format_exc())
        update_job_status(job_id, 0, f"Error: {str(e)}", "error")
        return False

def main():
    """Main function for the worker script"""
    parser = argparse.ArgumentParser(description="Process 360° videos with face and license plate detection/blurring")
    parser.add_argument("--job_id", required=True, help="Unique job identifier")
    parser.add_argument("--input", required=True, help="Input video path")
    parser.add_argument("--output", required=True, help="Output video path")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode with detection visualization")
    parser.add_argument("--use_dnn", action="store_true", help="Use DNN models for detection (recommended)")
    
    args = parser.parse_args()
    
    # Process the video
    process_video(
        args.job_id,
        args.input,
        args.output,
        debug_mode=args.debug,
        use_dnn=args.use_dnn
    )

if __name__ == "__main__":
    main()