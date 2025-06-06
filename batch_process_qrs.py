"""
This script provides a utility to batch process images in a specified directory.
It first attempts to detect a ChArUco board in each image and then, using the
(potentially modified) image from ChArUco detection, detects and highlights
QR codes.

It iterates through all files in the target directory, identifies supported
image files, and for each image:
1. Calls `detect_charuco_board` (from `charuco_detector.py`) to find ChArUco
   board patterns. The ChArUco board parameters (dimensions, marker size, etc.)
   are configurable within this script.
2. The image returned by `detect_charuco_board` (which may have ChArUco
   markers/corners drawn on it) is then passed to `detect_and_draw_qrcodes`
   (from `detect_and_draw_qr.py`).
3. This second function finds QR codes, draws highlights around them, and
   extracts cropped images of individual QR codes.
4. The main image (output of ChArUco detection, further modified with QR
   detections) is saved to a new file named `original_filename_qr_all.ext`.
5. Each successfully cropped individual QR code image is saved to files named
   `original_filename_qr_all.ext`.

This script is useful for processing a collection of images that may contain
both ChArUco boards and QR codes, visualizing all detections, and extracting
the individual QR code regions.

Requirements:
- OpenCV (cv2)
- qreader
- numpy (usually installed with opencv or qreader)
- The `detect_and_draw_qr.py` script must be accessible (e.g., in the same
  directory or in PYTHONPATH).
- The `charuco_detector.py` script must be accessible.

Usage:
1. Ensure required libraries are installed (`pip install opencv-python qreader numpy`).
2. Make sure `detect_and_draw_qr.py` and `charuco_detector.py` are in the
   same directory or accessible in PYTHONPATH.
3. Configure ChArUco board parameters (e.g., `squares_x`, `marker_length_mm`)
   at the top of this script if they differ from the defaults.
4. Modify the `target_image_directory` variable in the `if __name__ == "__main__":`
   block to point to the directory containing your images.
4. Run the script: `python batch_process_qrs.py`
5. The processed images and cropped QR codes will be saved in the same
   `target_image_directory`.

Note: The script assumes the `detect_and_draw_qrcodes` function returns a list
where the first element is the image with detections and subsequent elements
are cropped QR images.
Note:
- The script assumes `detect_charuco_board` returns an image (NumPy array) or None.
- It assumes `detect_and_draw_qrcodes` returns a list where the first element
  is the image with QR detections and subsequent elements are cropped QR images.
"""

import os
import cv2
# Assuming detect_and_draw_qr.py is in the same directory or accessible in PYTHONPATH
from charuco_detector import detect_charuco_board
from detect_and_draw_qr import detect_and_draw_qrcodes

# Define supported image extensions
SUPPORTED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.webp')

# --- Configuration for your specific board (MUST MATCH GENERATION SCRIPT) ---
squares_x = 5
squares_y = 5
board_width_cm = 5.0 # This is used to calculate square_length_mm
marker_length_mm = 7.0
dictionary_name = "DICT_4X4_100" # Ensure this matches the dictionary used for generation
# Calculate square length based on desired board width
square_length_mm = (board_width_cm * 10.0) / squares_x

