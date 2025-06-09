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
    logging.error("Failed to import detect_and_draw_qrcodes")
    detect_and_draw_qrcodes = None

try:
    from charuco_detector import detect_charuco_board
except ImportError:
    logging.error("Failed to import detect_charuco_board")
    detect_charuco_board = None

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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

def cv_image_to_base64(cv_image):
    """Convert OpenCV image to base64 string for web display."""
    if cv_image is None:
        return None
    
    # Convert BGR to RGB
    rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_image)
    
    # Convert to base64
    buffer = io.BytesIO()
    pil_image.save(buffer, format='JPEG', quality=85)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return f"data:image/jpeg;base64,{image_base64}"

def process_image(image_path):
    """Process image for QR codes and ChArUco detection."""
    result = {
        'original_image': None,
        'processed_image': None,
        'charuco_detected': False,
        'qr_codes': []
    }
    
    # Load image
    cv_image = cv2.imread(image_path)
    if cv_image is None:
        return result
    
    # Convert original image to base64
    result['original_image'] = cv_image_to_base64(cv_image)
    
    # Start with copy for processing
    processed_image = cv_image.copy()
    
    # QR Code detection
    if detect_and_draw_qrcodes:
        try:
            qr_images, qr_decoded_texts = detect_and_draw_qrcodes(cv_image)
            if qr_images and len(qr_images) > 0 and qr_images[0] is not None:
                processed_image = qr_images[0]
                if qr_decoded_texts:
                    result['qr_codes'] = qr_decoded_texts
        except Exception as e:
            logging.error(f"QR detection error: {e}")
    
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
                    result['charuco_detected'] = True
        except Exception as e:
            logging.error(f"ChArUco detection error: {e}")
    
    result['processed_image'] = cv_image_to_base64(processed_image)
    return result

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle multiple file uploads."""
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files[]')
    image_paths = []
    
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image_paths.append(filename)
    
    # Store in session
    session['image_paths'] = image_paths
    session['current_index'] = 0 if image_paths else -1
    
    return jsonify({
        'success': True,
        'image_count': len(image_paths),
        'images': image_paths
    })

@app.route('/process/<int:index>')
def process_image_route(index):
    """Process image at given index."""
    image_paths = session.get('image_paths', [])
    
    if not (0 <= index < len(image_paths)):
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
    return jsonify(result)

@app.route('/navigate/<direction>')
def navigate(direction):
    """Navigate to next/previous image."""
    current_index = session.get('current_index', 0)
    image_paths = session.get('image_paths', [])
    
    if direction == 'next' and current_index < len(image_paths) - 1:
        new_index = current_index + 1
    elif direction == 'prev' and current_index > 0:
        new_index = current_index - 1
    else:
        return jsonify({'error': 'Invalid navigation'}), 400
    
    return redirect(url_for('process_image_route', index=new_index))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app.run(debug=True, host='0.0.0.0', port=8000)
