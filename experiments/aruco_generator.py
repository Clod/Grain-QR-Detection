import cv2
import numpy as np

def generate_aruco_patterns_image(dictionary_name, num_patterns, marker_size=100, border_bits=1):
    """
    Generates an image containing a grid of ArUco patterns.

    Args:
        dictionary_name: The name of the ArUco dictionary (e.g., cv2.aruco.DICT_4X4_50).
        num_patterns: The number of ArUco patterns to generate (e.g., 16 for the first 16).
        marker_size: The size of each individual ArUco marker in pixels.
        border_bits: The size of the marker's border in bits (usually 1 or 2).
    """

    aruco_dict = cv2.aruco.getPredefinedDictionary(dictionary_name)

    # Find the string name of the dictionary for more descriptive output
    dict_str_name = "Unknown_DICT"
    for name, value in cv2.aruco.__dict__.items():
        if name.startswith("DICT_") and value == dictionary_name:
            dict_str_name = name
            break

    # Calculate grid dimensions (e.g., 4x4 for 16 patterns)
    grid_rows = int(np.ceil(np.sqrt(num_patterns)))
    grid_cols = int(np.ceil(num_patterns / grid_rows))

    # Calculate total image size
    image_width = grid_cols * (marker_size + 10)  # Add some padding between markers
    image_height = grid_rows * (marker_size + 10)
    
    # Create a blank white image
    output_image = np.ones((image_height, image_width), dtype=np.uint8) * 255

    print(f"Generating {num_patterns} ArUco patterns from {dict_str_name}...")

    for i in range(num_patterns):
        marker_image = cv2.aruco.generateImageMarker(aruco_dict, i, marker_size, borderBits=border_bits)

        row = i // grid_cols
        col = i % grid_cols

        y_offset = row * (marker_size + 10)
        x_offset = col * (marker_size + 10)

        output_image[y_offset : y_offset + marker_size, x_offset : x_offset + marker_size] = marker_image

    output_filename = f"{dict_str_name}_first_{num_patterns}_patterns.png"
    cv2.imwrite(output_filename, output_image)
    print(f"Image saved as {output_filename}")

if __name__ == "__main__":
    generate_aruco_patterns_image(cv2.aruco.DICT_4X4_50, 16)
    generate_aruco_patterns_image(cv2.aruco.DICT_4X4_100, 16)
    generate_aruco_patterns_image(cv2.aruco.DICT_4X4_250, 16)