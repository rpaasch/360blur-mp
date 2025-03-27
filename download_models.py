#!/usr/bin/env python3
"""
Download-script til at hente DNN-modelfiler til 360° video blur værktøjet
"""

import os
import sys
import urllib.request
from pathlib import Path

def download_file(url, destination):
    """Download a file from URL to destination with progress bar"""
    print(f"Downloading {os.path.basename(destination)} from {url}")
    
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
            print(f"Fil størrelse: {os.path.getsize(destination)} bytes")
            return True
        else:
            print(f"Fejl: Filen blev downloadet, men er tom eller mangler.")
            return False
    except urllib.error.URLError as e:
        print(f"\nURL fejl ved download: {e}")
        print("Kontroller din internetforbindelse og prøv igen.")
        print("Evt. blokerer en firewall adgangen.")
        return False
    except urllib.error.HTTPError as e:
        print(f"\nHTTP fejl ved download: {e}")
        print(f"Serveren returnerede en fejl. URL'en er muligvis forældet eller forkert.")
        alternative_urls = {
            "deploy.prototxt": "https://github.com/opencv/opencv/raw/master/samples/dnn/face_detector/deploy.prototxt",
            "res10_300x300_ssd_iter_140000.caffemodel": "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"
        }
        filename = os.path.basename(destination)
        if filename in alternative_urls:
            print(f"Prøver alternativ URL for {filename}...")
            return download_file(alternative_urls[filename], destination)
        return False
    except Exception as e:
        print(f"\nFejl ved download: {e}")
        return False

def main():
    # Create models directory
    models_dir = Path("models")
    models_dir.mkdir(exist_ok=True)
    
    # Face detection models
    face_model_files = [
        {
            "url": "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt",
            "dest": models_dir / "deploy.prototxt"
        },
        {
            "url": "https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel",
            "dest": models_dir / "res10_300x300_ssd_iter_140000.caffemodel"
        }
    ]
    
    # License plate detection model 
    # YOLOv8n License Plate-specific model from Hugging Face
    license_plate_model_files = [
        {
            "url": "https://huggingface.co/yasirfaizahmed/license-plate-object-detection/resolve/main/best.pt",
            "dest": models_dir / "yolov8n_lp.pt"
        }
    ]
    
    # YOLO face detection model - using a pre-trained YOLOv8n face detection model
    # Using a publicly accessible alternative source
    yolo_face_model_files = [
        {
            "url": "https://github.com/akanametov/yolov8-face/releases/download/v0.0.0/yolov8n-face.pt",
            "dest": models_dir / "yolov8n_face.pt"
        }
    ]
    
    print("Downloading DNN face detection models...")
    success = True
    
    for file_info in face_model_files:
        if not download_file(file_info["url"], file_info["dest"]):
            success = False
            
    print("\nDownloading license plate detection models...")
    license_plate_success = True
    
    for file_info in license_plate_model_files:
        if not download_file(file_info["url"], file_info["dest"]):
            license_plate_success = False
    
    print("\nDownloading YOLO face detection models...")
    yolo_face_success = True
    
    for file_info in yolo_face_model_files:
        if not download_file(file_info["url"], file_info["dest"]):
            yolo_face_success = False
    
    if success and license_plate_success and yolo_face_success:
        print("\nAlle modeller hentet korrekt!")
        print("Du kan nu anvende moderne deep learning-baseret ansigtsgenkendelse og nummerpladegenkendelse.")
    else:
        print("\nNogen af modeldownloads fejlede. Status:")
        print(f"- OpenCV DNN ansigtsmodel: {'SUCCESS' if success else 'FAILED'}")
        print(f"- YOLO nummerplademodel: {'SUCCESS' if license_plate_success else 'FAILED'}")
        print(f"- YOLO ansigtsmodel: {'SUCCESS' if yolo_face_success else 'FAILED'}")
        print("\nHer er kommandoer til eventuel manuel download:")
        
    if not success:
        print("\nAnsigts-modeller - Manuel download:")
        print("\nPå macOS eller Linux:")
        print("mkdir -p models")
        print("cd models")
        print("curl -O https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt")
        print("curl -L -o res10_300x300_ssd_iter_140000.caffemodel https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel")
        print("cd ..")
        
        print("\nPå Windows (i PowerShell):")
        print("New-Item -ItemType Directory -Force -Path models")
        print("Invoke-WebRequest -Uri \"https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt\" -OutFile \"models\\deploy.prototxt\"")
        print("Invoke-WebRequest -Uri \"https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel\" -OutFile \"models\\res10_300x300_ssd_iter_140000.caffemodel\"")
    
    if not license_plate_success:
        print("\nYOLOv8 nummerplade-model - Manuel download:")
        print("\nPå macOS eller Linux:")
        print("mkdir -p models")
        print("cd models")
        print("curl -O https://huggingface.co/yasirfaizahmed/license-plate-object-detection/resolve/main/best.pt -o yolov8n_lp.pt")
        print("cd ..")
        
        print("\nPå Windows (i PowerShell):")
        print("New-Item -ItemType Directory -Force -Path models")
        print("Invoke-WebRequest -Uri \"https://huggingface.co/yasirfaizahmed/license-plate-object-detection/resolve/main/best.pt\" -OutFile \"models\\yolov8n_lp.pt\"")
    
    print("\nBemærk om YOLOv8 modellen:")
    print("For at bruge YOLOv8 nummerplademodellen (yolov8n_lp.pt), skal du:")
    print("1. Installere Ultralytics YOLO biblioteket: pip install ultralytics")
    print("2. Genstart programmet")
    print("\nUden denne model vil nummerpladedetektion være begrænset.")

if __name__ == "__main__":
    main()