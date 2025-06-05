"""
This script generates a ChArUco board image using OpenCV's aruco module.

A ChArUco board is a planar board where the markers are placed inside the white
squares of a chessboard. This combination allows for more robust detection
and pose estimation compared to using only ArUco markers or a standard chessboard.

The script allows customization of the board dimensions, marker size,
ArUco dictionary, output filename, and resolution (DPI).

Requirements:
- OpenCV with aruco module (cv2)
- numpy

Usage:
1. Modify the configuration variables in the `if __name__ == "__main__":` block
   to define the desired board properties.
2. Run the script: `python charuco_generator.py`
3. An image file of the generated ChArUco board will be saved to the specified
   `output_filename`.

The generated board can then be printed and used for camera calibration
or pose estimation with the corresponding detection script.
"""

import cv2
import numpy as np

def generate_charuco_board(squares_x, squares_y, square_length_mm, marker_length_mm, dictionary_name, output_filename="charuco_board.png", dpi=600):
    """
    Generates and saves a ChArUco board image.

    Args:
        squares_x (int): Number of squares in X direction.
        squares_y (int): Number of squares in Y direction.
        square_length_mm (float): Length of a square in millimeters.
        marker_length_mm (float): Length of a marker in millimeters.
        dictionary_name (str): Name of the Aruco dictionary to use (e.g., "DICT_4X4_50", "DICT_5X5_100").
        output_filename (str): Name of the output image file.
        dpi (int): Dots per inch for the output image resolution.
    """

    # Get the ArUco dictionary
    try:
        dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary_name))
    except AttributeError:
        print(f"Error: Dictionary '{dictionary_name}' not found. Please check the dictionary name.")
        return

    # Create the ChArUco board object
    # The arguments are:
    # squaresX, squaresY: The number of squares in the X and Y directions.
    # squareLength: The side length of each square in the board (e.g., in meters or pixels).
    # markerLength: The side length of each marker in the board (e.g., in meters or pixels).
    # dictionary: The dictionary of markers.
    # board = cv2.aruco.CharucoBoard((squares_x, squares_y), square_length_mm / 1000.0, marker_length_mm / 1000.0, dictionary)
    board = cv2.aruco.CharucoBoard((squares_x, squares_y), 0.01, 0.007, dictionary)

    # Calculate image size based on desired DPI and physical dimensions
    board_width_mm = squares_x * square_length_mm
    board_height_mm = squares_y * square_length_mm

    # Add a small border for better visualization/detection
    border_mm = square_length_mm * 0.5
    image_width_mm = board_width_mm + 2 * border_mm
    image_height_mm = board_height_mm + 2 * border_mm

    # Convert mm to inches
    image_width_inches = image_width_mm / 25.4
    image_height_inches = image_height_mm / 25.4

    # Calculate pixel dimensions
    pixel_width = int(image_width_inches * dpi)
    pixel_height = int(image_height_inches * dpi)

    # Generate the board image
    # The arguments are:
    # board: The ChArUco board object.
    # outSize: Size of the output image in pixels.
    # marginSize: Size of the margin in pixels.
    # borderBits: Number of bits in the marker border.
    img = board.generateImage((pixel_width, pixel_height), marginSize=int(border_mm / 25.4 * dpi), borderBits=1)

    # Save the image
    cv2.imwrite(output_filename, img)
    print(f"ChArUco board generated and saved as '{output_filename}' with resolution {pixel_width}x{pixel_height} pixels at {dpi} DPI.")
    print(f"Physical dimensions: {board_width_mm / 10.0:.1f} cm x {board_height_mm / 10.0:.1f} cm")

if __name__ == "__main__":
    # --- Configuration for your specific board ---
    squares_x = 5
    squares_y = 5
    board_width_cm = 5.0
    marker_length_mm = 7.0
    dictionary_name = "DICT_4X4_100" # Using a 4x4 dictionary, sufficient for 12 markers

    # Calculate square length based on desired board width
    square_length_mm = (board_width_cm * 10.0) / squares_x

    generate_charuco_board(
        squares_x=squares_x,
        squares_y=squares_y,
        square_length_mm=square_length_mm,
        marker_length_mm=marker_length_mm,
        dictionary_name=dictionary_name,
        output_filename="charuco_5x5_12markers_5cm.png",
        dpi=600 # High DPI for printing
    )