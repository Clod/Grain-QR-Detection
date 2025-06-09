import cv2
from qreader import QReader
import numpy as np
import os
import json
import zlib
import binascii # For robust hex decoding error handling

def _decode_zlib_json_qr(qr_text_content):
    """
    Attempts to decode a QR text content assuming it's a hex-encoded,
    zlib-compressed JSON string.

    Args:
        qr_text_content (str): The raw string content from a QR code.

    Returns:
        dict or None: The decoded JSON object if successful, otherwise None.
    """
    if not isinstance(qr_text_content, str):
        return None
    try:
        compressed_data = bytes.fromhex(qr_text_content)
        json_str = zlib.decompress(compressed_data).decode('utf-8')
        decoded_data = json.loads(json_str)
        return decoded_data
    except (ValueError, binascii.Error, zlib.error, UnicodeDecodeError, json.JSONDecodeError):
        # ValueError for non-hex string in fromhex
        # binascii.Error for odd-length string or non-hex characters in fromhex
        # zlib.error for decompression issues
        # UnicodeDecodeError for utf-8 decoding issues
        # json.JSONDecodeError for JSON parsing issues
        # print(f"    Debug: Failed to decode/decompress QR content as zlib/JSON: {e}") # Optional
        return None

def detect_and_draw_qrcodes(image_input):
    """
    Reads an image from disk, detects QR codes in it,
    draws a green quadrilateral around each detected QR code, and attempts
    to decode zlib-compressed JSON content from the QR text.

    Args:
        image_input (str or numpy.ndarray): Path to the input image file or the image itself (as a NumPy array).
    Returns:
        tuple (list[numpy.ndarray], list[str], list[Optional[dict]]) or (None, None, None):
            - A list of images:
                - The first image is the input image with QR codes highlighted.
                  If no QR codes are found, it's the original unmodified image.
                - Subsequent images are cropped individual QR code regions.
            - A list of strings, where each string is the decoded text of a
              corresponding QR code. The order matches the cropped images.
            - A list of decoded JSON objects (dict) or None if decoding failed
              for the corresponding QR code text. The order matches the other lists.
            Returns (None, None, None) if the image cannot be read or if input type is invalid.
            Returns ([original_image], [], []) if no QR codes are found.
    """
    # Create a QReader instance
    qreader_detector = QReader()

    if isinstance(image_input, str):
        # Input is a path, load the image
        original_image = cv2.imread(image_input)
        if original_image is None:
            print(f"Error: Could not read image from path: '{image_input}'")
            return None, None, None
    elif isinstance(image_input, np.ndarray):
        original_image = image_input.copy() # Work on a copy
    else:
        print(f"Error: Invalid input type. Expected string path or NumPy array, got {type(image_input)}.")
        return None, None, None

    # Initialize image_for_display with the original. It will be copied if modifications are made.
    image_for_display = original_image 
    cropped_qr_images = []
    decoded_texts_list = []
    decoded_json_objects_list = []

    # QReader expects images in RGB format, OpenCV reads in BGR by default
    # Use the original_image for conversion, as it's pristine.
    rgb_img = cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB)

    # Step 1: Detect QR codes to get bounding boxes.
    # qreader.detect() returns a list of bounding boxes (numpy arrays of points),
    # or None if no QR codes are found.
    detected_bboxes = qreader_detector.detect(image=rgb_img)

    if detected_bboxes:  # Handles None or an empty list
        # Determine the source for logging
        image_source_name = image_input if isinstance(image_input, str) else "the provided image array"
        print(f"Found {len(detected_bboxes)} potential QR code(s) in {image_source_name}.")

        made_modifications_to_display_image = False

        for i, detection_info in enumerate(detected_bboxes):
            current_decoded_text = None
            try:
                # Step 2: Decode the text for each detected QR code using its bounding box.
                current_decoded_text = qreader_detector.decode(image=rgb_img, detection_result=detection_info)
            except Exception as e:
                print(f"  Error decoding potential QR Code #{i+1}: {e}. Detection info: {detection_info}.")
                continue # Skip to the next detection

            if current_decoded_text is not None:
                # Successfully decoded. Now check for corners to draw and crop.
                quad_corners = detection_info.get('quad_xy')

                if quad_corners is not None:
                    # This is a confirmed QR code with location.
                    if not made_modifications_to_display_image:
                        image_for_display = original_image.copy() # Copy before first drawing
                        made_modifications_to_display_image = True
                    
                    print(f"  QR Code #{i+1} decoded: '{current_decoded_text[:50]}{'...' if len(current_decoded_text) > 50 else ''}'")
                    try:
                        current_points = np.array(quad_corners, dtype=np.float32)
                        centroid = np.mean(current_points, axis=0)
                        expanded_points = centroid + 1.1 * (current_points - centroid)

                        img_height, img_width = original_image.shape[:2]
                        expanded_points[:, 0] = np.clip(expanded_points[:, 0], 0, img_width - 1)
                        expanded_points[:, 1] = np.clip(expanded_points[:, 1], 0, img_height - 1)

                        points_for_drawing = np.array(expanded_points, dtype=np.int32).reshape((-1, 1, 2))
                        cv2.polylines(image_for_display, [points_for_drawing], isClosed=True, color=(0, 255, 0), thickness=4)

                        # --- Crop the QR region from the original_image ---
                        x_coords = expanded_points[:, 0]
                        y_coords = expanded_points[:, 1]
                        crop_x_start = int(np.min(x_coords))
                        crop_y_start = int(np.min(y_coords))
                        crop_x_end = int(np.max(x_coords)) + 1
                        crop_y_end = int(np.max(y_coords)) + 1

                        if crop_x_start < crop_x_end and crop_y_start < crop_y_end:
                            cropped_qr_img = original_image[crop_y_start:crop_y_end, crop_x_start:crop_x_end]
                            if cropped_qr_img.size > 0:
                                cropped_qr_images.append(cropped_qr_img)
                                decoded_texts_list.append(current_decoded_text) # Add text IFF crop is successful
                                json_obj = _decode_zlib_json_qr(current_decoded_text)
                                decoded_json_objects_list.append(json_obj)
                            else:
                                print(f"  QR Code #{i+1} (decoded) resulted in an empty crop slice. Not adding to results.")
                        else:
                            print(f"  QR Code #{i+1} (decoded) has invalid dimensions for cropping. Not adding to results.")
                    except (ValueError, TypeError) as e:
                        print(f"  Error processing/drawing polygon for decoded QR Code #{i+1}: {e}. Quad corners: {quad_corners}. Not adding to results.")
                else:
                    # Decoded, but no quad_corners
                    print(f"  QR Code #{i+1} was decoded ('{current_decoded_text[:50]}...') but 'quad_xy' (corners) are missing. Cannot draw or crop.")
            else:
                # current_decoded_text is None: Detected by bbox, but not a decodable QR.
                print(f"  Potential QR Code #{i+1} was detected by bounding box, but could not be decoded. No box drawn.")
    else:
        # No bounding boxes detected at all
        image_source_name = image_input if isinstance(image_input, str) else "the provided image array"
        print(f"No QR codes found in {image_source_name}.")

    # If no modifications were made, image_for_display is still the original_image.
    # Otherwise, it's a copy with drawings.
    return [image_for_display] + cropped_qr_images, decoded_texts_list, decoded_json_objects_list