def process_images_in_directory(directory_path):
    """
    Processes all images in a given directory. For each image, it first
    attempts ChArUco board detection, then performs QR code detection on the
    resulting image.

    The processing steps for each image are:
    1. Load the image.
    2. Call `detect_charuco_board` with pre-configured board parameters.
       This function may draw ChArUco detections on the image.
    3. Pass the image from step 2 to `detect_and_draw_qrcodes`.
    4. Save the results:
       - Main image with ChArUco (if any) and QR detections:
         `original_filename_qr_all.ext`
       - Cropped QR images: `original_filename_qr_N.ext`

    Args:
        directory_path (str): The path to the directory containing images.
    """
    if not os.path.isdir(directory_path):
        print(f"Error: '{directory_path}' is not a valid directory.")
        return

    print(f"Starting QR code processing for images in directory: '{directory_path}'")
    processed_files_count = 0
    image_files_found = 0

    for filename in os.listdir(directory_path):
        if filename.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS):
            image_files_found += 1
            input_image_abs_path = os.path.join(directory_path, filename)
            print(f"\nProcessing image: '{input_image_abs_path}'...")
            
            # Detect CharUcoBoards
            charuco_image = detect_charuco_board(input_image_abs_path, squares_x, squares_y, square_length_mm, marker_length_mm, dictionary_name)
            
            list_of_images = detect_and_draw_qrcodes(charuco_image)

            # Apply the QR detection and drawing function
            # list_of_images = detect_and_draw_qrcodes(input_image_abs_path)

            if list_of_images:  # Check if the list is not None and not empty
                # os.path.splitext splits "path/to/file.ext" into ("path/to/file", ".ext")
                input_file_root, input_ext = os.path.splitext(input_image_abs_path)

                # --- Save the main image (first in the list) ---
                main_image_to_save = list_of_images[0]
                output_detections_abs_path = f"{input_file_root}_qr_all{input_ext}"
                try:
                    cv2.imwrite(output_detections_abs_path, main_image_to_save)
                    print(f"  Saved main detection image to: '{output_detections_abs_path}'")
                except Exception as e:
                    print(f"  Error saving main detection image '{output_detections_abs_path}': {e}")

                # --- Save the cropped QR images, if any ---
                if len(list_of_images) > 1:
                    for i, cropped_img in enumerate(list_of_images[1:]):
                        # Construct the output path for each cropped QR image
                        cropped_qr_abs_path = f"{input_file_root}_qr_{i + 1}{input_ext}"
                        try:
                            cv2.imwrite(cropped_qr_abs_path, cropped_img)
                            print(f"  Saved cropped QR image to: '{cropped_qr_abs_path}'")
                        except Exception as e:
                            print(f"  Error saving cropped QR image '{cropped_qr_abs_path}': {e}")
                processed_files_count +=1
            else:
                # detect_and_draw_qrcodes prints its own error if image can't be read.
                # This else might be hit if it returns None or an empty list for other reasons,
                # or if no QR codes were found (though it still returns the original image in that case).
                print(f"  No QR codes processed or error during processing for '{input_image_abs_path}'.")
        # else:
            # Optional: print(f"Skipping non-supported file: {filename}")

    if image_files_found == 0:
        print(f"No image files with supported extensions {SUPPORTED_IMAGE_EXTENSIONS} found in '{directory_path}'.")
    else:
        print(f"\nBatch processing complete. Successfully processed and saved results for {processed_files_count}/{image_files_found} image(s).")

if __name__ == "__main__":
    # --- Configuration ---
    # IMPORTANT: Replace this with the actual path to your image directory
    # You can use an absolute path or a relative path if the script is run from a suitable location.
    # Example: target_image_directory = "path/to/your/images"
    target_image_directory = os.path.join(os.path.dirname(__file__), "sample_qr_images") # Default to a subfolder
    target_image_directory = "/Users/claudiograsso/Documents/Semillas/code/images"
    # --- End Configuration ---

    if not os.path.exists(target_image_directory):
        print(f"The target directory '{target_image_directory}' does not exist.")
        print("Please create it and add some images, or modify the 'target_image_directory' variable in the script.")
        try:
            os.makedirs(target_image_directory, exist_ok=True)
            print(f"Attempted to create directory: '{target_image_directory}'. Please add images to it.")
        except OSError as e:
            print(f"Could not create directory '{target_image_directory}': {e}")
    elif not os.listdir(target_image_directory) and not any(f.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS) for f in os.listdir(target_image_directory)):
        print(f"The target directory '{target_image_directory}' is empty or contains no supported image files.")
        print(f"Please add some images (e.g., {', '.join(SUPPORTED_IMAGE_EXTENSIONS)}) to process.")
    else:
        process_images_in_directory(target_image_directory)