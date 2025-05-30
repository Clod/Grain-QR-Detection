import cv2
from qreader import QReader
import numpy as np
import os

def detect_and_draw_qrcodes(image_path):
    """
    Reads an image from disk, detects QR codes in it,
    draws a green quadrilateral around each detected QR code.

    Args:
        image_path (str): Path to the input image file.
    Returns:
        list[numpy.ndarray] or None:
            A list containing one image:
            - The image with QR codes highlighted by green quadrilaterals.
            - If no QR codes are found, it's the original image.
            Returns None if the image cannot be read.
    """
    # Create a QReader instance
    qreader_detector = QReader()

    # Read the image using OpenCV
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read image from '{image_path}'")
        return None

    # QReader expects images in RGB format, OpenCV reads in BGR by default
    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Step 1: Detect QR codes to get bounding boxes.
    # qreader.detect() returns a list of bounding boxes (numpy arrays of points),
    # or None if no QR codes are found.
    detected_bboxes = qreader_detector.detect(image=rgb_img)

    if not detected_bboxes:  # Handles None or an empty list
        print(f"No QR codes found in '{image_path}'.")
    else:
        print(f"Found {len(detected_bboxes)} QR code(s) in '{image_path}'.")

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
                    img_height, img_width = img.shape[:2]
                    expanded_points[:, 0] = np.clip(expanded_points[:, 0], 0, img_width - 1) # x-coordinates
                    expanded_points[:, 1] = np.clip(expanded_points[:, 1], 0, img_height - 1) # y-coordinates

                    # cv2.polylines expects points as int32.
                    points_for_drawing = np.array(expanded_points, dtype=np.int32)

                    # Reshape points for polylines: (num_points, 1, 2)
                    points_for_drawing = points_for_drawing.reshape((-1, 1, 2))

                    # Draw the green polygon (quadrilateral) around the QR code on the original BGR image
                    cv2.polylines(img, [points_for_drawing], isClosed=True, color=(0, 255, 0), thickness=2)

                except (ValueError, TypeError) as e: # Catch TypeError if quad_corners isn't array-like
                    print(f"  Error drawing polygon for QR Code #{i+1}: {e}. Quad corners: {quad_corners}. Skipping drawing for this QR code.")
                    continue  # Skip drawing for this problematic QR code

                if decoded_text:
                    print(f"  QR Code #{i+1} decoded text (first 50 chars): {decoded_text[:50]}{'...' if len(decoded_text) > 50 else ''}")
                else:
                    print(f"  QR Code #{i+1} detected (bounding box found), but could not be decoded.")
            else:
                print(f"  QR Code #{i+1} detected, but 'quad_xy' (corner points) are missing in detection_info: {detection_info}. Cannot draw.")

    return [img] # Return a list containing the processed image

if __name__ == "__main__":
    # Define the input and output image paths using absolute paths
    base_dir = "/Users/claudiograsso/Documents/Semillas/code/"
    input_image_filename = "IMG_20250521_185356657.jpg" # Example input file name
    output_image_filename = "qrcode_detected.jpg" # Example output file name

    input_image_abs_path = os.path.join(base_dir, input_image_filename)
    output_image_abs_path = os.path.join(base_dir, output_image_filename)

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
        if list_of_images is not None:
            # The first item is the image with green boxes (or original if no QR found)
            image_to_save = list_of_images[0]
            cv2.imwrite(output_image_abs_path, image_to_save)
            print(f"Output image with detected QR codes saved to '{output_image_abs_path}'")
        else:
            print(f"Failed to process image '{input_image_abs_path}'.")
    else:
        print(f"Input image '{input_image_abs_path}' not found. Please create it or modify the path in the script.")