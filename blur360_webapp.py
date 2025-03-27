# Flask-baseret webtjeneste til upload og automatisk behandling af 360°-videoer
# inkl. splitting, ansigts-/nummerpladegenkendelse og sløring

from flask import Flask, request, send_file, render_template_string, jsonify, session, Response
import os
import sys
import uuid
import cv2
import subprocess
import logging
import socket
import numpy as np
import time
import threading
import json
import datetime
import inspect
import re
import configparser
from pathlib import Path
from flask_socketio import SocketIO
from flask_babel import Babel
from flask_babel import gettext as _

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [WebApp] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('blur360_webapp')
try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
    print("Ultralytics YOLO detected and available.")
except ImportError:
    ULTRALYTICS_AVAILABLE = False
    print("Ultralytics YOLO not available. Will use OpenCV DNN if possible.")

# Load configuration from config.ini if it exists
config = configparser.ConfigParser()
config_file = Path('config.ini')
if config_file.exists():
    logger.info(f"Loading configuration from {config_file}")
    config.read(config_file)
else:
    logger.info("No config.ini found, using default settings")
    # Set default configuration
    config['server'] = {
        'host': '127.0.0.1',
        'port': '5000',
        'debug': 'False'
    }
    config['processing'] = {
        'language': 'da',
        'verbose_logging': 'False'
    }
    config['cloudflare'] = {
        'enabled': 'False'
    }
    
    # Save default configuration
    with open(config_file, 'w') as f:
        config.write(f)
    logger.info(f"Created default configuration file at {config_file}")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = "uploads"
app.config['PROCESSED_FOLDER'] = "processed"
app.config['BABEL_DEFAULT_LOCALE'] = config.get('processing', 'language', fallback='da')
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'
app.config['SUPPORTED_LANGUAGES'] = {
    'da': 'Dansk',
    'en': 'English',
    'de': 'Deutsch',
    'es': 'Español',
    'it': 'Italiano',
    'bg': 'Български'
}

# Server configuration
app.config['HOST'] = config.get('server', 'host', fallback='127.0.0.1')
app.config['PORT'] = config.getint('server', 'port', fallback=5000)
app.config['DEBUG'] = config.getboolean('server', 'debug', fallback=False)

UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']
PROCESSED_FOLDER = app.config['PROCESSED_FOLDER']
MODEL_FOLDER = "models"

# Sti til status-filer fra worker-processen
STATUS_FOLDER = "status"

# Opret nødvendige mapper
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)
os.makedirs(MODEL_FOLDER, exist_ok=True)
os.makedirs(STATUS_FOLDER, exist_ok=True)

# Initialiser Socket.IO for realtids-kommunikation
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', logger=True, engineio_logger=True)

# Initialiser Babel for internationalisering
babel = Babel(app)

# Job status dict for behandlingsstatus
processing_jobs = {}

def monitor_worker_status(job_id):
    """
    Overvåger job status fra worker processen og sender Socket.IO opdateringer til klienten.
    
    Args:
        job_id: ID for jobbet der skal overvåges
    """
    if job_id not in processing_jobs:
        logger.error(f"Cannot monitor job {job_id} - not found in processing_jobs")
        return
        
    status_file = os.path.join(STATUS_FOLDER, f"{job_id}.json")
    
    # Seneste status info for at undgå at sende duplicate beskeder
    last_progress = 0
    last_message = ""
    running = True
    check_interval = 0.5  # Check hvert halve sekund
    
    while running and job_id in processing_jobs:
        try:
            # Tjek om status-filen findes
            if os.path.exists(status_file):
                with open(status_file, 'r') as f:
                    try:
                        status_data = json.load(f)
                        
                        # Hent status
                        progress = status_data.get('progress', 0)
                        message = status_data.get('message', '')
                        status = status_data.get('status', 'processing')
                        
                        # Opdater job info
                        processing_jobs[job_id]['status'] = status
                        processing_jobs[job_id]['progress'] = progress
                        processing_jobs[job_id]['message'] = message
                        
                        # Send socket.io besked hvis status har ændret sig betydeligt
                        # (undgå for mange beskeder)
                        if (abs(progress - last_progress) >= 1 or 
                            message != last_message or
                            status in ['completed', 'error']):
                            
                            # Bestem aktuel og forrige step baseret på fremskridt
                            current_step = None
                            prev_step = None
                            
                            if progress < 15:
                                current_step = 'step-analyze'
                                prev_step = 'step-upload-status'
                            elif progress < 50:
                                current_step = 'step-detect'
                                prev_step = 'step-analyze'
                            elif progress < 95:
                                current_step = 'step-blur'
                                prev_step = 'step-detect'
                            else:
                                current_step = 'step-finalize'
                                prev_step = 'step-blur'
                            
                            # Emit progress update event
                            socketio.emit('progress_update', {
                                'job_id': job_id,
                                'progress': progress,
                                'message': message,
                                'step': current_step,
                                'prev_step': prev_step
                            })
                            
                            last_progress = progress
                            last_message = message
                            
                            logger.info(f"Job {job_id}: {progress}% - {message}")
                            
                            # Hvis jobbet er færdigt eller fejlet, emit completion event
                            if status == 'completed':
                                logger.info(f"Job {job_id} completed")
                                processing_jobs[job_id]['end_time'] = time.time()
                                processing_time = processing_jobs[job_id]['end_time'] - processing_jobs[job_id]['start_time']
                                
                                socketio.emit('job_complete', {
                                    'job_id': job_id,
                                    'download_url': f'/download/{job_id}',
                                    'processing_time': processing_time
                                })
                                running = False
                                
                            elif status == 'error':
                                logger.error(f"Job {job_id} failed: {message}")
                                socketio.emit('job_error', {
                                    'job_id': job_id,
                                    'error': message
                                })
                                running = False
                                
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON in status file for job {job_id}")
                
            # Vent før næste tjek
            time.sleep(check_interval)
            
        except Exception as e:
            logger.error(f"Error monitoring job {job_id}: {e}")
            # Fortsæt overvågning selvom der er en fejl
            time.sleep(check_interval)
    
    logger.info(f"Monitoring finished for job {job_id}")
    
    # Når jobbet er færdigt, ryd op i status-filen
    try:
        if os.path.exists(status_file):
            os.remove(status_file)
    except Exception as e:
        logger.error(f"Error removing status file: {e}")

# Locale selector for Babel
def get_locale():
    # 1. Brug request parameter (fx ?lang=en)
    lang = request.args.get('lang')
    if lang and lang in app.config['SUPPORTED_LANGUAGES']:
        session['lang'] = lang
        return lang
    
    # 2. Brug sprog gemt i session
    if 'lang' in session and session['lang'] in app.config['SUPPORTED_LANGUAGES']:
        return session['lang']
    
    # 3. Brug brugerens browser-præference
    return request.accept_languages.best_match(app.config['SUPPORTED_LANGUAGES'].keys(), 
                                              app.config['BABEL_DEFAULT_LOCALE'])

# Register the locale selector function with Babel
babel.init_app(app, locale_selector=get_locale)

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

def create_tracker():
    """
    Helper function to create a tracker based on available OpenCV capabilities.
    Returns None if tracking is not supported.
    """
    try:
        # Print out available tracking modules
        print(f"Checking tracking capabilities in OpenCV {cv2.__version__}")
        
        # Try to use available trackers in your installation
        available_trackers = []
        
        # MIL tracker (detected in your installation)
        if hasattr(cv2, 'TrackerMIL_create'):
            print("Using cv2.TrackerMIL_create")
            try:
                tracker = cv2.TrackerMIL_create()
                available_trackers.append("MIL")
                return tracker
            except Exception as e:
                print(f"Error creating MIL tracker: {e}")
        
        # NANO tracker (detected in your installation)
        if hasattr(cv2, 'TrackerNano_create'):
            print("Using cv2.TrackerNano_create")
            try:
                tracker = cv2.TrackerNano_create()
                available_trackers.append("Nano")
                return tracker
            except Exception as e:
                print(f"Error creating Nano tracker: {e}")
        
        # GOTURN tracker (detected in your installation but may need models)
        if hasattr(cv2, 'TrackerGOTURN_create'):
            print("Using cv2.TrackerGOTURN_create")
            try:
                tracker = cv2.TrackerGOTURN_create()
                available_trackers.append("GOTURN")
                return tracker
            except Exception as e:
                print(f"Error creating GOTURN tracker: {e}")
                
        # VIT tracker (detected in your installation)
        if hasattr(cv2, 'TrackerVit_create'):
            print("Using cv2.TrackerVit_create")
            try:
                tracker = cv2.TrackerVit_create()
                available_trackers.append("Vit")
                return tracker
            except Exception as e:
                print(f"Error creating VIT tracker: {e}")
        
        # DaSiamRPN has model dependency issues
        # Try all the old standby trackers too
        if hasattr(cv2, 'TrackerCSRT_create'):
            print("Using cv2.TrackerCSRT_create")
            try:
                tracker = cv2.TrackerCSRT_create()
                available_trackers.append("CSRT")
                return tracker
            except Exception as e:
                print(f"Error creating CSRT tracker: {e}")
        
        if hasattr(cv2, 'TrackerKCF_create'):
            print("Using cv2.TrackerKCF_create")
            try:
                tracker = cv2.TrackerKCF_create()
                available_trackers.append("KCF")
                return tracker
            except Exception as e:
                print(f"Error creating KCF tracker: {e}")
                
        # Summary of available trackers
        if available_trackers:
            print(f"Available trackers: {', '.join(available_trackers)}")
        else:
            print("WARNING: No suitable tracking implementation found in this OpenCV version")
            print("For best tracking support, try: pip install opencv-contrib-python==4.5.5.64")
        
        # Just disable tracking for now - need the proper models and environment
        print("Tracking temporarily disabled - try reinstalling opencv-contrib-python")
        return None
    except Exception as e:
        print(f"Error creating tracker: {e}")
        print(f"OpenCV version: {cv2.__version__}")
        print("Disabling tracking for compatibility")
        return None

