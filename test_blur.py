"""
Test script for the face and license plate blurring functionality
"""
import sys
import cv2
import os
from blur360_webapp import load_dnn_models, process_video

# Test video file - use one from the uploads folder if available
test_file = None
upload_dir = "uploads"
if os.path.exists(upload_dir) and os.listdir(upload_dir):
    test_file = os.path.join(upload_dir, os.listdir(upload_dir)[0])

if not test_file or not os.path.exists(test_file):
    print("No test file found in uploads directory")
    print("Please place a video file in the uploads directory")
    sys.exit(1)

print(f"Testing blurring with file: {test_file}")
output_file = "test_blurred.mp4"

# Load models
models = load_dnn_models()

# Process the video with debug mode on
debug_mode = True
print("Processing video with debug mode ON...")
process_video(
    test_file, 
    output_file, 
    debug_mode=debug_mode, 
    use_dnn=True, 
    models=models, 
    job_id=None, 
    skip_tracking=False,
    disable_legacy_tracking=False  # Try with tracking enabled
)

print(f"Processing complete. Output file: {output_file}")
print(f"Check the console output for debugging information.")