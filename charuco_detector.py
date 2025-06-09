"""
This script detects a ChArUco board in an image using OpenCV's aruco module.

It takes an image file as input, attempts to find the specified ChArUco board
within it, and then draws the detected ArUco markers and interpolated ChArUco
corners on the image.

The script utilizes `cv2.aruco.CharucoDetector` along with `cv2.aruco.CharucoParameters`
and `cv2.aruco.DetectorParameters` for robust detection.

The script requires the same board parameters (dimensions, square/marker lengths,
and dictionary) that were used to generate the ChArUco board.

Requirements:
- OpenCV with aruco module (cv2)
- numpy

Usage:
1. Ensure you have an image containing the ChArUco board you want to detect.
2. Modify the configuration variables in the `if __name__ == "__main__":` block
   to match the parameters of your ChArUco board and specify the path to your image.
3. Run the script: `python charuco_detector.py`
4. A window will display the image with detected markers and corners highlighted.
   Press any key to close the window.
5. Optionally, the script can save the resulting image with detections.

Note: For accurate pose estimation, camera calibration is required. This script
primarily focuses on detection and visualization.
"""

import cv2
import numpy as np

def detect_charuco_board(image_input, squares_x, squares_y, square_length_mm, marker_length_mm, dictionary_name, display=False):
    """
    Detects a ChArUco board in an image and draws the detected corners and board.

    Args:
        image_input (str or numpy.ndarray): Path to the input image or the image itself (as a NumPy array).
        squares_x (int): Number of squares in X direction of the board.
        squares_y (int): Number of squares in Y direction of the board.
        square_length_mm (float): Length of a square in millimeters.
        marker_length_mm (float): Length of a marker in millimeters.
        dictionary_name (str): Name of the Aruco dictionary used (e.g., "DICT_4X4_50").
        display (bool): Whether to display the image with detections.

    Note:
        - The function uses `cv2.aruco.CharucoDetector` for detection, which
        internally handles ArUco marker detection and ChArUco corner interpolation.
        - Physical lengths (`square_length_mm`, `marker_length_mm`) are converted
          to meters for `cv2.aruco.CharucoBoard` initialization.

    Returns:
        tuple or (None, None, None, None, None):
            - img (numpy.ndarray or None): The image with detections drawn. None if an error occurs (e.g., image not loaded).
            - charucoCorners (numpy.ndarray or None): Array of detected ChArUco corners. None if no corners are found or an error occurs.
            - charucoIds (numpy.ndarray or None): Array of IDs for the detected ChArUco corners. None if no corners are found or an error occurs.
            - markerCorners (list of numpy.ndarray or None): List of detected ArUco marker corners. None if no markers are found or an error occurs.
            - markerIds (numpy.ndarray or None): Array of IDs for the detected ArUco markers. None if no markers are found or an error occurs.
    """

    # Load the image
    if isinstance(image_input, str):
        img = cv2.imread(image_input)
        if img is None:
            print(f"Error: Could not load image from path: {image_input}")
            return None, None, None, None, None
    elif isinstance(image_input, np.ndarray):
        img = image_input.copy() # Work on a copy to avoid modifying the original array
    else:
        print("Error: Invalid image_input type. Must be a path (str) or a NumPy array.")
        return None, None, None, None, None

    # Get the ArUco dictionary
    try:
        dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary_name))
    except AttributeError:
        print(f"Error: Dictionary '{dictionary_name}' not found. Please check the dictionary name.")
        return None, None, None, None, None

    # Create the ChArUco board object (same as in generation)
    board = cv2.aruco.CharucoBoard((squares_x, squares_y), square_length_mm / 1000.0, marker_length_mm / 1000.0, dictionary)
    # board = cv2.aruco.CharucoBoard((squares_x, squares_y), 0.01, 0.007, dictionary)
    
    # Set legacy pattern for older ChArUco boards
    # board.setLegacyPattern(True)
    
    # --- NEW: Create CharucoParameters and DetectorParameters ---
    # DetectorParameters for the underlying Aruco detection
    detector_params = cv2.aruco.DetectorParameters()
    # CharucoParameters for the ChArUco interpolation/detection
    charuco_params = cv2.aruco.CharucoParameters()

    # --- NEW: Pass charuco_params and detector_params to CharucoDetector ---
    # The CharucoDetector constructor now expects (board, charucoParams, detectorParams)
    charucoDetector = cv2.aruco.CharucoDetector(board, charuco_params, detector_params)


    # Use detectBoard() to get charuco corners directly
    charucoCorners, charucoIds, markerCorners, markerIds = charucoDetector.detectBoard(img)

    if markerIds is not None:
        print(f"Detected {len(markerIds)} Aruco markers.")

        if charucoIds is not None:
            print(f"Detected {len(charucoIds)} ChArUco corners.")

            # Draw the detected ChArUco corners
            cv2.aruco.drawDetectedCornersCharuco(img, charucoCorners, charucoIds, cornerColor=(0, 255, 0))

            # Draw the individual ArUco markers (optional, as charuco detection is more robust)
            cv2.aruco.drawDetectedMarkers(img, markerCorners, markerIds,  borderColor=(0, 0, 255))

            # --- Pose Estimation (Optional, requires camera calibration) ---
            # If you have camera calibration parameters (camera_matrix, dist_coeffs),
            # you can estimate the pose of the board.
            # For example:
            # ret, rvec, tvec = cv2.aruco.estimatePoseCharucoBoard(
            #     charucoCorners, charucoIds, board, camera_matrix, dist_coeffs, None, None
            # )
            # if ret:
            #     print("Board pose estimated.")
            #     cv2.drawFrameAxes(img, camera_matrix, dist_coeffs, rvec, tvec, 0.05) # Draw axes on the board

        else:
            print("No ChArUco corners detected from the Aruco markers.")
    else:
        print("No Aruco markers detected in the image.")

    # Display the result
    if display:
        cv2.imshow("ChArUco Board Detection", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    
    return img, charucoCorners, charucoIds, markerCorners, markerIds

if __name__ == "__main__":
    # --- Configuration for your specific board (MUST MATCH GENERATION SCRIPT) ---
    squares_x = 5
    squares_y = 5
    board_width_cm = 5.0 # This is used to calculate square_length_mm
    marker_length_mm = 7.0
    dictionary_name = "DICT_4X4_100" # Ensure this matches the dictionary used for generation

    # Calculate square length based on desired board width
    square_length_mm = (board_width_cm * 10.0) / squares_x

    # --- Specify the path to your image ---
    # Make sure you have an image of the ChArUco board in the same directory,
    # or provide the full path to the image.
    image_to_detect = "test_images/charuco_5x5_12markers_5cm.png"
    #image_to_detect = "test_images/IMG_20250521_184547226.jpg" 
    #image_to_detect = "test_images/IMG_20250521_185417301.jpg"

    result = detect_charuco_board(
        image_input=image_to_detect,
        squares_x=squares_x,
        squares_y=squares_y,
        square_length_mm=square_length_mm,
        marker_length_mm=marker_length_mm,
        dictionary_name=dictionary_name,
        display=True
    )
    
    # img is the first element of the tuple returned by detect_charuco_board
    processed_image = result[0] 
    if processed_image is not None:
        # If you want to save the result image, uncomment the following line:
        cv2.imwrite("detected_charuco_board.png", processed_image)
        print("Saved detected_charuco_board.png")

        # Example of passing an already loaded image
        # loaded_img = cv2.imread(image_to_detect)
        # if loaded_img is not None:
        #     print("\nDetecting on a pre-loaded image:")
        #     img_from_array_tuple = detect_charuco_board(
        #         loaded_img, squares_x, squares_y, square_length_mm, marker_length_mm, dictionary_name, display=False
        #     )
        #     if img_from_array_tuple[0] is not None:
        #         cv2.imwrite("detected_charuco_from_array.png", img_from_array_tuple[0])
        #         print("Saved detected_charuco_from_array.png")