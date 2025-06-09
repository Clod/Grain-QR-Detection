from flask import Flask, request, render_template, jsonify, send_file, session, redirect, url_for
import os
import cv2
import numpy as np
import base64
import json
from werkzeug.utils import secure_filename
import logging
from PIL import Image
import io
import glob

# Optional imports with error handling
try:
    from detect_and_draw_qr import detect_and_draw_qrcodes
except ImportError:
    logging.error("Failed to import detect_and_draw_qrcodes from detect_and_draw_qr. QR detection will be skipped.")
    detect_and_draw_qrcodes = None

try:
    from charuco_detector import detect_charuco_board
except ImportError:
    logging.error("Failed to import detect_charuco_board")
    detect_charuco_board = None

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a-default-fallback-secret-key-if-not-set') # It's better to use environment variables for secret keys

# Configure Flask's built-in logger
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    # Clear existing handlers to prevent duplicate logging in debug mode
    app.logger.handlers.clear()
    app.logger.propagate = False # Optional: prevent messages from propagating to the root logger
    app.logger.setLevel(logging.INFO) # Set desired logging level
    handler = logging.StreamHandler() # Log to stderr
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'))
    app.logger.addHandler(handler)

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ChArUco configuration
CHARUCO_CONFIG = {
    'SQUARES_X': 5,
    'SQUARES_Y': 5,
    'SQUARE_LENGTH_MM': 10.0,
    'MARKER_LENGTH_MM': 7.0,
    'DICTIONARY_NAME': "DICT_4X4_100"
}

@app.errorhandler(413)
def request_entity_too_large(error):
    """Custom handler for 413 Request Entity Too Large errors."""
    content_length = request.headers.get('Content-Length', 'N/A')
    max_length = app.config.get('MAX_CONTENT_LENGTH', 'N/A')
    app.logger.error(
        f"Request entity too large (413) from {request.remote_addr}. "
        f"Content-Length: {content_length}, Limit: {max_length} bytes. "
        f"Error details: {error}"
    )
    return jsonify({
        'error': 'Payload too large',
        'message': f"The uploaded data exceeds the maximum allowed size of {max_length} bytes."
    }), 413

def cv_image_to_base64(cv_image):
    """Convert OpenCV image to base64 string for web display."""
    app.logger.info("Attempting to convert OpenCV image to base64.")
    if cv_image is None:
        app.logger.warning("Input OpenCV image is None, returning None.")
        return None
    
    # Convert BGR to RGB
    app.logger.debug("Converting BGR to RGB.")
    rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_image)
    app.logger.debug("Converted to PIL image.")
    
    # Convert to base64
    buffer = io.BytesIO()
    pil_image.save(buffer, format='JPEG', quality=85)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    app.logger.info("Successfully converted OpenCV image to base64 JPEG.")
    return f"data:image/jpeg;base64,{image_base64}"

def process_image(image_path):
    """Process image for QR codes and ChArUco detection."""
    app.logger.info(f"Starting image processing for: {image_path}")
    result = {
        'original_image': None,
        'processed_image': None,
        'charuco_detected': False,
        'qr_codes': []
    }
    
    # Load image
    app.logger.info(f"Loading image from path: {image_path}")
    cv_image = cv2.imread(image_path)
    if cv_image is None:
        app.logger.error(f"Failed to load image from path: {image_path}")
        return result
    
    app.logger.info(f"Successfully loaded image: {image_path}")
    # Convert original image to base64
    result['original_image'] = cv_image_to_base64(cv_image)
    
    # Start with copy for processing
    processed_image = cv_image.copy()
    app.logger.debug("Created a copy of the image for processing.")
    
    # QR Code detection
    if detect_and_draw_qrcodes:
        app.logger.info("Attempting QR code detection.")
        try:
            qr_images, qr_decoded_texts, qr_decoded_json_objects = detect_and_draw_qrcodes(cv_image)
            if qr_images and len(qr_images) > 0 and qr_images[0] is not None:
                processed_image = qr_images[0]
                app.logger.info(f"QR code detection successful. Found {len(qr_decoded_texts)} QR codes.")
                if qr_decoded_texts:
                    result['qr_codes'] = qr_decoded_texts
                    result['qr_codes_json'] = qr_decoded_json_objects
            else:
                app.logger.info("QR code detection ran, but no QR codes found or image not returned.")
        except Exception as e:
            app.logger.error(f"Exception during QR code detection for {image_path}: {e}", exc_info=True)
    else:
        app.logger.warning("detect_and_draw_qrcodes module not available. Skipping QR detection.")

    # ChArUco detection
    if detect_charuco_board:
        try:
            charuco_output, charuco_corners, charuco_ids, marker_corners, marker_ids = detect_charuco_board(
                processed_image,
                CHARUCO_CONFIG['SQUARES_X'], CHARUCO_CONFIG['SQUARES_Y'],
                CHARUCO_CONFIG['SQUARE_LENGTH_MM'], CHARUCO_CONFIG['MARKER_LENGTH_MM'],
                CHARUCO_CONFIG['DICTIONARY_NAME'], display=False
            )
            if charuco_output is not None:
                processed_image = charuco_output
                if charuco_ids is not None and len(charuco_ids) > 0:
                    app.logger.info(f"ChArUco board detection successful. Found {len(charuco_ids)} ChArUco IDs.")
                    result['charuco_detected'] = True
                else:
                    app.logger.info("ChArUco board detection ran, image updated, but no ChArUco IDs found.")
            else:
                app.logger.info("ChArUco board detection ran but returned None.")
        except Exception as e:
            app.logger.error(f"Exception during ChArUco board detection for {image_path}: {e}", exc_info=True)
    else:
        app.logger.warning("detect_charuco_board module not available. Skipping ChArUco detection.")

    result['processed_image'] = cv_image_to_base64(processed_image)
    app.logger.info(f"Finished image processing for: {image_path}. Charuco detected: {result['charuco_detected']}, QR codes: {len(result['qr_codes'])}")
    return result

