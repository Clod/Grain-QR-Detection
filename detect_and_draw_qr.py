import cv2
from qreader import QReader
import numpy as np
import os

def detect_and_draw_qrcodes(image_path, output_image_path=None):
    """
    Reads an image from disk, detects QR codes in it,
    and draws a green quadrilateral around each detected QR code.

    Args:
        image_path (str): Path to the input image file.
        output_image_path (str, optional): Path to save the output image with detections.
                                           If None, the image will be displayed instead.
    """
    # Create a QReader instance
    qreader_detector = QReader()

    # Read the image using OpenCV
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read image from '{image_path}'")
        return

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
                    # cv2.polylines expects points as int32.
                    points = np.array(quad_corners, dtype=np.int32)

                    # Reshape points for polylines: (num_points, 1, 2)
                    points = points.reshape((-1, 1, 2))

                    # Draw the green polygon (quadrilateral) around the QR code on the original BGR image
                    cv2.polylines(img, [points], isClosed=True, color=(0, 255, 0), thickness=2)
                except (ValueError, TypeError) as e: # Catch TypeError if quad_corners isn't array-like
                    print(f"  Error drawing polygon for QR Code #{i+1}: {e}. Quad corners: {quad_corners}. Skipping drawing for this QR code.")
                    continue  # Skip drawing for this problematic QR code

                if decoded_text:
                    print(f"  QR Code #{i+1} decoded text (first 50 chars): {decoded_text[:50]}{'...' if len(decoded_text) > 50 else ''}")
                else:
                    print(f"  QR Code #{i+1} detected (bounding box found), but could not be decoded.")
            else:
                print(f"  QR Code #{i+1} detected, but 'quad_xy' (corner points) are missing in detection_info: {detection_info}. Cannot draw.")

    # Save or display the image
    if output_image_path:
        cv2.imwrite(output_image_path, img)
        print(f"Output image with detected QR codes saved to '{output_image_path}'")
    else:
        cv2.imshow("QR Codes Detected", img)
        print("Press any key to close the image window.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

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
        detect_and_draw_qrcodes(input_image_abs_path, output_image_path=output_image_abs_path)
        # To display the image instead of saving it, call like this:
        # detect_and_draw_qrcodes(input_image_abs_path)
    else:
        print(f"Input image '{input_image_abs_path}' not found. Please create it or modify the path in the script.")