#!/usr/bin/env python3
"""
Download-script til at hente DNN-modelfiler til 360° video blur værktøjet.
Dette script håndterer automatisk download af alle nødvendige modeller under installationen.
"""

import os
import sys
import time
import urllib.request
import requests
import shutil
from pathlib import Path

def download_file(url, destination, retries=3, retry_delay=2):
    """
    Download a file from URL to destination with progress bar and robust retry logic
    
    Args:
        url: URL til download
        destination: Destination filepath
        retries: Number of retries on failure
        retry_delay: Seconds to wait between retries
    """
    # Brug requests for mere robust filhåndtering
    def download_with_requests():
        print(f"Downloading {os.path.basename(destination)} from {url}")
        try:
            # Hent fil med progress
            with requests.get(url, stream=True, timeout=30) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                
                if total_size == 0:
                    print("Warning: Unable to determine file size")
                
                downloaded = 0
                with open(destination, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = min(int(downloaded * 100 / total_size), 100)
                                sys.stdout.write(f"\r{percent}% [{downloaded} / {total_size}] bytes")
                            else:
                                sys.stdout.write(f"\rDownloaded {downloaded} bytes")
                            sys.stdout.flush()
                
                print(f"\nFærdig med download af {os.path.basename(destination)}")
                if os.path.exists(destination) and os.path.getsize(destination) > 0:
                    print(f"Fil størrelse: {os.path.getsize(destination):,} bytes")
                    return True
                else:
                    print(f"Fejl: Filen blev downloadet, men er tom eller mangler.")
                    return False
        except requests.exceptions.RequestException as e:
            print(f"\nFejl ved download: {e}")
            return False
    
    # Fallback til urllib hvis requests ikke er tilgængelig
    def download_with_urllib():
        print(f"Downloader (urllib fallback) {os.path.basename(destination)} fra {url}")
        
        def progress_bar(block_num, block_size, total_size):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(int(downloaded * 100 / total_size), 100)
                sys.stdout.write(f"\r{percent}% [{downloaded} / {total_size}] bytes")
            else:
                sys.stdout.write(f"\rDownloaded {downloaded} bytes")
            sys.stdout.flush()
        
        try:
            # Set a timeout of 30 seconds
            urllib.request.urlretrieve(url, destination, progress_bar)
            print(f"\nFærdig med download af {os.path.basename(destination)}")
            
            # Verify file was downloaded correctly
            if os.path.exists(destination) and os.path.getsize(destination) > 0:
                print(f"Fil størrelse: {os.path.getsize(destination):,} bytes")
                return True
            else:
                print(f"Fejl: Filen blev downloadet, men er tom eller mangler.")
                return False
        except Exception as e:
            print(f"\nFejl ved download: {e}")
            return False
    
    # Sikrer at destinationsmappen findes
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    
    # Prøv download med retry-logik
    for attempt in range(retries):
        try:
            # Prøv først requests (bedre fejlhåndtering)
            try:
                import requests
                success = download_with_requests()
            except ImportError:
                # Hvis requests ikke er installeret, brug urllib
                success = download_with_urllib()
                
            if success:
                return True
            
            if attempt < retries - 1:
                print(f"Download fejlede. Forsøger igen om {retry_delay} sekunder... (forsøg {attempt+1}/{retries})")
                time.sleep(retry_delay)
                # Fordobl retry delay for hver fejl (eksponentiel backoff)
                retry_delay *= 2
            else:
                print(f"Kunne ikke downloade efter {retries} forsøg.")
                # Prøv alternative URL'er hvis tilgængelige
                filename = os.path.basename(destination)
                alternative_urls = {
                    "deploy.prototxt": "https://github.com/opencv/opencv/raw/master/samples/dnn/face_detector/deploy.prototxt",
                    "res10_300x300_ssd_iter_140000.caffemodel": "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel",
                    "yolov8n_face.pt": "https://github.com/akanametov/yolov8-face/releases/download/v0.0.0/yolov8n-face.pt",
                    "yolov8n_lp.pt": "https://huggingface.co/yasirfaizahmed/license-plate-object-detection/resolve/main/best.pt"
                }
                if filename in alternative_urls and alternative_urls[filename] != url:
                    print(f"Prøver alternativ URL for {filename}...")
                    return download_file(alternative_urls[filename], destination, retries=1)
                return False
        except Exception as e:
            print(f"Uventet fejl: {e}")
            if attempt < retries - 1:
                print(f"Prøver igen om {retry_delay} sekunder...")
                time.sleep(retry_delay)
            else:
                print(f"Maksimum antal forsøg opbrugt.")
                return False
    
    return False

def main():
    """Main function for downloading detection models"""
    # Opret models directory
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    # Liste over alle model-filer der skal downloades
    model_files = [
        # OpenCV DNN face detection models
        {
            "type": "Face Detection (OpenCV)",
            "url": "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt",
            "dest": models_dir / "deploy.prototxt",
            "size": "29 KB",
            "required": True,
            "backup_url": "https://github.com/rpaasch/360blur-model-mirror/raw/main/deploy.prototxt"
        },
        {
            "type": "Face Detection (OpenCV)",
            "url": "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel",
            "dest": models_dir / "res10_300x300_ssd_iter_140000.caffemodel",
            "size": "10 MB",
            "required": True,
            "backup_url": "https://github.com/rpaasch/360blur-model-mirror/raw/main/res10_300x300_ssd_iter_140000.caffemodel"
        },
        
        # YOLO face detection model
        {
            "type": "Face Detection (YOLO)",
            "url": "https://github.com/akanametov/yolov8-face/releases/download/v0.0.0/yolov8n-face.pt",
            "dest": models_dir / "yolov8n_face.pt",
            "size": "6 MB", 
            "required": False,
            "backup_url": "https://github.com/rpaasch/360blur-model-mirror/raw/main/yolov8n_face.pt"
        },
        
        # YOLO license plate detection model
        {
            "type": "License Plate Detection (YOLO)",
            "url": "https://huggingface.co/yasirfaizahmed/license-plate-object-detection/resolve/main/best.pt",
            "dest": models_dir / "yolov8n_lp.pt",
            "size": "6 MB",
            "required": False,
            "backup_url": "https://github.com/rpaasch/360blur-model-mirror/raw/main/yolov8n_lp.pt"
        }
    ]
    
    # Statusstatistik
    success_count = 0
    fail_count = 0
    model_types = {}
    
    # Track hvis vi skal installere ultralytics
    need_ultralytics = False
    
    print("\n=== Downloading detection models for 360blur ===\n")
    print(f"Models will be saved to: {models_dir.absolute()}\n")
    
    # Download each model
    for model in model_files:
        model_type = model["type"]
        if model_type not in model_types:
            model_types[model_type] = {"success": True}
        
        print(f"\n--- Downloading {model_type}: {os.path.basename(model['dest'])} ({model['size']}) ---")
        
        # Prøv først hovedURL
        success = download_file(model["url"], model["dest"])
        
        # Hvis det fejler, prøv backup URL
        if not success and "backup_url" in model:
            print(f"Trying backup URL...")
            success = download_file(model["backup_url"], model["dest"])
        
        # Opdater status
        if success:
            success_count += 1
            if "YOLO" in model_type:
                need_ultralytics = True
        else:
            fail_count += 1
            model_types[model_type]["success"] = False
            if model["required"]:
                print(f"WARNING: Failed to download required model {os.path.basename(model['dest'])}")
    
    # Vis opsummering
    print("\n=== Model Download Summary ===")
    print(f"Successfully downloaded {success_count} of {len(model_files)} models")
    
    for model_type, status in model_types.items():
        status_text = "SUCCESS" if status["success"] else "FAILED"
        status_color = "\033[92m" if status["success"] else "\033[91m" 
        print(f"{status_color}{model_type}: {status_text}\033[0m")
    
    # Hvis vi har fejl, vis løsningsforslag
    if fail_count > 0:
        print("\n=== Troubleshooting ===")
        print("Some model downloads failed. You can try:")
        print("1. Check your internet connection")
        print("2. Run the script again (python download_models.py)")
        print("3. Try manual download and place files in the models/ directory")
        
        # Show OpenCV manual download commands if needed
        if "Face Detection (OpenCV)" in model_types and not model_types["Face Detection (OpenCV)"]["success"]:
            print("\nManual download for OpenCV models:")
            print("curl -O https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt")
            print("curl -L -o res10_300x300_ssd_iter_140000.caffemodel https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel")
    
    # YOLO-relaterede instruktioner
    if need_ultralytics:
        print("\n=== YOLO Models Setup ===")
        print("To use YOLO-based detection (recommended for best accuracy):")
        print("1. Install Ultralytics: pip install ultralytics")
        print("2. Restart the 360blur application")
        
        # Check if ultralytics is already installed
        try:
            import importlib.util
            if importlib.util.find_spec("ultralytics"):
                print("\033[92mUltralytics is already installed!\033[0m")
            else:
                print("\033[93mUltralytics not detected. Install with: pip install ultralytics\033[0m")
        except:
            print("\033[93mCould not verify if ultralytics is installed\033[0m")
    
    print("\n=== Next Steps ===")
    if success_count == len(model_files):
        print("\033[92mAll models downloaded successfully!\033[0m")
        print("You can now run the 360blur application with: python blur360_webapp.py")
    elif success_count > 0:
        print("\033[93mSome models downloaded. Basic functionality should work.\033[0m")
        print("You can run the application, but some detection features may be limited.")
    else:
        print("\033[91mNo models downloaded. The application will not function correctly.\033[0m")
        print("Please resolve download issues before running the application.")

if __name__ == "__main__":
    main()