import streamlit as st
import cv2
import numpy as np
import os
import glob
import logging
from PIL import Image
import pandas as pd

# Configure page
st.set_page_config(
    page_title="Image Viewer and Processor",
    page_icon="🖼️",
    layout="wide"
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

# Optional imports with error handling
try:
    from detect_and_draw_qr import detect_and_draw_qrcodes
except ImportError:
    logging.error("Failed to import detect_and_draw_qrcodes from detect_and_draw_qr. QR detection will be skipped.")
    detect_and_draw_qrcodes = None

try:
    from charuco_detector import detect_charuco_board
except ImportError:
    logging.error("Failed to import detect_charuco_board from charuco_detector")
    detect_charuco_board = None

# Initialize session state
if 'image_paths' not in st.session_state:
    st.session_state.image_paths = []
if 'current_image_index' not in st.session_state:
    st.session_state.current_image_index = -1
if 'processed_image' not in st.session_state:
    st.session_state.processed_image = None
if 'charuco_detected' not in st.session_state:
    st.session_state.charuco_detected = None
if 'qr_texts' not in st.session_state:
    st.session_state.qr_texts = []

# ChArUco parameters
CHARUCO_SQUARES_X = 5
CHARUCO_SQUARES_Y = 5
CHARUCO_SQUARE_LENGTH_MM = 10.0
CHARUCO_MARKER_LENGTH_MM = 7.0
CHARUCO_DICTIONARY_NAME = "DICT_4X4_100"

def load_images_from_directory(directory_path):
    """Load all image files from the specified directory."""
    if not os.path.isdir(directory_path):
        st.error("Invalid directory path. Please provide a valid folder path.")
        return []
    
    image_paths = []
    img_extensions = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif"]
    
    for ext in img_extensions:
        image_paths.extend(glob.glob(os.path.join(directory_path, ext)))
        # Also check uppercase extensions
        image_paths.extend(glob.glob(os.path.join(directory_path, ext.upper())))
    
    return sorted(list(set(image_paths)))

def process_image(image_path):
    """Process image for QR codes and ChArUco board detection."""
    # Reset processing results
    st.session_state.charuco_detected = False
    st.session_state.qr_texts = []
    
    # Load image
    loaded_image = cv2.imread(image_path)
    if loaded_image is None:
        st.error(f"Could not load image: {os.path.basename(image_path)}")
        return None
    
    processed_image = loaded_image.copy()
    
    # QR Code Detection
    if detect_and_draw_qrcodes:
        try:
            qr_images, qr_decoded_texts = detect_and_draw_qrcodes(loaded_image)
            if qr_images and len(qr_images) > 0 and qr_images[0] is not None:
                processed_image = qr_images[0]
                if qr_decoded_texts:
                    st.session_state.qr_texts = qr_decoded_texts
                logging.info("QR code detection successful")
        except Exception as e:
            logging.error(f"Exception during QR code detection: {e}")
            st.warning("Error during QR detection")
    
    # ChArUco Board Detection
    if detect_charuco_board:
        try:
            charuco_img_output, charuco_corners, charuco_ids, marker_corners, marker_ids = detect_charuco_board(
                processed_image,
                CHARUCO_SQUARES_X, CHARUCO_SQUARES_Y,
                CHARUCO_SQUARE_LENGTH_MM, CHARUCO_MARKER_LENGTH_MM,
                CHARUCO_DICTIONARY_NAME, display=False
            )
            if charuco_img_output is not None:
                processed_image = charuco_img_output
                if charuco_ids is not None and len(charuco_ids) > 0:
                    st.session_state.charuco_detected = True
                    logging.info("ChArUco board detection successful")
        except Exception as e:
            logging.error(f"Exception during ChArUco board detection: {e}")
            st.warning("Error during ChArUco detection")
    
    # Convert BGR to RGB for display
    processed_image_rgb = cv2.cvtColor(processed_image, cv2.COLOR_BGR2RGB)
    st.session_state.processed_image = processed_image_rgb
    
    return processed_image_rgb

def display_current_image():
    """Display the current image and its processed version."""
    if (st.session_state.current_image_index >= 0 and 
        st.session_state.current_image_index < len(st.session_state.image_paths)):
        
        current_path = st.session_state.image_paths[st.session_state.current_image_index]
        
        # Process the image
        processed_img = process_image(current_path)
        
        # Create columns for image display
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Original Image")
            try:
                original_image = Image.open(current_path)
                st.image(original_image, use_column_width=True)
            except Exception as e:
                st.error(f"Error loading original image: {e}")
        
        with col2:
            st.subheader("Processed Image")
            if processed_img is not None:
                st.image(processed_img, use_column_width=True)
            else:
                st.info("No processed image available")

# Main App Layout
st.title("🖼️ Image Viewer and Processor")
st.markdown("A Streamlit app for viewing images and detecting QR codes and ChArUco boards")

# Directory Selection Section
st.header("📁 Directory Selection")
directory_path = st.text_input(
    "Enter the folder path containing images:",
    placeholder="e.g., /path/to/your/images or C:\\path\\to\\your\\images",
    help="Enter the full path to the directory containing your images"
)

# Load Images Button
if st.button("📂 Load Images from Directory", type="primary"):
    if directory_path:
        with st.spinner("Loading images..."):
            image_paths = load_images_from_directory(directory_path)
            if image_paths:
                st.session_state.image_paths = image_paths
                st.session_state.current_image_index = 0
                st.success(f"✅ Loaded {len(image_paths)} images")
            else:
                st.warning("No image files found in the specified directory")
    else:
        st.warning("Please enter a directory path")

# Image Display and Navigation
if st.session_state.image_paths:
    st.header("🖼️ Image Viewer")
    
    # Navigation controls
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    
    with col1:
        if st.button("⬅️ Previous") and st.session_state.current_image_index > 0:
            st.session_state.current_image_index -= 1
            st.rerun()
    
    with col2:
        if st.button("➡️ Next") and st.session_state.current_image_index < len(st.session_state.image_paths) - 1:
            st.session_state.current_image_index += 1
            st.rerun()
    
    with col3:
        # Image selector
        current_idx = st.selectbox(
            "Select Image:",
            range(len(st.session_state.image_paths)),
            index=st.session_state.current_image_index,
            format_func=lambda x: f"{x+1}: {os.path.basename(st.session_state.image_paths[x])}"
        )
        if current_idx != st.session_state.current_image_index:
            st.session_state.current_image_index = current_idx
            st.rerun()
    
    with col4:
        # Current image info
        if st.session_state.current_image_index >= 0:
            current_file = os.path.basename(st.session_state.image_paths[st.session_state.current_image_index])
            st.info(f"📄 Current: {current_file} ({st.session_state.current_image_index + 1}/{len(st.session_state.image_paths)})")
    
    # Display images
    display_current_image()
    
    # Information Panel
    st.header("ℹ️ Detection Results")
    
    # Create columns for detection results
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🎯 ChArUco Board Detection")
        if st.session_state.charuco_detected is True:
            st.success("✅ ChArUco board detected!")
        elif st.session_state.charuco_detected is False:
            st.error("❌ No ChArUco board detected")
        else:
            st.info("🔍 Detection not performed")
        
        # ChArUco parameters
        with st.expander("ChArUco Parameters"):
            st.write(f"**Squares X:** {CHARUCO_SQUARES_X}")
            st.write(f"**Squares Y:** {CHARUCO_SQUARES_Y}")
            st.write(f"**Square Length:** {CHARUCO_SQUARE_LENGTH_MM}mm")
            st.write(f"**Marker Length:** {CHARUCO_MARKER_LENGTH_MM}mm")
            st.write(f"**Dictionary:** {CHARUCO_DICTIONARY_NAME}")
    
    with col2:
        st.subheader("📱 QR Code Detection")
        if st.session_state.qr_texts:
            st.success(f"✅ Found {len(st.session_state.qr_texts)} QR code(s)")
            for i, text in enumerate(st.session_state.qr_texts):
                with st.expander(f"QR Code #{i+1}"):
                    st.code(text, language=None)
        elif st.session_state.current_image_index >= 0:
            if detect_and_draw_qrcodes is None:
                st.warning("⚠️ QR detection module not available")
            else:
                st.info("❌ No QR codes found")
        else:
            st.info("🔍 Load an image to detect QR codes")

else:
    # Welcome message when no images are loaded
    st.info("👆 Please enter a directory path and click 'Load Images from Directory' to get started")
    
    # Instructions
    with st.expander("📖 How to use this app"):
        st.markdown("""
        1. **Enter directory path**: Type the full path to a folder containing images
        2. **Load images**: Click the 'Load Images from Directory' button
        3. **Navigate**: Use Previous/Next buttons or the dropdown to browse images
        4. **View results**: Check the Detection Results section for QR codes and ChArUco boards
        
        **Supported formats**: PNG, JPG, JPEG, BMP, GIF
        
        **Example paths**:
        - Windows: `C:\\Users\\YourName\\Pictures\\ImageFolder`
        - Mac/Linux: `/Users/YourName/Pictures/ImageFolder`
        """)

# Sidebar with additional information
with st.sidebar:
    st.header("📊 App Information")
    
    if st.session_state.image_paths:
        st.metric("Total Images", len(st.session_state.image_paths))
        if st.session_state.current_image_index >= 0:
            st.metric("Current Image", st.session_state.current_image_index + 1)
    
    st.subheader("🔧 Features")
    features = [
        "✅ QR Code Detection" if detect_and_draw_qrcodes else "❌ QR Code Detection",
        "✅ ChArUco Board Detection" if detect_charuco_board else "❌ ChArUco Board Detection",
        "✅ Image Navigation",
        "✅ Multiple Format Support"
    ]
    for feature in features:
        st.write(feature)
    
    st.subheader("ℹ️ Requirements")
    st.code("""
# requirements.txt
streamlit
opencv-python
pillow
numpy
pandas
    """)
