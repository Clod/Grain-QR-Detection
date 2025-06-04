import cv2
import cv2.aruco as aruco
import numpy as np

# Note: OpenCV versions 4.7+ changed the AruCo API to use ArucoDetector object.
def detect_charuco_pattern(image_path,
                           squaresX,
                           squaresY,
                           squareLength,
                           markerLength,
                           aruco_dict_type=aruco.DICT_4X4_50):
    """
    Detects a ChArUco pattern in an image.

    Args:
        image_path (str): Path to the input image.
        squaresX (int): Number of squares in X direction.
        squaresY (int): Number of squares in Y direction.
        squareLength (float): Side length of each square in meters/units.
        markerLength (float): Side length of each AruCo marker in meters/units.
        aruco_dict_type (int): Type of AruCo dictionary used for the markers.

    Returns:
        tuple: (detected_corners, detected_ids, image_with_drawing)
               detected_corners: Array of detected ChArUco corners.
               detected_ids: Array of IDs corresponding to the corners.
               image_with_drawing: The image with detected pattern drawn.
    """

    # Load the AruCo dictionary
    dictionary = aruco.getPredefinedDictionary(aruco_dict_type)

    # Create the ChArUco board object
    # For newer OpenCV versions (e.g., 4.7+), CharucoBoard_create is deprecated/removed.
    # Use the CharucoBoard constructor directly.
    # The first argument 'size' should be a tuple (squaresX, squaresY).
    board = aruco.CharucoBoard((squaresX, squaresY), squareLength, markerLength, dictionary)

    # Read the image
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read image from {image_path}")
        return None, None, None

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    detected_corners = None
    detected_ids = None
    image_with_drawing = img.copy() # Create a copy to draw on

    # Create CharucoDetector.
    # We can pass aruco.DetectorParameters() to its constructor if specific Aruco detection
    # parameters are needed, similar to how ArucoDetector was used.
    # Using default detector parameters here.
    # detector_params = aruco.DetectorParameters()
    # charuco_detector = aruco.CharucoDetector(board, detectorParameters=detector_params)
    charuco_detector = aruco.CharucoDetector(board)

    # Use the detectBoard method that handles both Aruco marker detection and Charuco interpolation.
    # This method returns: charuco_corners, charuco_ids, marker_corners, marker_ids
    # (assuming no camera matrix is provided for pose estimation)
    charucoCorners, charucoIds, markerCorners, markerIds = charuco_detector.detectBoard(gray)

    if charucoCorners is not None and len(charucoCorners) > 0:
        detected_corners = charucoCorners
        detected_ids = charucoIds
        # Draw the detected ChArUco board (drawing functions are often static)
        aruco.drawDetectedCornersCharuco(image_with_drawing, charucoCorners, charucoIds)
        print(f"Detected {len(charucoCorners)} ChArUco corners.")
    elif markerCorners is not None and len(markerCorners) > 0:
        # No ChArUco corners interpolated, but AruCo markers were detected by CharucoDetector
        print("No ChArUco corners interpolated, but AruCo markers were detected.")
        # Optionally draw detected AruCo markers
        aruco.drawDetectedMarkers(image_with_drawing, markerCorners, markerIds)
    else:
        print("No AruCo markers or ChArUco pattern detected by CharucoDetector.")

    return detected_corners, detected_ids, image_with_drawing

if __name__ == "__main__":
    # Define the parameters for the ChArUco board
    BOARD_SQUARES_X = 6 # Number of squares in X direction
    BOARD_SQUARES_Y = 6 # Number of squares in Y direction
    # These lengths are in *any consistent unit* (e.g., meters, millimeters, inches).
    # They are crucial for accurate pose estimation later.
    SQUARE_LENGTH = 10   
    MARKER_LENGTH = 7  
    ARUCO_DICTIONARY_TYPE = aruco.DICT_4X4_50    

    # Path to your image
    #image_file = "/Users/claudiograsso/Documents/Semillas/code/copy_of_images/IMG_20250521_184547226.jpg" # Replace with your actual image file
    image_file = "/Users/claudiograsso/Documents/Semillas/code/aruco.png" # Example image file

    corners, ids, image_with_drawing = detect_charuco_pattern(
        image_file,
        BOARD_SQUARES_X,
        BOARD_SQUARES_Y,
        SQUARE_LENGTH,
        MARKER_LENGTH,
        ARUCO_DICTIONARY_TYPE
    )

    if image_with_drawing is not None:
        cv2.imshow("Detected ChArUco Pattern", image_with_drawing)
        cv2.waitKey(0)
        cv2.destroyAllWindows()