# Base HTML template med Bootstrap og Socket.IO
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="{{ lang }}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ _('360° Video Blur') }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.3/font/bootstrap-icons.css">
    <script src="https://cdn.socket.io/4.6.0/socket.io.min.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f8f9fa;
            color: #333;
            padding-top: 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        .card {
            border-radius: 15px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            border: none;
        }
        .card-header {
            background-color: #4a6cf7;
            color: white;
            border-radius: 15px 15px 0 0 !important;
            font-weight: bold;
            padding: 15px 20px;
        }
        .card-body {
            padding: 25px;
        }
        .btn-primary {
            background-color: #4a6cf7;
            border-color: #4a6cf7;
            padding: 8px 20px;
            border-radius: 8px;
            font-weight: 500;
        }
        .btn-primary:hover {
            background-color: #3a5ce4;
            border-color: #3a5ce4;
        }
        .form-label {
            font-weight: 500;
            margin-bottom: 8px;
        }
        .progress {
            height: 25px;
            border-radius: 8px;
            margin: 15px 0;
        }
        .video-info {
            background-color: #f1f3f9;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
        }
        .video-info-item {
            margin-bottom: 5px;
            display: flex;
        }
        .video-info-label {
            font-weight: 500;
            width: 180px;
        }
        .lang-selector {
            float: right;
        }
        .loading-spinner {
            display: none;
            color: #4a6cf7;
            text-align: center;
            padding: 20px;
        }
        #preview-container {
            margin-top: 20px;
            text-align: center;
        }
        #video-preview {
            max-width: 100%;
            border-radius: 8px;
            display: none;
        }
        .status-step {
            margin: 5px 0;
            padding: 10px;
            border-radius: 8px;
            background-color: #f1f3f9;
        }
        .status-step.active {
            background-color: #e0e7ff;
            border-left: 4px solid #4a6cf7;
        }
        .status-step.completed {
            background-color: #e6ffee;
            border-left: 4px solid #28a745;
        }
        .time-estimate {
            font-size: 14px;
            font-style: italic;
            margin-top: 10px;
        }
        .settings-section {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #dee2e6;
        }
        .error-message {
            color: #dc3545;
            background-color: #f8d7da;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span>{{ _('360° Video Blur Tool') }}</span>
                <div class="dropdown lang-selector">
                    <button class="btn btn-sm btn-light dropdown-toggle" type="button" id="langDropdown" data-bs-toggle="dropdown" aria-expanded="false">
                        {{ current_language_name }}
                    </button>
                    <ul class="dropdown-menu" aria-labelledby="langDropdown">
                        {% for code, name in supported_languages.items() %}
                            <li><a class="dropdown-item" href="?lang={{ code }}">{{ name }}</a></li>
                        {% endfor %}
                    </ul>
                </div>
            </div>
            <div class="card-body">
                <div id="step-upload">
                    <h5 class="card-title">{{ _('Upload a 360° video for automatic face and license plate blurring') }}</h5>
                    <p class="card-text">{{ _('Select a video file (MP4 format) to process. The tool will automatically detect and blur faces and license plates.') }}</p>
                    
                    <form id="upload-form" method="post" enctype="multipart/form-data">
                        <div class="mb-3">
                            <label for="video" class="form-label">{{ _('Video file') }} (MP4)</label>
                            <input class="form-control" type="file" id="video" name="video" accept="video/mp4">
                        </div>
                        
                        <div id="preview-container">
                            <video id="video-preview" controls></video>
                            <div class="video-info" id="video-info" style="display:none;">
                                <h6>{{ _('Video Information') }}</h6>
                                <div class="video-info-item">
                                    <span class="video-info-label">{{ _('Duration') }}:</span>
                                    <span id="video-duration">-</span>
                                </div>
                                <div class="video-info-item">
                                    <span class="video-info-label">{{ _('Resolution') }}:</span>
                                    <span id="video-resolution">-</span>
                                </div>
                                <div class="video-info-item">
                                    <span class="video-info-label">{{ _('File size') }}:</span>
                                    <span id="video-size">-</span>
                                </div>
                                <div class="video-info-item">
                                    <span class="video-info-label">{{ _('Format') }}:</span>
                                    <span id="video-format">-</span>
                                </div>
                                <div class="time-estimate">
                                    {{ _('Estimated processing time') }}: <span id="time-estimate">-</span>
                                </div>
                            </div>
                        </div>
                        
                        <div class="settings-section">
                            <h6>{{ _('Processing options') }}</h6>
                            <div class="form-check mb-2">
                                <input class="form-check-input" type="checkbox" id="debug_mode" name="debug_mode" value="1">
                                <label class="form-check-label" for="debug_mode">
                                    {{ _('Show detections (debug mode)') }}
                                </label>
                            </div>
                            <div class="form-check mb-2">
                                <input class="form-check-input" type="checkbox" id="use_dnn" name="use_dnn" value="1" checked>
                                <label class="form-check-label" for="use_dnn">
                                    {{ _('Use DNN for better detection (recommended)') }}
                                </label>
                            </div>
                        </div>
                        
                        <div class="mt-4">
                            <button type="submit" class="btn btn-primary" id="upload-btn">
                                <i class="bi bi-cloud-arrow-up"></i> {{ _('Upload and process') }}
                            </button>
                        </div>
                    </form>
                </div>
                
                <div id="step-processing" style="display:none;">
                    <h5 class="card-title">{{ _('Processing your video') }}...</h5>
                    
                    <div class="progress">
                        <div class="progress-bar progress-bar-striped progress-bar-animated" id="progress-bar" role="progressbar" style="width: 0%"></div>
                    </div>
                    
                    <div id="progress-text" class="text-center mb-3">{{ _('Starting processing') }}...</div>
                    
                    <div id="estimated-time-container" class="alert alert-info text-center mb-3" style="display: none;">
                        <i class="bi bi-clock-history"></i> <strong>{{ _('Estimated time remaining') }}:</strong> <span id="estimated-time-remaining" class="fs-5">-</span>
                        <div class="small mt-1">{{ _('This estimate is updated continuously based on processing speed') }}</div>
                    </div>
                    
                    <!-- Detaljeret behandlingsinformation -->
                    <div id="processing-details-container" class="card mt-3 mb-3" style="display: none;">
                        <div class="card-header bg-light">
                            <div class="d-flex justify-content-between align-items-center">
                                <strong>{{ _('Processing Details') }}</strong>
                                <button class="btn btn-sm btn-outline-secondary" onclick="toggleProcessingDetails()">
                                    <i class="bi bi-arrows-expand" id="details-toggle-icon"></i>
                                </button>
                            </div>
                        </div>
                        <div id="processing-details-content" class="card-body bg-light" style="display: none; max-height: 300px; overflow-y: auto;">
                            <div class="row mb-2">
                                <div class="col-md-4">
                                    <div class="card">
                                        <div class="card-header py-1 bg-primary text-white">{{ _('CPU Utilization') }}</div>
                                        <div class="card-body py-2" id="cpu-info">-</div>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="card">
                                        <div class="card-header py-1 bg-primary text-white">{{ _('Processing Speed') }}</div>
                                        <div class="card-body py-2" id="processing-speed">-</div>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="card">
                                        <div class="card-header py-1 bg-primary text-white">{{ _('Current Batch') }}</div>
                                        <div class="card-body py-2" id="batch-info">-</div>
                                    </div>
                                </div>
                            </div>
                            <div>
                                <h6 class="border-bottom pb-1">{{ _('Processing Log') }}:</h6>
                                <div id="processing-log" class="small" style="font-family: monospace; height: 160px; overflow-y: auto;"></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="status-steps">
                        <div class="status-step" id="step-upload-status">
                            <i class="bi bi-check-circle"></i> {{ _('Uploading video') }}
                        </div>
                        <div class="status-step" id="step-analyze">
                            <i class="bi bi-hourglass"></i> {{ _('Analyzing video and loading detection models') }}
                        </div>
                        <div class="status-step" id="step-detect">
                            <i class="bi bi-eye"></i> {{ _('Detecting faces and license plates') }}
                        </div>
                        <div class="status-step" id="step-blur">
                            <i class="bi bi-person-bounding-box"></i> {{ _('Applying blur to detected objects') }}
                        </div>
                        <div class="status-step" id="step-finalize">
                            <i class="bi bi-file-earmark-check"></i> {{ _('Finalizing output video') }}
                        </div>
                    </div>
                    
                    <div class="text-center mt-4 mb-4">
                        <div class="loading-spinner" id="loading-spinner">
                            <div class="spinner-border" role="status">
                                <span class="visually-hidden">{{ _('Loading') }}...</span>
                            </div>
                            <p>{{ _('This can take several minutes depending on video length and complexity') }}</p>
                        </div>
                    </div>
                    
                    <div class="text-center">
                        <button id="cancel-btn" class="btn btn-danger">
                            <i class="bi bi-x-circle"></i> {{ _('Cancel processing') }}
                        </button>
                    </div>
                </div>
                
                <div id="step-download" style="display:none;">
                    <h5 class="card-title">{{ _('Processing complete!') }}</h5>
                    <p class="card-text">{{ _('Your video has been processed successfully. You can now download the result.') }}</p>
                    
                    <div class="text-center mb-4">
                        <div class="alert alert-success">
                            <i class="bi bi-check-circle-fill"></i> {{ _('All detected faces and license plates have been blurred') }}
                        </div>
                    </div>
                    
                    <div class="text-center">
                        <a id="download-link" href="#" class="btn btn-primary">
                            <i class="bi bi-download"></i> {{ _('Download processed video') }}
                        </a>
                        
                        <button id="restart-btn" class="btn btn-outline-secondary ms-2">
                            <i class="bi bi-arrow-repeat"></i> {{ _('Process another video') }}
                        </button>
                    </div>
                </div>
                
                <div class="error-message" id="error-message">
                    <i class="bi bi-exclamation-triangle-fill"></i> <span id="error-text"></span>
                </div>
            </div>
        </div>
        
        <div class="text-center text-muted mt-4">
            <small>
                &copy; 2025 {{ _('360° Video Blur Tool') }} | {{ _('Privacy focused video processing') }}
            </small>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Socket.IO setup
        const socket = io({
            transports: ['websocket', 'polling']
        });
        let jobId = {% if job_id %}"{{ job_id }}"{% else %}null{% endif %};
        
        // Funktion til at skifte mellem vising/skjul af detaljer
        function toggleProcessingDetails() {
            const detailsContent = document.getElementById('processing-details-content');
            const detailsIcon = document.getElementById('details-toggle-icon');
            
            if (detailsContent.style.display === 'none') {
                detailsContent.style.display = 'block';
                detailsIcon.classList.remove('bi-arrows-expand');
                detailsIcon.classList.add('bi-arrows-collapse');
            } else {
                detailsContent.style.display = 'none';
                detailsIcon.classList.remove('bi-arrows-collapse');
                detailsIcon.classList.add('bi-arrows-expand');
            }
        }
        
        // Funktion til at tilføje en log-linje til processing-log
        function addProcessingLogEntry(message) {
            const logElement = document.getElementById('processing-log');
            if (logElement) {
                const timestamp = new Date().toLocaleTimeString();
                const logLine = document.createElement('div');
                logLine.textContent = `[${timestamp}] ${message}`;
                logElement.appendChild(logLine);
                
                // Auto-scroll til bunden
                logElement.scrollTop = logElement.scrollHeight;
            }
        }
        
        // Hvis der er et aktivt job, vis processeringsskærmen
        document.addEventListener('DOMContentLoaded', function() {
            if (jobId) {
                // Vis korrekt UI baseret på job status
                const jobStatus = "{{ job_status }}";
                
                if (jobStatus === 'processing' || jobStatus === 'uploading') {
                    document.getElementById('step-upload').style.display = 'none';
                    document.getElementById('step-processing').style.display = 'block';
                    document.getElementById('loading-spinner').style.display = 'block';
                    
                    // Gem job ID i skjult input
                    const jobIdInput = document.createElement('input');
                    jobIdInput.type = 'hidden';
                    jobIdInput.id = 'job-id-input';
                    jobIdInput.value = jobId;
                    document.body.appendChild(jobIdInput);
                    
                    // Opret permalink sektion
                    const permalinkSection = document.createElement('div');
                    permalinkSection.id = 'permalink-section';
                    permalinkSection.className = 'alert alert-info mt-3';
                    permalinkSection.innerHTML = `
                        <strong>{{ _('Permanent link to this job') }}:</strong>
                        <div class="input-group mt-2">
                            <input type="text" class="form-control" id="permalink-input" value="${window.location.href}" readonly>
                            <button class="btn btn-outline-secondary" type="button" onclick="copyPermalink()">
                                <i class="bi bi-clipboard"></i> {{ _('Copy') }}
                            </button>
                        </div>
                        <small class="text-muted">{{ _('Save this link to check job status later') }}</small>
                    `;
                    
                    // Tilføj til DOM efter progress bar
                    const progressContainer = document.querySelector('.progress').parentNode;
                    progressContainer.appendChild(permalinkSection);
                    
                    // Tilføj copy funktion
                    window.copyPermalink = function() {
                        const permalinkInput = document.getElementById('permalink-input');
                        permalinkInput.select();
                        document.execCommand('copy');
                        alert('{{ _("Link copied to clipboard!") }}');
                    };
                    
                    // Start at lytte efter opdateringer for dette job
                    setupJobListeners();
                    
                    // Anmod om den aktuelle status
                    fetch('/status/' + jobId)
                        .then(response => response.json())
                        .then(data => {
                            console.log("INITIAL STATUS DATA:", JSON.stringify(data));
                            updateProgress(data.progress, data.message);
                            
                            // Consistent approach for FPS handling
                            if (data.fps) {
                                console.log("INITIAL FPS DATA FOUND!", data.fps);
                                
                                // Validate FPS data has the expected structure
                                if (data.fps.batch && data.fps.avg) {
                                    document.querySelectorAll('#processing-speed').forEach(function(element) {
                                        element.innerHTML = `${data.fps.batch} FPS (current)<br>${data.fps.avg} FPS (average)`;
                                        console.log("INITIAL FPS UPDATE COMPLETE!");
                                    });
                                    
                                    addProcessingLogEntry(`Initial processing rate: ${data.fps.batch} FPS`);
                                } else {
                                    console.error("Initial FPS data structure is invalid:", data.fps);
                                }
                            } else {
                                console.log("No initial FPS data available yet");
                                document.querySelectorAll('#processing-speed').forEach(function(element) {
                                    element.innerText = "Calculating...";
                                });
                            }
                            
                            if (data.batch) {
                                const batchInfo = document.getElementById('batch-info');
                                if (batchInfo) {
                                    batchInfo.innerHTML = `Batch <strong>${data.batch.current}</strong> of ${data.batch.total}<br>Size: ${data.batch.size} frames`;
                                }
                            }
                            
                            // Vis CPU info hvis tilgængelig (kommer fra en anden kilde, men tjek alligevel)
                            const cpuInfo = document.getElementById('cpu-info');
                            if (cpuInfo && cpuInfo.textContent === '-') {
                                // Hvis CPU info ikke er sat endnu, tilføj en placeholder
                                cpuInfo.innerHTML = 'Detecting cores...';
                            }
                            
                            // Vis processing details container og sørg for det er åbent
                            document.getElementById('processing-details-container').style.display = 'block';
                            document.getElementById('processing-details-content').style.display = 'block';
                            
                            // Skift ikon til collapse
                            const icon = document.getElementById('details-toggle-icon');
                            if (icon) {
                                icon.classList.remove('bi-arrows-expand');
                                icon.classList.add('bi-arrows-collapse');
                            }
                        })
                        .catch(error => {
                            console.error('Error fetching status:', error);
                        });
                } else if (jobStatus === 'completed') {
                    document.getElementById('step-upload').style.display = 'none';
                    document.getElementById('step-processing').style.display = 'none';
                    document.getElementById('step-download').style.display = 'block';
                    
                    const downloadLink = document.getElementById('download-link');
                    downloadLink.href = '/download/' + jobId;
                } else if (jobStatus === 'error' || jobStatus === 'cancelled') {
                    document.getElementById('error-text').textContent = "{{ _('This job has been cancelled or encountered an error') }}";
                    document.getElementById('error-message').style.display = 'block';
                }
            }
        });
        
        // Funktion til at opsætte lyttere til Socket.IO-events
        function setupJobListeners() {
            // Lokal variabel til at holde styr på vores status interval
            let statusUpdateInterval = null;
            
            // Listen for progress updates
            socket.on('progress_update', function(data) {
                if (data.job_id !== jobId) return;
                
                updateProgress(data.progress, data.message);
                updateStepStatus(data.step, 'active');
                
                if (data.prev_step) {
                    updateStepStatus(data.prev_step, 'completed');
                }
                
                // Handle FPS update directly in the progress_update event
                if (data.fps || data.fps_update) {
                    console.log("FPS UPDATE DETECTED IN PROGRESS EVENT:", data.fps);
                    
                    // Ensure FPS data is properly structured before updating
                    if (data.fps && data.fps.batch && data.fps.avg) {
                        document.querySelectorAll('#processing-speed').forEach(function(element) {
                            element.innerHTML = `${data.fps.batch} FPS (current)<br>${data.fps.avg} FPS (average)`;
                            console.log("FPS DISPLAY UPDATED FROM PROGRESS EVENT");
                        });
                        addProcessingLogEntry(`Processing rate updated: ${data.fps.batch} FPS (current batch)`);
                    } else {
                        console.error("FPS update event received but data structure is invalid:", data.fps);
                    }
                }
                
                // Hvis vi ikke har en status-interval endnu, opret en
                if (!statusUpdateInterval) {
                    // Opdater detaljeret status hvert 3. sekund
                    statusUpdateInterval = setInterval(function() {
                        // Hent opdateret status fra server
                        fetch('/status/' + jobId)
                            .then(response => response.json())
                            .then(data => {
                                console.log("Status update received:", data);
                                
                                // SUPER ENKEL DIREKTE OPDATERING - Rydde alt andet væk
                                console.log("RAW STATUS DATA:", JSON.stringify(data));
                                
                                // Simplified direct update approach
                                if (data.fps) {
                                    console.log("FPS DATA FOUND IN POLL!", data.fps);
                                    
                                    // Validate FPS data has the expected structure
                                    if (data.fps.batch && data.fps.avg) {
                                        // Directly update all processing-speed elements
                                        document.querySelectorAll('#processing-speed').forEach(function(element) {
                                            element.innerHTML = `${data.fps.batch} FPS (current)<br>${data.fps.avg} FPS (average)`;
                                            console.log("FPS DISPLAY UPDATED FROM STATUS POLL");
                                        });
                                        
                                        // Log til debugkonsollet
                                        addProcessingLogEntry(`Processing rate: ${data.fps.batch} FPS (current batch)`);
                                    } else {
                                        console.error("FPS data structure from poll is invalid:", data.fps);
                                    }
                                } else {
                                    console.log("No FPS data in status poll");
                                    // We'll wait for a proper FPS update instead of trying to extract it
                                }
                                
                                if (data.batch) {
                                    const batchInfo = document.getElementById('batch-info');
                                    if (batchInfo) {
                                        batchInfo.innerHTML = `Batch <strong>${data.batch.current}</strong> of ${data.batch.total}<br>Size: ${data.batch.size} frames`;
                                    }
                                }
                                
                                // Opdater også tid-estimat
                                if (data.time && data.time.message) {
                                    const estimatedTimeElement = document.getElementById('estimated-time-remaining');
                                    if (estimatedTimeElement) {
                                        // Udtræk tid fra meddelelsen
                                        if (data.time.message.includes("min")) {
                                            const match = data.time.message.match(/(\\d+) min (\\d+) sec/);
                                            if (match) {
                                                estimatedTimeElement.textContent = `${match[1]} min ${match[2]} sec`;
                                            }
                                        } else {
                                            const match = data.time.message.match(/(\\d+) sec/);
                                            if (match) {
                                                estimatedTimeElement.textContent = `${match[1]} sec`;
                                            }
                                        }
                                        
                                        // Sørg for at containeren er synlig
                                        document.getElementById('estimated-time-container').style.display = 'block';
                                    }
                                }
                            })
                            .catch(error => {
                                console.error('Error fetching status update:', error);
                            });
                    }, 3000);
                }
            });
            
            // Lyt efter CPU info
            socket.on('worker_cpu_info', function(data) {
                if (data.job_id !== jobId) return;
                
                console.log("CPU info received:", data);
                try {
                    // Sikre os at DOM-elementet eksisterer
                    const cpuInfo = document.getElementById('cpu-info');
                    console.log("CPU info element:", cpuInfo);
                    
                    if (cpuInfo) {
                        // Simpel test af DOM-opdatering
                        cpuInfo.textContent = "Testing update...";
                        console.log("Test update of CPU info successful");
                        
                        // Opdater med de reelle data
                        cpuInfo.innerHTML = `<strong>${data.used_cores}</strong> of ${data.total_cores} cores (${data.percentage})`;
                        addProcessingLogEntry(`CPU utilization: ${data.used_cores} of ${data.total_cores} cores (${data.percentage})`);
                        
                        // Log til konsol for at bekræfte
                        console.log("Updated CPU info to:", cpuInfo.innerHTML);
                    } else {
                        console.error("CPU info element not found in DOM!");
                        
                        // Forsøg at finde overordnet element og oprette det
                        setTimeout(function() {
                            const container = document.querySelector('.card-body');
                            if (container) {
                                console.log("Found container, recreating CPU info element");
                                const newCpuInfo = document.createElement('div');
                                newCpuInfo.id = 'cpu-info';
                                newCpuInfo.innerHTML = `<strong>${data.used_cores}</strong> of ${data.total_cores} cores (${data.percentage})`;
                                container.appendChild(newCpuInfo);
                            }
                        }, 500);
                    }
                } catch (error) {
                    console.error("Error updating CPU info:", error);
                }
                
                // Sørg for at processing details container er synlig
                document.getElementById('processing-details-container').style.display = 'block';
                
                // Vis også detaljernes indhold automatisk
                const detailsContent = document.getElementById('processing-details-content');
                const detailsIcon = document.getElementById('details-toggle-icon');
                if (detailsContent && detailsContent.style.display === 'none') {
                    detailsContent.style.display = 'block';
                    if (detailsIcon) {
                        detailsIcon.classList.remove('bi-arrows-expand');
                        detailsIcon.classList.add('bi-arrows-collapse');
                    }
                }
            });
            
            // Vi bruger ikke længere denne metode til at opdatere FPS info,
            // da vi i stedet bruger status-polling
            
            // Listen for job completion
            socket.on('job_complete', function(data) {
                if (data.job_id !== jobId) return;
                
                // Stop status update interval hvis den kører
                if (statusUpdateInterval) {
                    clearInterval(statusUpdateInterval);
                    statusUpdateInterval = null;
                }
                
                document.getElementById('step-processing').style.display = 'none';
                document.getElementById('step-download').style.display = 'block';
                
                const downloadLink = document.getElementById('download-link');
                downloadLink.href = data.download_url;
                
                // Tilføj den endelige tid til loggen
                if (data.processing_time) {
                    const totalSeconds = Math.round(data.processing_time);
                    const minutes = Math.floor(totalSeconds / 60);
                    const seconds = totalSeconds % 60;
                    const timeMessage = minutes > 0 ? 
                        `${minutes} min ${seconds} sec` : `${seconds} sec`;
                    
                    addProcessingLogEntry(`Processing completed in ${timeMessage}`);
                }
            });
            
            // Handle errors
            socket.on('job_error', function(data) {
                if (data.job_id !== jobId) return;
                showError(data.error);
            });
        }
        
        // File input change handler
        document.getElementById('video').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (!file) return;
            
            // Show preview
            const video = document.getElementById('video-preview');
            video.src = URL.createObjectURL(file);
            video.style.display = 'block';
            
            // Load video metadata
            video.onloadedmetadata = function() {
                document.getElementById('video-info').style.display = 'block';
                
                // Show video information
                document.getElementById('video-duration').textContent = formatTime(video.duration);
                document.getElementById('video-resolution').textContent = `${video.videoWidth} × ${video.videoHeight}`;
                document.getElementById('video-size').textContent = formatSize(file.size);
                document.getElementById('video-format').textContent = file.type;
                
                // Calculate estimated processing time
                const estimatedSeconds = Math.round(video.duration * 1.5); // Rough estimate: 1.5x real-time
                document.getElementById('time-estimate').textContent = formatTime(estimatedSeconds);
            };
        });
        
        // Form submission
        document.getElementById('upload-form').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const videoFile = document.getElementById('video').files[0];
            if (!videoFile) {
                showError("{{ _('Please select a video file') }}");
                return;
            }
            
            // Create FormData
            const formData = new FormData();
            formData.append('video', videoFile);
            
            // Add options
            if (document.getElementById('debug_mode').checked) {
                formData.append('debug_mode', '1');
            }
            
            if (document.getElementById('use_dnn').checked) {
                formData.append('use_dnn', '1');
            }
            
            // Show processing UI
            document.getElementById('step-upload').style.display = 'none';
            document.getElementById('step-processing').style.display = 'block';
            document.getElementById('loading-spinner').style.display = 'block';
            
            // Update initial status
            updateStepStatus('step-upload-status', 'active');
            
            // Submit the form
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showError(data.error);
                    return;
                }
                
                jobId = data.job_id;
                console.log('Processing started with job ID:', jobId);
                
                // Opsæt Socket.IO lyttere
                setupJobListeners();
                
                // Handle job cancellation
                document.getElementById('cancel-btn').addEventListener('click', function() {
                    if (!jobId) return;
                    
                    if (confirm('{{ _("Are you sure you want to cancel processing? This cannot be undone.") }}')) {
                        fetch('/cancel/' + jobId, { method: 'POST' })
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    document.getElementById('step-processing').style.display = 'none';
                                    document.getElementById('step-upload').style.display = 'block';
                                    document.getElementById('upload-form').reset();
                                    document.getElementById('video-preview').style.display = 'none';
                                    document.getElementById('video-info').style.display = 'none';
                                } else {
                                    showError(data.error || '{{ _("Failed to cancel processing") }}');
                                }
                            })
                            .catch(error => {
                                showError('{{ _("Error cancelling process") }}: ' + error.message);
                            });
                    }
                });
            })
            .catch(error => {
                showError("{{ _('An error occurred during upload') }}: " + error.message);
            });
        });
        
        // Restart button
        document.getElementById('restart-btn').addEventListener('click', function() {
            document.getElementById('step-download').style.display = 'none';
            document.getElementById('step-upload').style.display = 'block';
            document.getElementById('upload-form').reset();
            document.getElementById('video-preview').style.display = 'none';
            document.getElementById('video-info').style.display = 'none';
            
            // Reset progress and steps
            updateProgress(0, "{{ _('Starting processing') }}...");
            document.querySelectorAll('.status-step').forEach(el => {
                el.classList.remove('active', 'completed');
            });
        });
        
        // Utility functions
        function updateProgress(percent, message) {
            document.getElementById('progress-bar').style.width = percent + '%';
            document.getElementById('progress-bar').setAttribute('aria-valuenow', percent);
            document.getElementById('progress-text').textContent = message;
            
            // Gemmer job ID i en skjult input, så vi kan bruge det til permalink
            if (jobId && !document.getElementById('job-id-input')) {
                const jobIdInput = document.createElement('input');
                jobIdInput.type = 'hidden';
                jobIdInput.id = 'job-id-input';
                jobIdInput.value = jobId;
                document.body.appendChild(jobIdInput);
                
                // Opdater URL med job_id for at lave et permalink
                const url = new URL(window.location.href);
                url.searchParams.set('job_id', jobId);
                window.history.replaceState({}, '', url.toString());
                
                // Vis permalink section hvis den eksisterer
                if (!document.getElementById('permalink-section')) {
                    // Opret permalink section
                    const permalinkSection = document.createElement('div');
                    permalinkSection.id = 'permalink-section';
                    permalinkSection.className = 'alert alert-info mt-3';
                    permalinkSection.innerHTML = `
                        <strong>{{ _('Permanent link to this job') }}:</strong>
                        <div class="input-group mt-2">
                            <input type="text" class="form-control" id="permalink-input" value="${url.toString()}" readonly>
                            <button class="btn btn-outline-secondary" type="button" onclick="copyPermalink()">
                                <i class="bi bi-clipboard"></i> {{ _('Copy') }}
                            </button>
                        </div>
                        <small class="text-muted">{{ _('Save this link to check job status later') }}</small>
                    `;
                    
                    // Tilføj til DOM efter progress bar
                    const progressContainer = document.querySelector('.progress').parentNode;
                    progressContainer.appendChild(permalinkSection);
                    
                    // Tilføj copy funktion
                    window.copyPermalink = function() {
                        const permalinkInput = document.getElementById('permalink-input');
                        permalinkInput.select();
                        document.execCommand('copy');
                        alert('{{ _("Link copied to clipboard!") }}');
                    };
                }
            }
            
            // Vis detaljevisningen når vi får den første progress update
            document.getElementById('processing-details-container').style.display = 'block';
            
            // Vis også detaljernes indhold automatisk for første progress update
            if (!window.detailsShown) {
                window.detailsShown = true;
                const detailsContent = document.getElementById('processing-details-content');
                const detailsIcon = document.getElementById('details-toggle-icon');
                if (detailsContent && detailsContent.style.display === 'none') {
                    detailsContent.style.display = 'block';
                    if (detailsIcon) {
                        detailsIcon.classList.remove('bi-arrows-expand');
                        detailsIcon.classList.add('bi-arrows-collapse');
                    }
                }
            }
            
            // Add the message to the processing log
            addProcessingLogEntry(message);
            
            // Check if message contains time information and extract it
            const timeRegex = /(\\d+) min (\\d+) sec remaining|(\\d+) sec remaining/;
            const timeMatch = message.match(timeRegex);
            
            // For debugging
            console.log("Message:", message);
            console.log("Time match:", timeMatch);
            
            // We now use structured FPS data directly so we don't
            // need to extract it from messages anymore
            
            // Extract batch information if available
            const batchRegex = /Processing frames (\\d+)-(\\d+) of (\\d+)/;
            const batchMatch = message.match(batchRegex);
            if (batchMatch) {
                const batchInfo = document.getElementById('batch-info');
                if (batchInfo) {
                    const startFrame = batchMatch[1];
                    const endFrame = batchMatch[2];
                    const totalFrames = batchMatch[3];
                    const batchSize = parseInt(endFrame) - parseInt(startFrame) + 1;
                    batchInfo.textContent = `Frames ${startFrame}-${endFrame} (${batchSize} frames)`;
                }
            }
            
            if (timeMatch) {
                // Update the estimated time element if it exists
                const estimatedTimeElement = document.getElementById('estimated-time-remaining');
                if (estimatedTimeElement) {
                    if (timeMatch[1] && timeMatch[2]) {
                        estimatedTimeElement.textContent = `${timeMatch[1]} min ${timeMatch[2]} sec`;
                    } else if (timeMatch[3]) {
                        estimatedTimeElement.textContent = `${timeMatch[3]} sec`;
                    }
                    
                    // Make sure the container is visible
                    const estimatedTimeContainer = document.getElementById('estimated-time-container');
                    if (estimatedTimeContainer) {
                        estimatedTimeContainer.style.display = 'block';
                    }
                }
            } else {
                // Fall back to manually checking for "remaining" text anywhere in the message
                if (message.includes("remaining")) {
                    const parts = message.split("remaining")[0].trim().split(" ");
                    let timeText = "";
                    
                    // Try to extract time based on pattern
                    for (let i = parts.length-1; i >= 0; i--) {
                        if (parts[i] === "min" && i > 0 && !isNaN(parts[i-1])) {
                            timeText = parts[i-1] + " min";
                            if (i+1 < parts.length && !isNaN(parts[i+1]) && parts[i+2] === "sec") {
                                timeText += " " + parts[i+1] + " sec";
                            }
                            break;
                        } else if (parts[i] === "sec" && i > 0 && !isNaN(parts[i-1])) {
                            timeText = parts[i-1] + " sec";
                            break;
                        }
                    }
                    
                    if (timeText) {
                        const estimatedTimeElement = document.getElementById('estimated-time-remaining');
                        if (estimatedTimeElement) {
                            estimatedTimeElement.textContent = timeText;
                            
                            // Make sure the container is visible
                            const estimatedTimeContainer = document.getElementById('estimated-time-container');
                            if (estimatedTimeContainer) {
                                estimatedTimeContainer.style.display = 'block';
                            }
                        }
                    }
                }
            }
        }
        
        function updateStepStatus(stepId, status) {
            const el = document.getElementById(stepId);
            if (!el) return;
            
            el.classList.remove('active', 'completed');
            el.classList.add(status);
        }
        
        function showError(message) {
            document.getElementById('error-text').textContent = message;
            document.getElementById('error-message').style.display = 'block';
            document.getElementById('step-processing').style.display = 'none';
            document.getElementById('step-upload').style.display = 'block';
            document.getElementById('loading-spinner').style.display = 'none';
        }
        
        function formatTime(seconds) {
            const hrs = Math.floor(seconds / 3600);
            const mins = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);
            
            let result = '';
            if (hrs > 0) {
                result += `${hrs}h `;
            }
            if (mins > 0 || hrs > 0) {
                result += `${mins}m `;
            }
            result += `${secs}s`;
            
            return result;
        }
        
        function formatSize(bytes) {
            const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
            if (bytes === 0) return '0 Bytes';
            const i = Math.floor(Math.log(bytes) / Math.log(1024));
            return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + ' ' + sizes[i];
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    current_lang = get_locale()
    current_language_name = app.config['SUPPORTED_LANGUAGES'].get(current_lang, 'Dansk')
    
    # Tjek om der er et job_id parameter i URL'en
    job_id = request.args.get('job_id')
    job_exists = False
    job_status = None
    
    # Hvis der er et job_id, tjek om jobbet findes
    if job_id:
        # Tjek om jobbet findes i processing_jobs
        if job_id in processing_jobs:
            job_exists = True
            job_status = processing_jobs[job_id].get('status', 'unknown')
        else:
            # Tjek om der findes en status-fil for jobbet
            status_file = os.path.join(STATUS_FOLDER, f"{job_id}.json")
            if os.path.exists(status_file):
                try:
                    with open(status_file, 'r') as f:
                        status_data = json.load(f)
                        job_exists = True
                        job_status = status_data.get('status', 'unknown')
                        
                        # Genopret job i processing_jobs dictionary hvis det er aktivt
                        if job_status in ['processing', 'uploading']:
                            # Tjek om outputfilen findes
                            output_path = os.path.join(PROCESSED_FOLDER, f"{job_id}.mp4")
                            input_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.mp4")
                            
                            if os.path.exists(input_path):
                                # Genopret job info
                                processing_jobs[job_id] = {
                                    'input_path': input_path,
                                    'output_path': output_path,
                                    'debug_mode': False,  # Default value
                                    'use_dnn': True,      # Default value
                                    'start_time': status_data.get('timestamp', time.time() - 60),  # Antag det har kørt i mindst et minut
                                    'status': status_data.get('status', 'processing'),
                                    'progress': status_data.get('progress', 0),
                                    'message': status_data.get('message', '')
                                }
                                
                                # Start en monitoreringsstråd
                                monitoring_thread = threading.Thread(
                                    target=monitor_worker_status,
                                    args=(job_id,)
                                )
                                monitoring_thread.daemon = True
                                monitoring_thread.start()
                                
                                logger.info(f"Resumed monitoring for job {job_id}")
                except Exception as e:
                    logger.error(f"Error reading status file for job {job_id}: {e}")
    
    # Render template med sprog-variabler og job info
    return render_template_string(
        BASE_TEMPLATE,
        lang=current_lang,
        current_language_name=current_language_name,
        supported_languages=app.config['SUPPORTED_LANGUAGES'],
        job_id=job_id if job_exists else None,
        job_status=job_status,
        current_url=request.url_root
    )

@app.route('/upload', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({'error': _('No video file provided')}), 400
    
    file = request.files['video']
    if not file.filename:
        return jsonify({'error': _('No file selected')}), 400
    
    if not file.filename.lower().endswith('.mp4'):
        return jsonify({'error': _('Only MP4 videos are supported')}), 400
    
    try:
        # Generate unique ID for this job
        job_id = str(uuid.uuid4())
        
        # Save file
        filename = f"{job_id}.mp4"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Get processing options
        debug_mode = 'debug_mode' in request.form
        use_dnn = 'use_dnn' in request.form
        
        # Setup processing job
        output_path = os.path.join(PROCESSED_FOLDER, filename)
        
        # Store job information
        processing_jobs[job_id] = {
            'input_path': filepath,
            'output_path': output_path,
            'debug_mode': debug_mode,
            'use_dnn': use_dnn,
            'start_time': time.time(),
            'status': 'uploading'
        }
        
        # Start background worker process
        try:
            # Bestem Python-stien
            python_path = sys.executable
            worker_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blur360_worker.py")
            
            # Build command for worker script
            cmd = [
                python_path,  # Current Python interpreter
                worker_script,
                "--job_id", job_id,
                "--input", filepath,
                "--output", output_path
            ]
            
            # Add optional parameters
            if debug_mode:
                cmd.append("--debug")
            if use_dnn:
                cmd.append("--use_dnn")
                
            # Start the worker process
            worker_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Start en tråd til at overvåge worker-processens stdout/stderr
            def monitor_worker_output(process):
                """Læser output fra worker-processen og logger det til webappens log"""
                for line in iter(process.stdout.readline, ''):
                    if line:
                        line = line.strip()
                        if "CPU UTILIZATION" in line or "Running with" in line:
                            # Fremhæv CPU-information
                            logger.info(f"WORKER CPU INFO: {line}")
                            print(f"\n\033[1;32m>>> {line} <<<\033[0m\n")  # Grøn fed tekst i terminal
                            
                            # Find CPU-informationen og send til klienten via Socket.IO
                            if "Running with" in line:
                                # Udtræk CPU-info
                                cpu_match = re.search(r"Running with (\d+) parallel processes \(of (\d+) available cores\)", line)
                                if cpu_match:
                                    used_cores = cpu_match.group(1)
                                    total_cores = cpu_match.group(2)
                                    
                                    # Send til klienten
                                    socketio.emit('worker_cpu_info', {
                                        'job_id': job_id,
                                        'used_cores': used_cores,
                                        'total_cores': total_cores,
                                        'percentage': f"{int(int(used_cores) / int(total_cores) * 100)}%"
                                    })
                        elif "Processing rate:" in line:
                            # Fremhæv FPS-information
                            logger.info(f"WORKER SPEED INFO: {line}")
                            
                            # Udtræk FPS-info
                            fps_match = re.search(r"Processing rate: ([0-9.]+) FPS \(batch\), ([0-9.]+) FPS \(avg\), ([0-9.]+) FPS \(weighted\)", line)
                            if fps_match:
                                batch_fps = fps_match.group(1)
                                avg_fps = fps_match.group(2)
                                weighted_fps = fps_match.group(3)
                                
                                # Send til klienten via en standard progress_update event så vi sikrer konsistent håndtering
                                socketio.emit('progress_update', {
                                    'job_id': job_id,
                                    'fps': {
                                        'batch': batch_fps,
                                        'avg': avg_fps,
                                        'weighted': weighted_fps
                                    },
                                    'fps_update': True
                                })
                        elif "ERROR" in line.upper():
                            # Log fejl
                            logger.error(f"WORKER: {line}")
                        else:
                            # Log almindelige beskeder
                            logger.info(f"WORKER: {line}")
                
                # Tjek også stderr
                for line in iter(process.stderr.readline, ''):
                    if line:
                        logger.error(f"WORKER ERROR: {line.strip()}")
            
            # Start tråden
            worker_output_thread = threading.Thread(
                target=monitor_worker_output,
                args=(worker_process,)
            )
            worker_output_thread.daemon = True
            worker_output_thread.start()
            
            # Start a thread to monitor the status file
            monitoring_thread = threading.Thread(
                target=monitor_worker_status,
                args=(job_id,)
            )
            monitoring_thread.daemon = True
            monitoring_thread.start()
            
            logger.info(f"Started worker process for job {job_id}")
            processing_jobs[job_id]['worker_pid'] = worker_process.pid
            processing_jobs[job_id]['status'] = 'processing'
            
            return jsonify({
                'success': True,
                'job_id': job_id,
                'message': _('Processing started in background')
            })
        
        except Exception as e:
            logging.exception(f"Error starting worker process: {e}")
            return jsonify({'error': _('Failed to start processing: ') + str(e)}), 500
        
    except Exception as e:
        logging.exception("Error in video upload")
        return jsonify({'error': str(e)}), 500

@app.route('/download/<job_id>')
def download_video(job_id):
    if job_id not in processing_jobs:
        return jsonify({'error': _('Invalid job ID')}), 404
    
    job = processing_jobs[job_id]
    
    # Tjek status-filen fra worker processen for at være sikker på, at jobbet er færdigt
    status_file = os.path.join(STATUS_FOLDER, f"{job_id}.json")
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status_data = json.load(f)
                
                # Hvis status-filen siger, jobbet ikke er fuldført endnu
                if status_data.get('status') != 'completed':
                    return jsonify({'error': _('Processing not yet complete (according to worker status)')}), 400
        except Exception as e:
            logger.error(f"Error reading status file for job {job_id}: {e}")
    
    # Tjek også job status i memory
    if job['status'] != 'completed':
        return jsonify({'error': _('Processing not yet complete')}), 400
    
    # Tjek at output-filen faktisk findes
    if not os.path.exists(job['output_path']):
        return jsonify({'error': _('Output file not found - processing may have failed')}), 404
    
    return send_file(
        job['output_path'],
        as_attachment=True,
        download_name=f"blurred_{os.path.basename(job['input_path'])}"
    )

@app.route('/status/<job_id>')
def get_job_status(job_id):
    if job_id not in processing_jobs:
        return jsonify({'error': _('Invalid job ID')}), 404
    
    job = processing_jobs[job_id]
    
    # Tjek først om der findes en status-fil fra worker processen
    status_file = os.path.join(STATUS_FOLDER, f"{job_id}.json")
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status_data = json.load(f)
                
                # Returner status fra worker processen - inkluder alle detaljer hvis de findes
                response_data = {
                    'status': status_data.get('status', job['status']),
                    'progress': status_data.get('progress', job.get('progress', 0)),
                    'message': status_data.get('message', job.get('message', ''))
                }
                
                # Tilføj yderligere detaljer hvis de findes
                for field in ['fps', 'batch', 'frames', 'time']:
                    if field in status_data:
                        response_data[field] = status_data[field]
                
                return jsonify(response_data)
        except Exception as e:
            logger.error(f"Error reading status file for job {job_id}: {e}")
    
    # Returner status fra job dictionary hvis status-filen ikke findes
    return jsonify({
        'status': job['status'],
        'progress': job.get('progress', 0),
        'message': job.get('message', '')
    })

@app.route('/cancel/<job_id>', methods=['POST'])
def cancel_processing(job_id):
    if job_id not in processing_jobs:
        return jsonify({'error': _('Invalid job ID')}), 404
    
    job = processing_jobs[job_id]
    
    # Dræb worker-processen hvis den kører
    if 'worker_pid' in job:
        try:
            worker_pid = job['worker_pid']
            logger.info(f"Attempting to terminate worker process {worker_pid} for job {job_id}")
            
            # Forsøg at afslutte processen
            import signal
            
            # Prøv først med direkte OS-signaler
            try:
                os.kill(worker_pid, signal.SIGTERM)
                logger.info(f"Sent SIGTERM to worker process {worker_pid}")
            except ProcessLookupError:
                logger.info(f"Process {worker_pid} already terminated")
            except Exception as e:
                logger.error(f"Error sending signal to process {worker_pid}: {e}")
                
            # Prøv også med psutil hvis tilgængeligt
            try:
                import psutil
                process = psutil.Process(worker_pid)
                process.terminate()  # Send SIGTERM signal
                
                # Vent på at processen afslutter (max 5 sekunder)
                process.wait(timeout=5)
                logger.info(f"Worker process {worker_pid} terminated successfully")
            except ImportError:
                logger.warning("psutil ikke installeret - kan ikke verificere process termination")
            except psutil.NoSuchProcess:
                logger.info(f"Worker process {worker_pid} no longer exists")
            except psutil.TimeoutExpired:
                try:
                    logger.warning(f"Worker process {worker_pid} did not terminate within timeout, forcing kill")
                    process.kill()  # Send SIGKILL signal
                except Exception as e:
                    logger.error(f"Failed to kill process: {e}")
            except Exception as e:
                logger.error(f"Error terminating worker process {worker_pid}: {e}")
        except Exception as e:
            logger.error(f"Error cancelling job {job_id}: {e}")
    
    # Markér job som annulleret
    job['status'] = 'cancelled'
    
    # Skriv annulleringsstatus til status-fil så worker-processen kan læse det
    status_file = os.path.join(STATUS_FOLDER, f"{job_id}.json")
    try:
        with open(status_file, 'w') as f:
            json.dump({
                'job_id': job_id,
                'progress': 0,
                'message': _('Job cancelled by user'),
                'status': 'cancelled',
                'timestamp': time.time()
            }, f)
    except Exception as e:
        logger.error(f"Error writing cancel status to file: {e}")
    
    # Returner success
    return jsonify({
        'success': True,
        'message': _('Processing cancelled')
    })

def load_dnn_models():
    """Load DNN-based detector models if available"""
    models_dir = Path("models")
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
            print("Loaded YOLOv8 face detector (Ultralytics)")
        except Exception as e:
            print(f"Failed to load YOLOv8 face detector: {e}")
    
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
                print("Loaded OpenCV DNN face detector as fallback (SSD/Caffe)")
            except Exception as e:
                print(f"Failed to load OpenCV DNN face detector: {e}")
        else:
            print(f"Neither YOLO nor OpenCV face detection models found in {models_dir}")
            print("For face detection, download models with: python download_models.py")
    
    # === YOLOv8 License Plate Detection Model ===
    yolov8_model_path = models_dir / "yolov8n_lp.pt"
    if ULTRALYTICS_AVAILABLE and yolov8_model_path.exists():
        try:
            # Load YOLOv8 license plate model
            yolo_model = YOLO(str(yolov8_model_path))
            models["yolov8_plate_detector"] = yolo_model
            models["detector_types"]["plate"] = "YOLOv8"
            print("Loaded YOLOv8 license plate detector (Ultralytics)")
        except Exception as e:
            print(f"Failed to load YOLOv8 license plate detector: {e}")
    
    # Check if license plate detection is available
    if models["yolov8_plate_detector"] is None:
        models["detector_types"]["plate"] = "Not available"
        print(f"YOLOv8 license plate model not found in {models_dir}")
        print("For license plate detection, download YOLOv8 model with: python download_models.py")
    
    # Print summary of loaded models
    print("\n=== DETECTION MODELS SUMMARY ===")
    print(f"Face detection: {models['detector_types']['face']}")
    print(f"License plate detection: {models['detector_types']['plate']}")
    print("===============================\n")
        
    return models

def update_job_progress(job_id, progress, message, step=None, prev_step=None):
    """Helper function to update job progress and emit Socket.IO event"""
    if job_id in processing_jobs:
        job = processing_jobs[job_id]
        job['progress'] = progress
        job['message'] = message
        if step:
            job['status'] = step
        
        # Log progress to console
        print(f"Job {job_id}: {progress}% - {message}")
        
        # Emit socket event with progress update
        try:
            socketio.emit('progress_update', {
                'job_id': job_id,
                'progress': progress,
                'message': message,
                'step': step,
                'prev_step': prev_step
            })
            print(f"Emitted progress update: {progress}% - {message}")
        except Exception as e:
            print(f"Error emitting progress: {e}")

# process_video_with_progress er nu erstattet af worker-processen via blur360_worker.py

def get_video_info(input_path):
    """Get information about a video file"""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        return None
    
    info = {
        'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        'fps': cap.get(cv2.CAP_PROP_FPS),
        'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        'duration': int(cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)) if cap.get(cv2.CAP_PROP_FPS) > 0 else 0,
        'codec': cap.get(cv2.CAP_PROP_FOURCC)
    }
    
    cap.release()
    return info

def process_video(input_path, output_path, debug_mode=False, use_dnn=True, models=None, job_id=None, skip_tracking=False, disable_legacy_tracking=True):
    """Main video processing function with optional progress reporting"""
    # Import gettext function for translations
    from flask_babel import gettext as _
    
    print(f"\n==== Starting video processing ====")
    print(f"OpenCV version: {cv2.__version__}")
    print(f"Input video: {input_path}")
    print(f"Output video: {output_path}")
    print(f"Debug mode: {debug_mode}")
    print(f"Use DNN: {use_dnn}")
    
    # Open video
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {input_path}")
        
    # Get video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"Video properties: {width}x{height} pixels, {fps} FPS, {frame_count} frames")
    
    # Use H.264 codec if available, fallback to mp4v
    try:
        fourcc = cv2.VideoWriter_fourcc(*'avc1')  # H.264 codec
    except:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Fallback codec
        
    # Create video writer
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # We no longer use Haar cascade classifiers
    # Instead, we exclusively use modern deep learning models for detection
    
    # Load or use provided DNN models for better detection
    if models is None and use_dnn:
        models = load_dnn_models()
        
    dnn_face_detector = models["face_detector"] if models and use_dnn else None
    dnn_plate_detector = models["plate_detector"] if models and use_dnn else None
    
    # Check for YOLOv8 model (will be preferred for license plates if available)
    yolov8_plate_detector = models["yolov8_plate_detector"] if models and use_dnn else None
    
    # Log model availability and types
    print(f"=== MODELS IN USE ===")
    print(f"Face detector: {models['detector_types']['face'] if models and 'detector_types' in models else 'Not available'}")
    print(f"License plate detector: {models['detector_types']['plate'] if models and 'detector_types' in models else 'Not available'}")
    print(f"====================\n")

    # Initialize frame counter and processing frequency
    frame_count = 0
    
    # Determine if tracking is supported/enabled
    has_tracking_support = False
    if skip_tracking:
        print("Tracking explicitly disabled via parameter")
    elif disable_legacy_tracking:
        print("Legacy tracking disabled for compatibility")
    else:
        # Only try to use tracking if not explicitly disabled
        try:
            # Try to create a tracker to see if it's supported
            tracker = create_tracker()
            has_tracking_support = tracker is not None
            if has_tracking_support:
                print(f"Successfully created tracker of type: {type(tracker).__name__}")
                print(f"Tracking is ENABLED and working correctly!")
            else:
                print("WARNING: Could not create a valid tracker. Tracking will be disabled.")
        except Exception as e:
            print(f"WARNING: Your OpenCV version does not support tracking. Error: {e}")
            print("Using detection-only mode.")
            has_tracking_support = False
        
    # Set processing frequency based on tracking support
    if has_tracking_support:
        process_every = 5  # Process detection every 5 frames, use tracking for in-between frames
        print("Using tracking-enhanced detection (processing every 5th frame)")
    else:
        process_every = 1  # Process every frame if no tracking support
        print("Using detection-only mode (processing every frame)")
        
    detection_interval = process_every  # How often to run full detection
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Initialize tracker structures if tracking is supported
    trackers = []  # List of active trackers
    tracked_objects = []  # List of objects being tracked (with their bounding boxes)
    tracker_max_age = 20  # Maximum number of frames to keep a tracker without re-detection
    
    # Report detection model loading completion
    if job_id:
        update_job_progress(job_id, 15, "Detection models loaded", 'step-detect', 'step-analyze')
    
    # Process frames
    start_processing_time = time.time()
    last_time_check = start_processing_time
    
    while True:
        # Check if job has been cancelled
        if job_id and job_id in processing_jobs and processing_jobs[job_id].get('status') == 'cancelled':
            print(f"Job {job_id} was cancelled by user")
            break
            
        success, frame = cap.read()
        if not success:
            break
            
        frame_count += 1
        
        # Update progress every 30 frames or at 5% intervals
        progress_interval = max(1, total_frames // 20)  # 5% intervals
        
        # For the initial info message
        if job_id and frame_count == 1:
            update_job_progress(
                job_id, 
                15, 
                f"Starting processing. Total frames to process: {total_frames}",
                'step-detect',
                None
            )
            
        # For subsequent progress updates
        current_time = time.time()
        if job_id and (frame_count % progress_interval == 0 or frame_count % 30 == 0 or current_time - last_time_check > 30):
            last_time_check = current_time
            progress = min(95, 15 + int(80 * frame_count / total_frames))
            
            # Calculate time estimate
            elapsed_time = current_time - start_processing_time
            frames_per_second = frame_count / elapsed_time if elapsed_time > 0 else 0
            
            # Create a basic message without translations for now
            pct_complete = 100 * frame_count / total_frames
            time_message = f"Processing frame {frame_count} of {total_frames} ({pct_complete:.1f}%). "
            
            if frames_per_second > 0:
                estimated_total_time = total_frames / frames_per_second
                remaining_time = max(0, estimated_total_time - elapsed_time)
                
                # Format the time estimate in minutes and seconds
                if remaining_time > 60:
                    minutes = int(remaining_time // 60)
                    seconds = int(remaining_time % 60)
                    time_message += f"Estimated time remaining: {minutes} min {seconds} sec. ({frames_per_second:.1f} FPS)"
                else:
                    seconds = int(remaining_time)
                    time_message += f"Estimated time remaining: {seconds} sec. ({frames_per_second:.1f} FPS)"
            else:
                time_message += "Calculating time estimate..."
            
            # Change step when we're halfway through processing
            current_step = 'step-detect'
            prev_step = None
            
            if frame_count > total_frames // 2:
                current_step = 'step-blur'
                prev_step = 'step-detect'
                
            update_job_progress(
                job_id, 
                progress, 
                time_message,
                current_step,
                prev_step
            )
        
        # Anvend wrap-around padding for at forbedre detektion ved 360° kant
        original_width = frame.shape[1]
        
        # Tilføj wrap-around padding til billedet
        wrapped_frame, pad_w = wrap_frame_for_detection(frame)
        
        # Initialize list to hold all detections (faces and plates)
        all_detections = []
        
        # Note: We no longer need to convert to grayscale since we're using only deep learning-based detection
        
        # Decide whether to run detection or use tracking for this frame
        if has_tracking_support:
            run_detection = (frame_count % detection_interval == 1) or (frame_count == 1) or (len(trackers) == 0)
        else:
            # If no tracking support, always run detection
            run_detection = True
        
        # Update existing trackers first (tracking is less computationally expensive than detection)
        temp_tracked_objects = []
        if has_tracking_support and len(trackers) > 0:
            print(f"Updating {len(trackers)} object trackers...")
            
            # Ensure tracked_objects has the same length as trackers
            if len(tracked_objects) != len(trackers):
                print(f"WARNING: Mismatch between trackers ({len(trackers)}) and tracked_objects ({len(tracked_objects)})")
                # If needed, fill in missing tracked_objects
                while len(tracked_objects) < len(trackers):
                    tracked_objects.append((0, 0, 10, 10))  # Default box, will be replaced by tracker update
            
            # For each existing tracker, update with current frame
            for i, (tracker, bbox) in enumerate(zip(trackers, tracked_objects)):
                # Determine object type
                object_type = 'face' if i < (len(tracked_objects) - num_plates) else 'plate'
                
                # Update tracker with current frame
                try:
                    success, new_bbox = tracker.update(frame)
                    if success:
                        # Extract updated coordinates
                        x, y, w, h = [int(v) for v in new_bbox]
                        
                        # Only keep valid boxes
                        if x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= frame.shape[1] and y + h <= frame.shape[0]:
                            # Add to temporary tracking list
                            temp_tracked_objects.append((x, y, w, h))
                            all_detections.append((x, y, w, h))
                            print(f"  - Tracking {object_type} at ({x},{y}), size {w}x{h}")
                except Exception as e:
                    print(f"  Error updating tracker {i} ({object_type}): {e}")
        
        # Run detection if scheduled or if tracking is not supported
        if run_detection:
            print(f"Frame {frame_count}: Running full detection...")
            
            # We'll initialize new trackers for all detected objects
            # Clear existing trackers and objects before setting up new ones
            trackers = []
            tracked_objects = []
            print("DEBUG: Cleared tracking lists before detection")
            
            # Using YOLO-based face detection for optimal accuracy
            print("Using YOLO face detection for optimal accuracy...")
            yolov8_face_detector = models["yolov8_face_detector"] if models and "yolov8_face_detector" in models else None
            
            # First try to use YOLO face detector (more accurate)
            if yolov8_face_detector is not None:
                try:
                    # Process the frame with YOLOv8 face detector - using a lower confidence threshold for better recall
                    # Process original frame
                    print("Running YOLO face detection on original frame")
                    results = yolov8_face_detector(frame, conf=0.35, verbose=False)  # Lower confidence for more detections
                    yolo_face_detections = []
                    
                    # Process results from original frame
                    for result in results:
                        for i, box in enumerate(result.boxes.xyxy.cpu().numpy()):  # Get boxes in xyxy format
                            x1, y1, x2, y2 = box[:4]
                            conf = float(result.boxes.conf.cpu().numpy()[i])  # Get confidence score
                            # Convert to xywh format
                            x, y, w, h = int(x1), int(y1), int(x2-x1), int(y2-y1)
                            yolo_face_detections.append((x, y, w, h, conf))
                    
                    # Process wrapped frame to detect faces at the 360° boundary
                    print("Running YOLO face detection on wrapped frame")
                    wrapped_results = yolov8_face_detector(wrapped_frame, conf=0.35, verbose=False)  # Lower confidence
                    wrapped_yolo_face_detections = []
                    
                    # Process results from wrapped frame
                    for result in wrapped_results:
                        for i, box in enumerate(result.boxes.xyxy.cpu().numpy()):
                            x1, y1, x2, y2 = box[:4]
                            conf = float(result.boxes.conf.cpu().numpy()[i])
                            # Convert to xywh format
                            x, y, w, h = int(x1), int(y1), int(x2-x1), int(y2-y1)
                            wrapped_yolo_face_detections.append((x, y, w, h, conf))
                    
                    # Adjust coordinates for wrapped detections
                    adjusted_wrapped_detections = []
                    for (x, y, w, h, conf) in wrapped_yolo_face_detections:
                        # Convert to format needed for the helper function
                        adjusted = adjust_coords_for_wrapped_detections([(x, y, w, h)], pad_w, original_width)
                        
                        # If detection isn't entirely outside the original frame, add it with its confidence
                        if adjusted:
                            adjusted_x, adjusted_y, adjusted_w, adjusted_h = adjusted[0]
                            adjusted_wrapped_detections.append((adjusted_x, adjusted_y, adjusted_w, adjusted_h, conf))
                    
                    # Report detections
                    if yolo_face_detections:
                        print(f"YOLO face detector found {len(yolo_face_detections)} faces in original frame:")
                        for i, (x, y, w, h, conf) in enumerate(yolo_face_detections):
                            print(f"  - YOLO Face {i+1}: Position ({x},{y}), Size {w}x{h}, Confidence: {conf:.2f}")
                        
                        # Add to overall detections list
                        for x, y, w, h, _ in yolo_face_detections:
                            # Create a tracker for each detection
                            try:
                                tracker = create_tracker()
                                if tracker is not None:
                                    # Initialize the tracker with the current frame and bounding box
                                    tracker.init(frame, (x, y, w, h))
                                    # Add the tracker and bounding box to our lists
                                    trackers.append(tracker)
                                    tracked_objects.append((x, y, w, h))
                                else:
                                    print(f"WARNING: Could not create tracker for face at ({x},{y}), size {w}x{h}")
                            except Exception as e:
                                print(f"Error creating tracker for face: {e}")
                            
                            # Add to current detections list regardless of tracker
                            all_detections.append((x, y, w, h))
                    else:
                        print("YOLO face detector found NO faces in original frame")
                    
                    if adjusted_wrapped_detections:
                        print(f"YOLO face detector found {len(adjusted_wrapped_detections)} additional faces in wrapped frame:")
                        for i, (x, y, w, h, conf) in enumerate(adjusted_wrapped_detections):
                            print(f"  - YOLO Wrapped Face {i+1}: Position ({x},{y}), Size {w}x{h}, Confidence: {conf:.2f}")
                        
                        # Add to overall detections list and trackers
                        for x, y, w, h, _ in adjusted_wrapped_detections:
                            # Create a tracker for each detection
                            try:
                                tracker = create_tracker()
                                if tracker is not None:
                                    # Initialize the tracker with the current frame and bounding box
                                    tracker.init(frame, (x, y, w, h))
                                    # Add the tracker and bounding box to our lists
                                    trackers.append(tracker)
                                    tracked_objects.append((x, y, w, h))
                                else:
                                    print(f"WARNING: Could not create tracker for wrapped face at ({x},{y}), size {w}x{h}")
                            except Exception as e:
                                print(f"Error creating tracker for wrapped face: {e}")
                            
                            # Add to current detections list regardless of tracker
                            all_detections.append((x, y, w, h))
                    else:
                        print("YOLO face detector found NO additional faces in wrapped frame")
                    
                except Exception as e:
                    print(f"Error during YOLO face detection: {e}")
                    print("Falling back to OpenCV DNN face detector if available")
                    # Fall back to OpenCV DNN if YOLO fails
                    yolov8_face_detector = None
        
        # Fallback to OpenCV DNN if YOLO is not available and we're in detection phase
        if run_detection and yolov8_face_detector is None and dnn_face_detector is not None:
            print("Using OpenCV DNN face detection as fallback...")
            
            # Process original frame
            print("Running DNN face detection on original frame")
            
            # Process at multiple scales to better detect faces at different sizes
            scales = [1.0, 0.75, 1.25]  # Process at normal size, smaller and larger scales
            
            for scale in scales:
                # Calculate dimensions for the current scale
                current_height = int(height * scale)
                current_width = int(width * scale)
                
                # Skip invalid scales
                if current_height <= 0 or current_width <= 0:
                    continue
                
                # Resize frame for current scale
                resized_frame = cv2.resize(frame, (current_width, current_height))
                
                # Prepare image for DNN processing
                blob = cv2.dnn.blobFromImage(
                    cv2.resize(resized_frame, (300, 300)), 
                    1.0, (300, 300), 
                    (104.0, 177.0, 123.0),
                    swapRB=False  # Don't swap channels for OpenCV BGR format
                )
                
                dnn_face_detector.setInput(blob)
                detections = dnn_face_detector.forward()
                
                # Process DNN detections with confidence threshold
                dnn_face_detections = []
                for i in range(0, detections.shape[2]):
                    confidence = detections[0, 0, i, 2]
                    # Using slightly lower threshold (0.4) to catch more faces
                    if confidence > 0.4:
                        box = detections[0, 0, i, 3:7] * np.array([current_width, current_height, current_width, current_height])
                        (startX, startY, endX, endY) = box.astype("int")
                        
                        # Scale back to original image dimensions
                        startX = int(startX / scale)
                        startY = int(startY / scale)
                        endX = int(endX / scale)
                        endY = int(endY / scale)
                        
                        # Ensure coordinates are within image boundaries
                        startX = max(0, startX)
                        startY = max(0, startY)
                        endX = min(width, endX)
                        endY = min(height, endY)
                        
                        # Skip invalid detections
                        if startX >= endX or startY >= endY:
                            continue
                            
                        # Convert to x, y, w, h format
                        x, y, w, h = startX, startY, endX - startX, endY - startY
                        
                        # Add to DNN detection list with confidence
                        dnn_face_detections.append((x, y, w, h, confidence))
                
                # Report DNN face detections
                if dnn_face_detections:
                    print(f"DNN face detector found {len(dnn_face_detections)} faces at scale {scale}:")
                    for i, (x, y, w, h, conf) in enumerate(dnn_face_detections):
                        print(f"  - DNN Face {i+1}: Position ({x},{y}), Size {w}x{h}, Confidence: {conf:.2f}")
                    
                    # Add to overall detections list and create trackers
                    for x, y, w, h, _ in dnn_face_detections:
                        # Create a tracker for each detection
                        try:
                            tracker = create_tracker()
                            if tracker is not None:
                                # Initialize the tracker
                                tracker.init(frame, (x, y, w, h))
                                # Add to tracker lists
                                trackers.append(tracker)
                                tracked_objects.append((x, y, w, h))
                            else:
                                print(f"WARNING: Could not create tracker for DNN face at ({x},{y}), size {w}x{h}")
                        except Exception as e:
                            print(f"Error creating tracker for DNN face: {e}")
                        
                        # Also add to current detections regardless of tracker
                        all_detections.append((x, y, w, h))
                else:
                    print(f"DNN face detector found NO faces at scale {scale}")
            
            # Process wrapped frame to catch faces at the 360° boundary
            print("Running DNN face detection on wrapped frame")
            
            # Prepare wrapped frame for DNN processing
            wrapped_blob = cv2.dnn.blobFromImage(
                cv2.resize(wrapped_frame, (300, 300)), 
                1.0, (300, 300), 
                (104.0, 177.0, 123.0),
                swapRB=False
            )
            
            dnn_face_detector.setInput(wrapped_blob)
            wrapped_detections = dnn_face_detector.forward()
            
            # Process wrapped frame DNN detections
            wrapped_dnn_face_detections = []
            for i in range(0, wrapped_detections.shape[2]):
                confidence = wrapped_detections[0, 0, i, 2]
                if confidence > 0.4:
                    # Get bounding box coordinates in full 300x300 image space
                    box = wrapped_detections[0, 0, i, 3:7] * np.array([300, 300, 300, 300])
                    
                    # Scale to wrapped frame dimensions
                    box = box * np.array([wrapped_frame.shape[1]/300, wrapped_frame.shape[0]/300, 
                                         wrapped_frame.shape[1]/300, wrapped_frame.shape[0]/300])
                    
                    (startX, startY, endX, endY) = box.astype("int")
                    
                    # Convert to x, y, w, h format
                    x, y, w, h = startX, startY, endX - startX, endY - startY
                    
                    # Add to wrapped detections list
                    wrapped_dnn_face_detections.append((x, y, w, h, confidence))
            
            # Adjust coordinates for wrapped detections
            adjusted_wrapped_detections = []
            for (x, y, w, h, conf) in wrapped_dnn_face_detections:
                # Convert to format needed for the helper function
                adjusted = adjust_coords_for_wrapped_detections([(x, y, w, h)], pad_w, original_width)
                
                # If detection isn't entirely outside the original frame, add it with its confidence
                if adjusted:
                    adjusted_x, adjusted_y, adjusted_w, adjusted_h = adjusted[0]
                    adjusted_wrapped_detections.append((adjusted_x, adjusted_y, adjusted_w, adjusted_h, conf))
            
            # Report wrapped frame detections
            if adjusted_wrapped_detections:
                print(f"DNN face detector found {len(adjusted_wrapped_detections)} additional faces in wrapped frame:")
                for i, (x, y, w, h, conf) in enumerate(adjusted_wrapped_detections):
                    print(f"  - DNN Wrapped Face {i+1}: Position ({x},{y}), Size {w}x{h}, Confidence: {conf:.2f}")
                
                # Add to overall detections list and create trackers
                for x, y, w, h, _ in adjusted_wrapped_detections:
                    # Create a tracker for each detection 
                    try:
                        tracker = create_tracker()
                        if tracker is not None:
                            # Initialize the tracker
                            tracker.init(frame, (x, y, w, h))
                            # Add to tracker lists
                            trackers.append(tracker)
                            tracked_objects.append((x, y, w, h))
                        else:
                            print(f"WARNING: Could not create tracker for DNN wrapped face at ({x},{y}), size {w}x{h}")
                    except Exception as e:
                        print(f"Error creating tracker for DNN wrapped face: {e}")
                    
                    # Also add to current detections regardless of tracker
                    all_detections.append((x, y, w, h))
            else:
                print("DNN face detector found NO additional faces in wrapped frame")
        
        # Show warning if no face detectors are available during detection phase
        if run_detection and yolov8_face_detector is None and dnn_face_detector is None:
            print("WARNING: No face detectors available! Please run download_models.py to get the required models.")
        
        # 3. License plate detection using deep learning only (if we're in detection phase)
        num_plates = 0
        if run_detection:  # Only run license plate detection during detection frames
            # Using YOLOv8-based license plate detection (Modern approach)
            if models["yolov8_plate_detector"] is not None:
                try:
                    # Run YOLOv8 detection on both original and wrapped frames for best results
                    # Øget confidence threshold til 0.55 for at reducere falske positiver yderligere
                    yolo_results = models["yolov8_plate_detector"](frame, conf=0.55)  # Even higher confidence for fewer false positives
                    yolo_plates = []
                    yolo_confidences = []
                    
                    # Process results from original frame
                    for result in yolo_results:
                        for i, box in enumerate(result.boxes.xyxy.cpu().numpy()):  # Get boxes in xyxy format
                            x1, y1, x2, y2 = box[:4]
                            conf = float(result.boxes.conf.cpu().numpy()[i])  # Get confidence score
                            # Convert to xywh format from xyxy
                            x, y, w, h = int(x1), int(y1), int(x2-x1), int(y2-y1)
                            yolo_plates.append((x, y, w, h))
                            yolo_confidences.append(conf)
                    
                    # Also process wrapped frame to catch detections at the edges
                    wrapped_yolo_results = models["yolov8_plate_detector"](wrapped_frame, conf=0.55)
                    wrapped_yolo_plates = []
                    wrapped_yolo_confidences = []
                    
                    for result in wrapped_yolo_results:
                        for i, box in enumerate(result.boxes.xyxy.cpu().numpy()):
                            x1, y1, x2, y2 = box[:4]
                            conf = float(result.boxes.conf.cpu().numpy()[i])  # Get confidence score
                            # Convert to xywh format
                            x, y, w, h = int(x1), int(y1), int(x2-x1), int(y2-y1)
                            wrapped_yolo_plates.append((x, y, w, h))
                            wrapped_yolo_confidences.append(conf)
                    
                    # Adjust coordinates for wrapped detections
                    adjusted_wrapped_plates = adjust_coords_for_wrapped_detections(wrapped_yolo_plates, pad_w, original_width)
                    
                    # Detailed logging for license plates with confidence scores
                    if len(yolo_plates) > 0:
                        print(f"YOLOv8 detected {len(yolo_plates)} license plates in original frame:")
                        for i, (x, y, w, h) in enumerate(yolo_plates):
                            print(f"  - Plate {i+1}: Position ({x},{y}), Size {w}x{h}, Confidence: {yolo_confidences[i]:.2f}")
                        
                        # Add to detections and create trackers
                        for x, y, w, h in yolo_plates:
                            # Create a tracker for each detection
                            try:
                                tracker = create_tracker()
                                if tracker is not None:
                                    # Initialize the tracker
                                    tracker.init(frame, (x, y, w, h))
                                    # Add to tracker lists - at the end (after face trackers)
                                    trackers.append(tracker)
                                    tracked_objects.append((x, y, w, h))
                                else:
                                    print(f"WARNING: Could not create tracker for license plate at ({x},{y}), size {w}x{h}")
                            except Exception as e:
                                print(f"Error creating tracker for license plate: {e}")
                            
                            # Also add to current detections regardless of tracker
                            all_detections.append((x, y, w, h))
                            # Increment license plate count
                            num_plates += 1
                    else:
                        print("YOLOv8 detected NO license plates in original frame")
                    
                    if len(adjusted_wrapped_plates) > 0:
                        print(f"YOLOv8 detected {len(adjusted_wrapped_plates)} additional license plates in wrapped frame:")
                        for i, (x, y, w, h) in enumerate(adjusted_wrapped_plates):
                            if i < len(wrapped_yolo_confidences):  # Make sure we have a matching confidence
                                print(f"  - Plate {i+1}: Position ({x},{y}), Size {w}x{h}, Confidence: {wrapped_yolo_confidences[i]:.2f}")
                        
                        # Add to detections and create trackers
                        for x, y, w, h in adjusted_wrapped_plates:
                            # Create a tracker for each detection
                            try:
                                tracker = create_tracker()
                                if tracker is not None:
                                    # Initialize the tracker
                                    tracker.init(frame, (x, y, w, h))
                                    # Add to tracker lists - at the end (after face trackers)
                                    trackers.append(tracker)
                                    tracked_objects.append((x, y, w, h))
                                else:
                                    print(f"WARNING: Could not create tracker for wrapped plate at ({x},{y}), size {w}x{h}")
                            except Exception as e:
                                print(f"Error creating tracker for wrapped plate: {e}")
                            
                            # Also add to current detections regardless of tracker
                            all_detections.append((x, y, w, h))
                            # Increment license plate count
                            num_plates += 1
                    else:
                        print("YOLOv8 detected NO additional license plates in wrapped frame")
                    
                except Exception as e:
                    print(f"Error during YOLOv8 license plate detection: {e}")
            else:
                print("YOLOv8 license plate detector not available. Using only face detection.")
        
        # YOLOv3 er fjernet - vi bruger kun YOLOv8
        
        # Apply Non-Maximum Suppression to merge overlapping detections
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
        
        # Group overlapping detections using Non-Maximum Suppression
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
                if iou > 0.3:  # Adjust threshold as needed
                    # Create a bounding box that includes both detections
                    merged_x = min(x1, x2)
                    merged_y = min(y1, y2)
                    merged_w = max(x1 + w1, x2 + w2) - merged_x
                    merged_h = max(y1 + h1, y2 + h2) - merged_y
                    
                    merged_box = [merged_x, merged_y, merged_w, merged_h]
                    used_indices.add(j)
            
            merged_detections.append(tuple(merged_box))
            
        # Replace original detections with merged ones
        final_detections_count = len(all_detections)
        all_detections = merged_detections
        
        # Print progress and detection count
        if frame_count % 30 == 0 or len(all_detections) > 0:
            print(f"Processing frame {frame_count}/{total_frames} - Found {len(all_detections)} regions to blur")
            
        # Set face detection counts for debug coloring
        # Count YOLO face detections first (primary detector)
        num_faces = 0
        if 'yolo_face_detections' in locals():
            num_faces += len(yolo_face_detections)
        if 'adjusted_wrapped_detections' in locals() and yolov8_face_detector is not None:
            num_faces += len(adjusted_wrapped_detections)
            
        # Add OpenCV DNN detections if YOLO wasn't used
        if yolov8_face_detector is None and 'dnn_face_detections' in locals():
            num_faces += len(dnn_face_detections)
            if 'adjusted_wrapped_detections' in locals():
                num_faces += len(adjusted_wrapped_detections)
        
        # Get number of detected license plates (from YOLO only)
        num_plates = 0
        if 'yolo_plates' in locals():
            num_plates += len(yolo_plates)
        if 'wrapped_yolo_plates' in locals():
            num_plates += len(wrapped_yolo_plates)
        
        # 4. Apply blur to all detected regions
        for i, (x, y, w, h) in enumerate(all_detections):
            # Validate detection coordinates
            if x < 0 or y < 0 or w <= 0 or h <= 0:
                continue
                
            # Add padding around detection for better coverage
            padding = int(w * 0.1)  # 10% padding
            x_padded = max(0, x - padding)
            y_padded = max(0, y - padding)
            w_padded = min(width - x_padded, w + 2*padding)
            h_padded = min(height - y_padded, h + 2*padding)
            
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
                    # Apply a stronger blur for better anonymization
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
                        # Use different colors for different detection types
                        if i < num_faces:  # Face detection (YOLO or DNN)
                            color = (0, 0, 255)  # Red for face detections
                        else:  # License plate detections
                            color = (255, 0, 0)  # Blue for license plate detections
                            
                        cv2.rectangle(frame, (x_padded, y_padded), 
                                    (x_padded+w_padded, y_padded+h_padded), color, 2)
                except Exception as e:
                    print(f"Error applying blur: {e}, roi shape: {roi.shape}, kernel: {kernel_size}")
            except Exception as e:
                print(f"Error extracting ROI for detection at ({x},{y}): {e}")

        out.write(frame)

    cap.release()
    out.release()
    
    # Report finalization
    if job_id:
        update_job_progress(
            job_id, 
            98, 
            "Finalizing video output", 
            'step-finalize',
            'step-blur'
        )
        
        # Short delay to ensure output file is fully written
        time.sleep(1)
        
        # Report completion
        update_job_progress(
            job_id, 
            100, 
            "Processing complete!", 
            'step-finalize'
        )

if __name__ == '__main__':
    try:
        # Initialize translation directory
        translations_dir = Path("translations")
        if not translations_dir.exists():
            translations_dir.mkdir()
            
            # Create basic babel.cfg file
            with open("babel.cfg", "w") as f:
                f.write("[python: **.py]\n[jinja2: **/templates/**.html]\nextensions=jinja2.ext.autoescape,jinja2.ext.with_\n")
                
            print("Created translations directory and babel.cfg")
            print("To extract translations, run: pybabel extract -F babel.cfg -o messages.pot .")
            print("To initialize a language, run: pybabel init -i messages.pot -d translations -l <language_code>")
            print("To compile translations, run: pybabel compile -d translations")
        
        # Check for model files
        if not Path("models/res10_300x300_ssd_iter_140000.caffemodel").exists():
            print("\nWARNING: DNN face detection model not found!")
            print("For better face detection, run: python download_models.py")
            
        # Check for either YOLOv3 or YOLOv8 license plate models
        yolov3_available = Path("models/yolov3_lp.cfg").exists() and Path("models/yolov3_lp.weights").exists()
        yolov8_available = Path("models/yolov8n_lp.pt").exists()
        
        if not (yolov3_available or yolov8_available):
            print("\nWARNING: No YOLO license plate model found!")
            print("For license plate detection, either:")
            print("1. Run 'python download_models.py' to get the YOLOv8 model (recommended)")
            print("2. Download YOLOv3 models and place them in 'models' as 'yolov3_lp.cfg' and 'yolov3_lp.weights'")
        
        # Get server configuration
        host = app.config['HOST']
        port = app.config['PORT']
        debug = app.config['DEBUG']
        
        # Check for CloudFlare configuration
        cloudflare_enabled = config.getboolean('cloudflare', 'enabled', fallback=False)
        cloudflare_hostname = config.get('cloudflare', 'hostname', fallback=None)
        
        if cloudflare_enabled and cloudflare_hostname:
            print(f"\nStarting server with CloudFlare Tunnel enabled")
            print(f"Your 360blur instance will be accessible at https://{cloudflare_hostname}")
            # When using CloudFlare, we bind only to localhost
            host = '127.0.0.1'
        
        print(f"\nStarting server on http://{host}:{port}")
        print(f"Press Ctrl+C to stop the server")
        
        # Check if we're binding to all interfaces
        if host == '0.0.0.0':
            print(f"Server will be accessible from other devices on your network")
            local_ip = socket.gethostbyname(socket.gethostname())
            print(f"You can access it at http://{local_ip}:{port}")
        
        # Run with Socket.IO
        # Different versions of Flask-SocketIO have different APIs
        try:
            # Newer versions
            print("Starting Socket.IO server with WebSocket support...")
            socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)
        except TypeError:
            try:
                # Older versions
                socketio.run(app, host=host, port=port, debug=debug)
            except Exception as e:
                print(f"Error starting SocketIO: {e}")
                print("Falling back to regular Flask server")
                app.run(host=host, port=port, debug=debug)
    except OSError as e:
        logging.error(f"Could not start server: {e}")
        print(f"Check if port {port} is already in use, or if you have permissions to bind to the address.")
        print("To use a different port, edit the config.ini file and change the port setting.")