@app.route('/')
def index():
    """Main page."""
    app.logger.info("Main page '/' accessed.")
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle multiple file uploads."""
    app.logger.info(f"Received file upload request from {request.remote_addr}")
    app.logger.info(f"Request Headers: {request.headers}")
    app.logger.info(f"Request Form data: {request.form}")
    app.logger.info(f"Request Files: {request.files}")
    if request.data:
        app.logger.info(f"Request Raw Data: {request.data[:200]}...") # Log first 200 bytes if raw data exists

    if 'files[]' not in request.files:
        app.logger.warning("Upload request received, but 'files[]' not in request.files.")
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files[]')
    image_paths = []
    
    for file in files:
        if file and file.filename:
            app.logger.info(f"File details - Name: {file.name}, Filename: {file.filename}, ContentType: {file.content_type}, ContentLength: {file.content_length}")
            filename = secure_filename(file.filename)
            app.logger.info(f"Processing uploaded file: {filename}")
            # Log more details about the file object if needed, e.g., file.headers
            # app.logger.info(f"File headers for {filename}: {file.headers}")
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                try:
                    file.save(filepath)
                    image_paths.append(filename)
                    app.logger.info(f"Saved uploaded file to: {filepath}")
                except Exception as e:
                    app.logger.error(f"Error saving uploaded file {filename} to {filepath}: {e}", exc_info=True)
            else:
                app.logger.warning(f"Skipped file {filename} due to unsupported extension.")
        else:
            app.logger.warning("Encountered a file object without a filename in upload.")
    
    # Store in session
    session['image_paths'] = image_paths
    session['current_index'] = 0 if image_paths else -1
    app.logger.info(f"Stored {len(image_paths)} image paths in session. Current index: {session['current_index']}.")
    return jsonify({
        'success': True,
        'image_count': len(image_paths),
        'images': image_paths
    })

@app.route('/process/<int:index>')
def process_image_route(index):
    """Process image at given index."""
    app.logger.info(f"Processing image request for index: {index}.")
    image_paths = session.get('image_paths', [])
    
    if not (0 <= index < len(image_paths)):
        app.logger.warning(f"Invalid image index {index} requested. Total images: {len(image_paths)}.")
        return jsonify({'error': 'Invalid image index'}), 400
    
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_paths[index])
    result = process_image(image_path)
    
    # Add navigation info
    result.update({
        'current_index': index,
        'total_images': len(image_paths),
        'filename': image_paths[index],
        'has_next': index < len(image_paths) - 1,
        'has_prev': index > 0
    })
    
    session['current_index'] = index
    app.logger.info(f"Successfully processed image at index {index}: {image_paths[index]}. Returning JSON response.")
    return jsonify(result)

@app.route('/navigate/<direction>')
def navigate(direction):
    """Navigate to next/previous image."""
    app.logger.info(f"Navigation request received: {direction}.")
    current_index = session.get('current_index', 0)
    image_paths = session.get('image_paths', [])
    app.logger.debug(f"Current index from session: {current_index}, Total images: {len(image_paths)}.")
    
    if direction == 'next' and current_index < len(image_paths) - 1:
        new_index = current_index + 1
        app.logger.info(f"Navigating to next image. New index: {new_index}.")
    elif direction == 'prev' and current_index > 0:
        new_index = current_index - 1
        app.logger.info(f"Navigating to previous image. New index: {new_index}.")
    else:
        app.logger.warning(f"Invalid navigation request: {direction}. Current index: {current_index}, Total images: {len(image_paths)}.")
        return jsonify({'error': 'Invalid navigation'}), 400
    
    return redirect(url_for('process_image_route', index=new_index))

if __name__ == '__main__':
    # Flask's logger is configured above. This basicConfig would be for other modules if needed.
    app.logger.info("Starting Flask application...")
    app.run(debug=True, host='0.0.0.0', port=8000)
