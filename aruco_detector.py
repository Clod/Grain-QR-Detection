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
    # --- Configuration for your specific ChArUco board ---
    # You MUST adjust these values to match the board you are using.
    # The 'pattern.jpg' shows a 5x5 board (including the black squares outside the markers)
    # with 4x4 internal chessboard squares, where each square contains an AruCo marker.
    # Assuming 'pattern.jpg' shows a 5x5 grid of squares (4 internal AruCo markers across x and y)
    # Let's assume squareLength = 0.02 (2 cm) and markerLength = 0.015 (1.5 cm)
    # The Aruco dictionary in 'pattern.jpg' seems to be DICT_4X4_50.
    
    # If the board has 5x5 *total* squares including the outermost empty ones,
    # then it has 4x4 *internal* chessboard squares where Aruco markers are.
    # So, squaresX and squaresY would be 4.
    
    # It's crucial to know the exact dimensions of your printed board.
    # For example, if it's a 5x7 chessboard with markers, then squaresX=5, squaresY=7.
    # Let's *assume* the pattern.jpg is a 5x5 grid of squares with AruCo markers in each.
    # This implies 4 internal squares in x and 4 internal squares in y that can contain markers.
    
    # Based on pattern.jpg, it looks like a 5x5 grid of squares (5 across, 5 down).
    # If each square contains an Aruco marker, then:
    BOARD_SQUARES_X = 6 # Number of squares in X direction
    BOARD_SQUARES_Y = 6 # Number of squares in Y direction
    # These lengths are in *any consistent unit* (e.g., meters, millimeters, inches).
    # They are crucial for accurate pose estimation later.
    SQUARE_LENGTH = 0.01  # Example: 3 cm per square
    MARKER_LENGTH = 0.007 # Example: 2.5 cm for the AruCo marker inside the square
    ARUCO_DICTIONARY_TYPE = aruco.DICT_4X4_50 # Adjust if your markers are from a different dictionary    

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