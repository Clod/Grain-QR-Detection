import cv2
from qreader import QReader
import numpy as np
import os

def detect_and_draw_qrcodes(image_input):
    """
    Reads an image from disk, detects QR codes in it,
    draws a green quadrilateral around each detected QR code.

    Args:
        image_input (str or numpy.ndarray): Path to the input image file or the image itself (as a NumPy array).
    Returns:
        list[numpy.ndarray] or None: A list of images.
            - The first image is the input image with QR codes highlighted by
              green quadrilaterals. If no QR codes are found, it's the
              original unmodified image.
            - Subsequent images in the list are the cropped individual QR code
              regions, if any were detected and successfully cropped.
            Returns None if the image cannot be read or if input type is invalid.
    """
    # Create a QReader instance
    qreader_detector = QReader()

    if isinstance(image_input, str):
        # Input is a path, load the image
        original_image = cv2.imread(image_input)
        if original_image is None:
            print(f"Error: Could not read image from path: '{image_input}'")
            return None
    elif isinstance(image_input, np.ndarray):
        original_image = image_input.copy() # Work on a copy
    else:
        print(f"Error: Invalid input type. Expected string path or NumPy array, got {type(image_input)}.")
        return None

    # This will be the image we draw on, and the first image returned.
    # If no QRs are found, it remains the original_image. If QRs are found, it becomes a copy.
    image_for_display = original_image
    cropped_qr_images = []

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
        print(f"Found {len(detected_bboxes)} QR code(s) in {image_source_name}.")


        # Create a copy to draw on, so original_image remains clean for cropping
        image_for_display = original_image.copy()

        for i, detection_info in enumerate(detected_bboxes):
            # detection_info is a dictionary from qreader.detect(),
            # containing keys like 'bbox_xyxy', 'confidence', 'quad_xy'.
            # 'quad_xy' holds the four corner points of the QR code.
            decoded_text = None
            try:
                # Step 2: Decode the text for each detected QR code using its bounding box.
                # qreader.decode() returns the decoded string or None.
                # It can accept the entire detection_info dictionary.
                decoded_text = qreader_detector.decode(image=rgb_img, detection_result=detection_info)
            except Exception as e:
                print(f"  Error decoding QR Code #{i+1} with detection_info: {detection_info}. Error: {e}")

            # Get the corner points for drawing
            quad_corners = detection_info.get('quad_xy')

            if quad_corners is not None:
                try:
                    # quad_corners should be a NumPy array of shape (4, 2) or similar list/tuple.
                    # Convert to float for calculations if not already
                    current_points = np.array(quad_corners, dtype=np.float32)

                    # Calculate the centroid of the quadrilateral
                    centroid = np.mean(current_points, axis=0)

                    # Expand each point by 10% outwards from the centroid
                    # New_Point = Centroid + 1.1 * (Old_Point - Centroid)
                    expanded_points = centroid + 1.1 * (current_points - centroid)

                    # Ensure the expanded points are within the image boundaries
                    img_height, img_width = original_image.shape[:2]
                    expanded_points[:, 0] = np.clip(expanded_points[:, 0], 0, img_width - 1) # x-coordinates
                    expanded_points[:, 1] = np.clip(expanded_points[:, 1], 0, img_height - 1) # y-coordinates

                    # cv2.polylines expects points as int32.
                    points_for_drawing = np.array(expanded_points, dtype=np.int32)

                    # Reshape points for polylines: (num_points, 1, 2)
                    points_for_drawing = points_for_drawing.reshape((-1, 1, 2))

                    # Draw the green polygon on the image_for_display
                    cv2.polylines(image_for_display, [points_for_drawing], isClosed=True, color=(0, 255, 0), thickness=4)

                    # --- Crop the QR region from the original_image ---
                    # Use the bounding box of the expanded_points for cropping
                    x_coords = expanded_points[:, 0]
                    y_coords = expanded_points[:, 1]

                    # Determine the min/max coordinates for the crop area
                    crop_x_start = int(np.min(x_coords))
                    crop_y_start = int(np.min(y_coords))
                    # For slicing, the end point is exclusive. To include the max coordinate, add 1.
                    crop_x_end = int(np.max(x_coords)) + 1
                    crop_y_end = int(np.max(y_coords)) + 1

                    # Ensure crop coordinates define a valid, non-empty region
                    if crop_x_start < crop_x_end and crop_y_start < crop_y_end:
                        # Crop from the pristine original_image
                        cropped_qr_img = original_image[crop_y_start:crop_y_end, crop_x_start:crop_x_end]
                        if cropped_qr_img.size > 0: # Check if the slice is not empty
                            cropped_qr_images.append(cropped_qr_img)
                        else:
                            print(f"  QR Code #{i+1} resulted in an empty crop slice. Skipping.")
                    else:
                        print(f"  QR Code #{i+1} has invalid dimensions for cropping. Skipping crop.")

                except (ValueError, TypeError) as e: # Catch TypeError if quad_corners isn't array-like
                    print(f"  Error drawing polygon for QR Code #{i+1}: {e}. Quad corners: {quad_corners}. Skipping drawing for this QR code.")
                    continue  # Skip drawing for this problematic QR code

                if decoded_text:
                    print(f"  QR Code #{i+1} decoded text (first 50 chars): {decoded_text[:50]}{'...' if len(decoded_text) > 50 else ''}")
                else:
                    print(f"  QR Code #{i+1} detected (bounding box found), but could not be decoded.")
            else:
                print(f"  QR Code #{i+1} detected, but 'quad_xy' (corner points) are missing in detection_info: {detection_info}. Cannot draw.")
    else:
        print(f"No QR codes found in '{image_path}'.")
        image_source_name = image_input if isinstance(image_input, str) else "the provided image array"
        print(f"No QR codes found in {image_source_name}.")

    return [image_for_display] + cropped_qr_images

if __name__ == "__main__":
    # Define the input and output image paths using absolute paths
    base_dir = "/Users/claudiograsso/Documents/Semillas/code/"
    input_image_filename = "IMG_20250521_185356657.jpg" # Example input file name

    input_image_abs_path = os.path.join(base_dir, input_image_filename)

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
        list_of_images = detect_and_draw_qrcodes(input_image_abs_path)

        if list_of_images: # Check if the list is not None and not empty
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
        else:
            print(f"Failed to process image '{input_image_abs_path}'.")

        # --- Example of passing an already loaded image ---
        print("\n--- Testing with a pre-loaded image ---")
        loaded_img_for_qr = cv2.imread(input_image_abs_path)
        if loaded_img_for_qr is not None:
            list_from_array = detect_and_draw_qrcodes(loaded_img_for_qr)
            if list_from_array:
                input_path_basename, input_ext = os.path.splitext(input_image_abs_path)
                # Save the main image from array processing
                main_img_from_array = list_from_array[0]
                output_from_array_path = f"{input_path_basename}_qr_all_from_array{input_ext}"
                cv2.imwrite(output_from_array_path, main_img_from_array)
                print(f"Output image (from array) with detected QR codes saved to '{output_from_array_path}'")
                # Save cropped images from array processing
                if len(list_from_array) > 1:
                    for i, cropped_img_arr in enumerate(list_from_array[1:]):
                        cropped_qr_from_array_path = f"{input_path_basename}_qr_{i + 1}_from_array{input_ext}"
                        cv2.imwrite(cropped_qr_from_array_path, cropped_img_arr)
                        print(f"Saved cropped QR image (from array) to '{cropped_qr_from_array_path}'")
    else:
        print(f"Input image '{input_image_abs_path}' not found. Please create it or modify the path in the script.")