if __name__ == "__main__":
    # Note: The main block is for demonstration and testing.
    # Define the input and output image paths using absolute paths
    base_dir = "/Users/claudiograsso/Documents/Semillas/code/"
    # input_image_filename = "IMG_20250521_185356657.jpg" # Example input file name
    # input_image_abs_path = os.path.join(base_dir, input_image_filename)
    
    input_image_abs_path = "/Users/claudiograsso/Documents/Semillas/code/images/IMG_20250521_184547226.jpg"

    # For demonstration: if 'qrcode.png' doesn't exist, try to generate a sample one
    if not os.path.exists(input_image_abs_path):
        try:
            import qrcode # Requires 'qrcode' library (pip install qrcode[pil])
            print(f"'{input_image_abs_path}' not found. Generating a sample QR image...")
            sample_img = qrcode.make("Test QR for Gemini Code Assist!")
            sample_img.save(input_image_abs_path)
            print(f"Sample '{input_image_abs_path}' generated.")
        except ImportError:
            print(f"Warning: '{input_image_abs_path}' not found, and 'qrcode' library is not installed to generate a sample.")
        except Exception as e:
            print(f"Error generating sample QR image '{input_image_abs_path}': {e}")

    if os.path.exists(input_image_abs_path):
        list_of_images, decoded_qr_texts, decoded_json_objects = detect_and_draw_qrcodes(input_image_abs_path)

        if list_of_images: # Check if the list of images is not None and not empty
            # Get base name (including path) and extension from the input_image_abs_path
            input_path_basename, input_ext = os.path.splitext(input_image_abs_path)

            # --- Save the main image (first in the list) ---
            main_image_to_save = list_of_images[0]
            # Construct the output path for the main image with detections
            output_detections_abs_path = f"{input_path_basename}_qr_all{input_ext}"
            cv2.imwrite(output_detections_abs_path, main_image_to_save)
            print(f"Output image with detected QR codes saved to '{output_detections_abs_path}'")

            # --- Save the cropped QR images, if any ---
            if len(list_of_images) > 1:
                for i, cropped_img in enumerate(list_of_images[1:]):
                    # Construct the output path for each cropped QR image
                    # e.g., /path/to/input_qr_1.jpg, /path/to/input_qr_2.jpg
                    cropped_qr_abs_path = f"{input_path_basename}_qr_{i + 1}{input_ext}"
                    cv2.imwrite(cropped_qr_abs_path, cropped_img)
                    print(f"Saved cropped QR image to '{cropped_qr_abs_path}'")
            
            if decoded_qr_texts:
                print("\nDecoded QR Code Texts:")
                for i, text in enumerate(decoded_qr_texts):
                    print(f"  QR #{i+1}: {text}")
                
                print("\nDecoded JSON Objects from QR Codes:")
                for i, json_obj in enumerate(decoded_json_objects):
                    if json_obj is not None:
                        print(f"  QR #{i+1} JSON: {json_obj}")
                    else:
                        print(f"  QR #{i+1} JSON: Not a valid zlib-compressed JSON or decoding failed.")
            else:
                print("\nNo QR codes were successfully decoded or yielded text.")
        else:
            print(f"Failed to process image '{input_image_abs_path}'.")

        # --- Example of passing an already loaded image ---
        print("\n--- Testing with a pre-loaded image ---")
        loaded_img_for_qr = cv2.imread(input_image_abs_path)
        if loaded_img_for_qr is not None:
            images_from_array, texts_from_array, json_from_array = detect_and_draw_qrcodes(loaded_img_for_qr)
            if images_from_array:
                input_path_basename, input_ext = os.path.splitext(input_image_abs_path)
                # Save the main image from array processing
                main_img_from_array = images_from_array[0]
                output_from_array_path = f"{input_path_basename}_qr_all_from_array{input_ext}"
                cv2.imwrite(output_from_array_path, main_img_from_array)
                print(f"Output image (from array) with detected QR codes saved to '{output_from_array_path}'")
                # Save cropped images from array processing
                if len(images_from_array) > 1:
                    for i, cropped_img_arr in enumerate(images_from_array[1:]):
                        cropped_qr_from_array_path = f"{input_path_basename}_qr_{i + 1}_from_array{input_ext}"
                        cv2.imwrite(cropped_qr_from_array_path, cropped_img_arr)
                        print(f"Saved cropped QR image (from array) to '{cropped_qr_from_array_path}'")
                if texts_from_array:
                    print("\nDecoded QR Code Texts (from array):")
                    for i, text in enumerate(texts_from_array):
                        print(f"  QR #{i+1}: {text}")
                if json_from_array:
                    print("\nDecoded JSON Objects (from array):")
                    for i, json_obj_arr in enumerate(json_from_array):
                        if json_obj_arr is not None:
                            print(f"  QR #{i+1} JSON: {json_obj_arr}")
                        else:
                            print(f"  QR #{i+1} JSON: Not a valid zlib-compressed JSON or decoding failed.")
    else:
        print(f"Input image '{input_image_abs_path}' not found. Please create it or modify the path in the script.")