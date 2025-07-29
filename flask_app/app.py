"""
app.py - Main Flask Application for the Semillas Image Processor

This module implements a web-based image analysis tool using the Flask framework.
It provides a user interface for uploading or selecting images and processing them
to detect and analyze ChArUco boards and QR codes.

Key Features:
- **Dual Image Sources:** Supports processing images from two distinct sources:
  1.  **Local Uploads:** Users can upload multiple image files directly to the server.
  2.  **Google Drive Integration:** Users can authenticate with their Google account,
      browse their Drive folders, or paste a folder link to process images stored
      in the cloud.
- **Image Processing:**
  - **QR Code Detection:** Identifies QR codes in images, draws bounding boxes,
    and decodes their content. It can handle standard text and compressed JSON data.
  - **ChArUco Board Detection:** Detects ChArUco calibration patterns, drawing
    the detected board and corners on the image.
- **Dynamic Web Interface:** The backend serves a single main HTML page (`index.html`)
  and provides a set of API endpoints. The frontend uses JavaScript (AJAX/Fetch)
  to communicate with these endpoints, allowing for a dynamic user experience
  without full page reloads (e.g., navigating between images, viewing processing
  results).
- **Google OAuth 2.0 Flow:** Manages the entire authentication and authorization
  process for accessing Google Drive, including token handling, refresh, and
  session management.
- **State Management:** Uses Flask's session to maintain user state across requests,
  such as the list of images (local or Drive), the current image index, and
  Google authentication credentials.

Architecture:
- The application is built around a set of RESTful-like API endpoints that return
  JSON data.
- A central helper function, `get_processed_image_data`, abstracts the logic for
  fetching and processing an image, regardless of its source (local or Drive).
- For Google Drive, image metadata (file list) is fetched once per folder, but
  the actual image content is downloaded on-demand as the user navigates to it,
  improving performance and reducing bandwidth.
- The application is configured to run behind a reverse proxy (using
  `werkzeug.middleware.proxy_fix.ProxyFix`), making it suitable for deployment
  on platforms like Google Cloud Run.

Configuration:
- The application relies on environment variables for sensitive data, primarily
  `FLASK_SECRET_KEY` and `GOOGLE_OAUTH_CREDENTIALS`. It falls back to a local
  `client_secret.json` file if the environment variable is not set.
"""
from flask import Flask, request, render_template, jsonify, send_file, session, redirect, url_for, flash
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import google.oauth2.credentials
from googleapiclient.errors import HttpError
import google.auth.transport.requests # Moved here
import googleapiclient.http # Added
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
import os
from werkzeug.middleware.proxy_fix import ProxyFix # Added ProxyFix
import re # Added for regex operations

# Optional imports with error handling
try:
    from utils.detect_and_draw_qr import detect_and_draw_qrcodes
except ImportError:
    logging.error("Failed to import detect_and_draw_qrcodes from detect_and_draw_qr. QR detection will be skipped.")
    detect_and_draw_qrcodes = None

try:
    from utils.charuco_detector import detect_charuco_board
except ImportError:
    logging.error("Failed to import detect_charuco_board")
    detect_charuco_board = None


os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a-default-fallback-secret-key-if-not-set') # It's better to use environment variables for secret keys

# If app is behind one proxy (e.g., Cloud Run's frontend)
# This will tell Flask to trust X-Forwarded-Proto, X-Forwarded-Host, etc.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

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
app.config['DRIVE_TEMP_FOLDER'] = 'drive_temp_downloads' # Added
app.config['SERVER_IMAGES_FOLDER'] = 'shared_data' # This maps to /app/shared_data in Docker

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DRIVE_TEMP_FOLDER'], exist_ok=True) # Added
os.makedirs(app.config['SERVER_IMAGES_FOLDER'], exist_ok=True) # Added

# Google OAuth Configuration
CLIENT_SECRETS_FILE = 'client_secret.json' # IMPORTANT: This file needs to be obtained from Google Cloud Console
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly', 'https://www.googleapis.com/auth/drive.readonly']

# ChArUco configuration
CHARUCO_CONFIG = {
    'SQUARES_X': 5,
    'SQUARES_Y': 5,
    'SQUARE_LENGTH_MM': 10.0,
    'MARKER_LENGTH_MM': 7.0,
    'DICTIONARY_NAME': "DICT_4X4_100"
}

def load_google_flow(scopes, redirect_uri, state=None):
    """Loads and configures the Google OAuth2 Flow object.

    This function centralizes the logic for initializing the OAuth flow. It prioritizes
    loading credentials from the `GOOGLE_OAUTH_CREDENTIALS` environment variable,
    which can contain either a direct JSON string or a path to a credentials file.
    If the environment variable is not set or fails to load, it falls back to
    a local `client_secret.json` file.

    Args:
        scopes (list[str]): A list of strings representing the Google API scopes
            required for the application.
        redirect_uri (str): The URI that Google will redirect to after the user
            authorizes the application. This must match one of the authorized
            redirect URIs in the Google Cloud Console.
        state (str, optional): A unique string to prevent cross-site request forgery.
            If provided, it will be included in the authorization request and
            checked on the callback. Defaults to None.

    Returns:
        google_auth_oauthlib.flow.Flow: An initialized Flow object ready to be used
            for generating an authorization URL or fetching a token.

    """
    client_config = None
    creds_env_var = os.getenv("GOOGLE_OAUTH_CREDENTIALS")

    if creds_env_var:
        try:
            # Attempt to parse as direct JSON content
            client_config = json.loads(creds_env_var)
            app.logger.info("Loaded Google OAuth credentials from GOOGLE_OAUTH_CREDENTIALS env var (direct JSON).")
        except json.JSONDecodeError:
            # If not direct JSON, treat as a file path
            app.logger.info(f"GOOGLE_OAUTH_CREDENTIALS env var is not direct JSON, treating as path: {creds_env_var}")
            if os.path.exists(creds_env_var):
                try:
                    with open(creds_env_var, 'r') as f:
                        client_config = json.load(f)
                    app.logger.info(f"Loaded Google OAuth credentials from file specified in GOOGLE_OAUTH_CREDENTIALS: {creds_env_var}")
                except Exception as e:
                    app.logger.error(f"Error reading/parsing credentials file from GOOGLE_OAUTH_CREDENTIALS path '{creds_env_var}': {e}")
            else:
                app.logger.warning(f"File specified in GOOGLE_OAUTH_CREDENTIALS env var not found: {creds_env_var}")
        except Exception as e:
            app.logger.error(f"Error processing GOOGLE_OAUTH_CREDENTIALS env var: {e}")

    if client_config:
        return Flow.from_client_config(client_config, scopes=scopes, redirect_uri=redirect_uri, state=state)
    else:
        # Fallback to CLIENT_SECRETS_FILE
        app.logger.info(f"Falling back to CLIENT_SECRETS_FILE: {CLIENT_SECRETS_FILE}")
        # FileNotFoundError will be raised by from_client_secrets_file if CLIENT_SECRETS_FILE doesn't exist.
        return Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=scopes, redirect_uri=redirect_uri, state=state)

@app.errorhandler(413)
def request_entity_too_large(error):
    """Custom error handler for HTTP 413 Request Entity Too Large.

    This function is triggered when an upload exceeds the `MAX_CONTENT_LENGTH`
    configured for the Flask app. It logs the error details and returns a
    JSON response to the client, providing a more user-friendly error message
    than the default server response.

    Args:
        error: The error object passed by Flask.

    Returns:
        tuple[flask.Response, int]: A tuple containing a JSON response object
            with error details and the HTTP status code 413.
    """
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
    """Converts an OpenCV image (numpy array) to a base64 encoded string.

    This is used to embed image data directly into HTML or JSON responses for
    display in a web browser. The image is converted from BGR (OpenCV's default)
    to RGB, then saved as a JPEG in-memory, and finally base64 encoded.

    Args:
        cv_image (numpy.ndarray): The input image in OpenCV format (BGR color).

    Returns:
        str | None: A data URI string (e.g., "data:image/jpeg;base64,...")
            representing the image, or None if the input `cv_image` is None.
    """
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

def process_image(image_path, return_image_object=False):
    """Loads an image from a file path and processes it for ChArUco and QR codes.

    This function performs the core image analysis:
    1. Reads the image file using OpenCV.
    2. Converts the original image to base64 for display.
    3. Calls `detect_and_draw_qrcodes` to find and decode QR codes, drawing on a copy.
    4. Calls `detect_charuco_board` on the (potentially QR-annotated) image.
    5. Converts the final processed image to base64.

    Args:
        image_path (str): The local file system path to the image to be processed.
        return_image_object (bool): If True, the function returns the processed
                                    OpenCV image object instead of the dictionary.


    Returns:
        dict or numpy.ndarray: A dictionary containing the processing results,
            or the processed OpenCV image object if return_image_object is True.
            - 'original_image' (str): Base64 encoded original image.
            - 'processed_image' (str): Base64 encoded image with detections drawn.
            - 'charuco_detected' (bool): True if a ChArUco board was found.
            - 'qr_codes' (list[str]): A list of decoded string data from QR codes.
            - 'qr_codes_json' (list[dict]): A list of decoded JSON objects from QR codes.
            Returns a dictionary with default values if the image cannot be loaded.
    """
    app.logger.info(f"Starting image processing for: {image_path}")
    result = {
        'original_image': None,
        'processed_image': None,
        'charuco_detected': False,
        'qr_codes': [],
        'qr_codes_json': []
    }
    
    # Load image
    app.logger.info(f"Loading image from path: {image_path}")
    cv_image = cv2.imread(image_path)
    if cv_image is None:
        app.logger.error(f"Failed to load image from path: {image_path}")
        return result if not return_image_object else None
    
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

    if return_image_object:
        return processed_image

    result['processed_image'] = cv_image_to_base64(processed_image)
    app.logger.info(f"Finished image processing for: {image_path}. Charuco detected: {result['charuco_detected']}, QR codes: {len(result['qr_codes'])}")
    return result

def get_processed_image_data(index):
    """Fetches and processes an image by its index, abstracting the source.

    This is a central helper that handles two modes based on the user's session:
    1.  **Google Drive Mode**: If a Drive folder is selected, it uses the index to
        find the file ID, downloads the image to a temporary location, processes it,
        and then deletes the temporary file. It also handles Google API token refresh.
    2.  **Local Mode**: If images were uploaded locally, it uses the index to find
        the file path in the `uploads` folder and processes it.

    It consolidates the processing results with navigation and state information.

    Args:
        index (int): The zero-based index of the image to process from the
            current list (either in `session['drive_image_files']` or
            `session['image_paths']`).

    Returns:
        tuple[dict, int]: A tuple containing:
            - A dictionary with the processed data. On success, this includes
              image data, navigation state ('current_index', 'total_images',
              'has_next', 'has_prev'), and metadata ('filename', 'source').
              On error, it contains an 'error' key and may include a 'redirect' URL.
            - An integer representing the HTTP status code (e.g., 200, 400, 401, 404, 500).
    """
    app.logger.info(f"Getting processed image data for index: {index}.")

    if session.get('selected_google_drive_folder_id') and session.get('drive_image_files') is not None:
        # Google Drive Mode
        drive_files = session.get('drive_image_files', [])
        if not (0 <= index < len(drive_files)):
            app.logger.warning(f"Invalid Drive image index {index} requested. Total Drive images: {len(drive_files)}.")
            return ({'error': 'Invalid Drive image index'}, 400)

        image_info = drive_files[index]
        file_id = image_info['id']
        file_name = image_info['name']
        secure_file_name = secure_filename(file_name) if file_name else f"unnamed_drive_file_{file_id}"
        if not secure_file_name:
            secure_file_name = f"drive_file_{file_id}"
        temp_image_path = os.path.join(app.config['DRIVE_TEMP_FOLDER'], secure_file_name)
        app.logger.info(f"Processing Drive file: ID='{file_id}', Name='{file_name}', Temp Path='{temp_image_path}'")

        if 'google_credentials' not in session:
            return ({'error': 'Google session ended', 'redirect': url_for('login_google')}, 401)

        download_attempted_or_successful = False
        try:
            creds_dict = session['google_credentials']
            if not all(k in creds_dict for k in ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret', 'scopes']):
                raise ValueError("Stored Google credentials missing required fields.")

            credentials = google.oauth2.credentials.Credentials(**creds_dict)
            if credentials.expired and credentials.refresh_token:
                req = google.auth.transport.requests.Request()
                credentials.refresh(req)
                session['google_credentials'] = {
                    'token': credentials.token, 'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret, 'scopes': credentials.scopes
                }
                app.logger.info("Refreshed Google token for downloading image.")

            service = build('drive', 'v3', credentials=credentials)
            drive_request = service.files().get_media(fileId=file_id)

            with io.FileIO(temp_image_path, 'wb') as fh:
                downloader = googleapiclient.http.MediaIoBaseDownload(fh, drive_request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    app.logger.info(f"Download {file_name}: {int(status.progress() * 100)}%.")
            app.logger.info(f"Successfully downloaded Drive file '{file_name}' to '{temp_image_path}'.")
            download_attempted_or_successful = True

            result_data = process_image(temp_image_path)
            result_data.update({
                'current_index': index,
                'total_images': len(drive_files),
                'filename': file_name,
                'has_next': index < len(drive_files) - 1,
                'has_prev': index > 0,
                'source': 'drive'
            })
            session['current_drive_image_index'] = index
            return result_data, 200
        except HttpError as error:
            app.logger.error(f"Google Drive API HttpError downloading file '{file_name}': {error.resp.status} - {error._get_reason()}", exc_info=True)
            status_code = error.resp.status
            error_payload = {'error': f"API error accessing file '{file_name}'. Status: {status_code}.", 'filename': file_name, 'current_index': index, 'total_images': len(drive_files), 'has_next': index < len(drive_files) - 1, 'has_prev': index > 0, 'is_api_error': True, 'source': 'drive'}
            if status_code == 404: error_payload['error'] = f"Image '{file_name}' not found on Google Drive (404)."
            elif status_code == 403: error_payload['error'] = f"Permission denied for image '{file_name}' on Google Drive (403)."
            elif status_code == 401: error_payload['error'] = f"Authentication error for '{file_name}' (401)."; session.pop('google_credentials', None); error_payload['redirect'] = url_for('login_google')
            return error_payload, status_code
        except ValueError as ve:
            app.logger.error(f"Credential error processing Drive image: {ve}", exc_info=True)
            session.pop('google_credentials', None)
            return ({'error': 'Corrupted Google session data.', 'redirect': url_for('login_google'), 'is_api_error': True}, 401)
        except Exception as e:
            app.logger.error(f"Unexpected error processing Drive file '{file_name}' (index {index}): {e}", exc_info=True)
            return ({'error': f"An unexpected error occurred while processing file '{file_name}'.", 'filename': file_name, 'current_index': index, 'total_images': len(drive_files), 'has_next': index < len(drive_files) - 1, 'has_prev': index > 0, 'is_api_error': True, 'source': 'drive'}, 500)
        finally:
            if download_attempted_or_successful and os.path.exists(temp_image_path):
                try:
                    os.remove(temp_image_path)
                    app.logger.info(f"Successfully deleted temporary Drive file: {temp_image_path}")
                except OSError as e_remove:
                    app.logger.error(f"Error deleting temporary Drive file {temp_image_path}: {e_remove}")
    elif session.get('is_server_mode') and session.get('server_image_files') is not None: # New Server Mode
        server_files = session.get('server_image_files', [])
        if not (0 <= index < len(server_files)):
            app.logger.warning(f"Invalid Server image index {index} requested. Total Server images: {len(server_files)}.")
            return ({'error': 'Invalid Server image index'}, 400)

        file_name = server_files[index]
        image_path = os.path.join(app.config['SERVER_IMAGES_FOLDER'], file_name)
        app.logger.info(f"Processing Server file: Name='{file_name}', Path='{image_path}'")

        result_data = process_image(image_path)
        result_data.update({
            'current_index': index,
            'total_images': len(server_files),
            'filename': file_name,
            'has_next': index < len(server_files) - 1,
            'has_prev': index > 0,
            'source': 'server'
        })
        session['current_server_image_index'] = index
        app.logger.info(f"Successfully processed server image at index {index}: {file_name}. Returning data.")
        return result_data, 200
    else:
        # Local File Mode
        image_paths = session.get('image_paths', [])
        if not (0 <= index < len(image_paths)):
            app.logger.warning(f"Invalid local image index {index} requested. Total local images: {len(image_paths)}.")
            return ({'error': 'Invalid local image index'}, 400)

        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_paths[index])
        result_data = process_image(image_path)
        result_data.update({
            'current_index': index, 'total_images': len(image_paths), 'filename': image_paths[index],
            'has_next': index < len(image_paths) - 1, 'has_prev': index > 0, 'source': 'local'
        })
        session['current_index'] = index
        app.logger.info(f"Successfully processed local image at index {index}: {image_paths[index]}. Returning data.")
        return result_data, 200

@app.route('/')
def index():
    """Renders the main application page (index.html).

    This is the main entry point for the user interface. It checks the session
    to determine if the application is in "local upload mode" or "Google Drive mode"
    and passes relevant state to the template, such as the number of images and
    the current mode. This allows the Jinja2 template to render the correct UI
    elements on initial page load.

    Returns:
        str: The rendered HTML content of the `index.html` template.
    """
    app.logger.info("Main page '/' accessed.")
    drive_image_files = session.get('drive_image_files', [])
    drive_images_count = len(drive_image_files)
    server_image_files = session.get('server_image_files', [])
    server_images_count = len(server_image_files)

    # Determine the active mode. Server mode takes precedence over drive mode if both are somehow set.
    is_server_mode = bool(session.get('is_server_mode') and server_image_files is not None)
    is_drive_mode = bool(session.get('selected_google_drive_folder_id') and drive_image_files is not None and not is_server_mode)

    # If in drive mode and no images, or index is bad, try to reset/clarify state
    if is_server_mode: # Check server mode first
        current_server_index = session.get('current_server_image_index', -1)
        if not server_image_files or current_server_index == -1:
            app.logger.info("Server mode active but no images or invalid index, ensuring clean state for JS.")
        elif current_server_index >= server_images_count:
            app.logger.warning(f"Server index {current_server_index} out of bounds for {server_images_count} images. Resetting index.")
            session['current_server_image_index'] = 0 if server_images_count > 0 else -1
    elif is_drive_mode:
        current_drive_index = session.get('current_drive_image_index', -1)
        if not drive_image_files or current_drive_index == -1 : # No images, or explicitly set to no valid image
             app.logger.info("Drive mode active but no images or invalid index, ensuring clean state for JS.")
             # This helps JS initialize correctly if user selected an empty folder or an error occurred fetching images.
        elif current_drive_index >= drive_images_count: # Index out of bounds
            app.logger.warning(f"Drive index {current_drive_index} out of bounds for {drive_images_count} images. Resetting index.")
            session['current_drive_image_index'] = 0 if drive_images_count > 0 else -1
    else: # Local file mode or initial state
        # Ensure server/drive modes are explicitly off if we're not in them
        session.pop('is_server_mode', None)
        session.pop('server_image_files', None)
        session.pop('current_server_image_index', None)
        session.pop('selected_google_drive_folder_id', None)
        session.pop('drive_image_files', None)
        session.pop('current_drive_image_index', None)


    return render_template('index.html',
                           drive_images_count=drive_images_count,
                           is_drive_mode=is_drive_mode,
                           server_images_count=server_images_count, # New
                           is_server_mode=is_server_mode) # New

@app.route('/login/google')
def login_google():
    """Initiates the Google OAuth 2.0 authentication flow.

    This route generates the Google authorization URL with the necessary scopes
    and a unique 'state' token for CSRF protection. It then redirects the user's
    browser to this URL to grant the application permission to access their
    Google Drive files.

    Returns:
        flask.Response: A redirect to the Google authorization page.
        On configuration error, it renders an error page with a 500 status code.
    """
    try:
        redirect_uri_for_google = url_for('authorize_google', _external=True)
        app.logger.info(f"Using redirect_uri for Google OAuth: {redirect_uri_for_google}")
        flow = load_google_flow(scopes=SCOPES, redirect_uri=redirect_uri_for_google)

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='select_account'  # Add this line
        )
        session['state'] = state
        # app.logger.info(f"Redirecting to Google for authorization. State: {state}. Authorization URL: {authorization_url}")
        return redirect(authorization_url)
    except FileNotFoundError:
        app.logger.error(f"OAuth2 client secrets configuration not found. Neither GOOGLE_OAUTH_CREDENTIALS env var nor '{CLIENT_SECRETS_FILE}' file were successfully loaded.")
        return render_template('error.html', message=f"OAuth2 client secrets configuration not found. Ensure GOOGLE_OAUTH_CREDENTIALS is set correctly or '{CLIENT_SECRETS_FILE}' is available."), 500
    except Exception as e:
        app.logger.error(f"Error during Google login initiation: {e}", exc_info=True)
        return render_template('error.html', message="An error occurred during Google login."), 500

@app.route('/logout/google')
def logout_google():
    """Logs the user out from their Google account within the application.

    This function clears all Google-related data from the user's session,
    including credentials, state, and the list of Drive files. It effectively
    resets the application to its initial state, requiring the user to
    log in again to access Google Drive features.

    Returns:
        flask.Response: A redirect to the main index page.
    """
    session.pop('google_credentials', None)
    session.pop('state', None)
    session.pop('selected_google_drive_folder_id', None)
    session.pop('selected_google_drive_folder_name', None)
    session.pop('drive_image_files', None) # Added
    session.pop('current_drive_image_index', None) # Added
    session.pop('server_image_files', None) # New
    session.pop('is_server_mode', None) # New
    session.pop('current_server_image_index', None) # New
    app.logger.info("User logged out from Google, session cleared for Drive items as well.")
    flash('You have been logged out from Google.', 'info')
    return redirect(url_for('index'))

@app.route('/drive/folders')
def drive_folders():
    """Fetches and displays a list of the user's Google Drive folders.

    This route requires the user to be logged in. It uses the stored Google
    credentials to make an API call to the Google Drive v3 API, listing all
    folders owned by the user. It handles token expiration and refresh. The
    list of folders is then passed to the `drive_folders.html` template for rendering.

    Returns:
        str | flask.Response: The rendered `drive_folders.html` page with the list
            of folders. If the user is not logged in or the token refresh fails,
            it redirects to the login page. If an API error occurs, it renders
            the folder list page with an error message.
    """
    if 'google_credentials' not in session:
        flash('Please login with Google first.', 'warning')
        return redirect(url_for('login_google'))

    try:
        creds_dict = session['google_credentials']
        # Ensure all required fields are present for Credentials object
        if not all(k in creds_dict for k in ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret', 'scopes']):
            app.logger.error("Stored Google credentials missing required fields.")
            flash("Your Google session data is corrupted. Please log in again.", "error")
            session.pop('google_credentials', None) # Clear corrupted creds
            return redirect(url_for('login_google'))

        credentials = google.oauth2.credentials.Credentials(**creds_dict)

        if credentials.expired and credentials.refresh_token:
            app.logger.info("Google API credentials expired, attempting refresh.")
            try:
                # Attempt to refresh token
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
                # Update session with new token
                session['google_credentials'] = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                app.logger.info("Google API credentials refreshed successfully.")
            except Exception as refresh_error:
                app.logger.error(f"Error refreshing Google API token: {refresh_error}", exc_info=True)
                flash('Your Google session has expired and could not be refreshed. Please log in again.', 'error')
                session.pop('google_credentials', None)
                session.pop('state', None)
                return redirect(url_for('login_google'))

        service = build('drive', 'v3', credentials=credentials)

        results = service.files().list(
            q="mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='nextPageToken, files(id, name)'
        ).execute()

        items = results.get('files', [])
        app.logger.info(f"Found {len(items)} folders in Google Drive.")
        return render_template('drive_folders.html', folders=items)

    except HttpError as error:
        app.logger.error(f"Google Drive API HttpError: {error.resp.status} - {error._get_reason()}", exc_info=True)
        error_json = error.resp.reason
        try:
            error_details = json.loads(error.content).get('error', {})
            message = error_details.get('message', 'An API error occurred.')
            if error_details.get('status') == 'PERMISSION_DENIED':
                message = "Permission denied. Ensure the application has access to Google Drive."
            elif error.resp.status == 401 or error.resp.status == 403: # Unauthorized or Forbidden
                 flash('Your Google session is invalid or has expired. Please log in again.', 'error')
                 session.pop('google_credentials', None)
                 session.pop('state', None)
                 return redirect(url_for('login_google'))
        except json.JSONDecodeError:
            message = f"An API error occurred: {error_json}"

        return render_template('drive_folders.html', error=message)
    except Exception as e:
        app.logger.error(f"Unexpected error listing Google Drive folders: {e}", exc_info=True)
        return render_template('drive_folders.html', error='An unexpected error occurred while fetching folders.')

@app.route('/drive/select_folder/<folder_id>/<path:folder_name>')
def drive_select_folder(folder_id, folder_name):
    """Handles the selection of a Google Drive folder.

    When a user clicks a folder from the list, this route is called. It stores
    the selected folder's ID and name in the session. It then makes another
    Google Drive API call to list all image files within that folder. The list
    of image files (ID and name) is stored in the session, and the user is
    redirected back to the main index page, which will now be in "Drive mode".

    Args:
        folder_id (str): The unique ID of the selected Google Drive folder.
        folder_name (str): The name of the selected Google Drive folder.

    Returns:
        flask.Response: A redirect to the main index page.
    """
    if 'google_credentials' not in session:
        flash('Please login with Google first.', 'warning')
        return redirect(url_for('login_google'))

    session['selected_google_drive_folder_id'] = folder_id
    session['selected_google_drive_folder_name'] = folder_name
    app.logger.info(f"User selected Google Drive folder: ID={folder_id}, Name='{folder_name}'")

    # Clear local file session variables
    session.pop('image_paths', None)
    session.pop('current_index', None)
    session.pop('server_image_files', None) # New
    session.pop('is_server_mode', None) # New
    session.pop('current_server_image_index', None) # New
    app.logger.info("Cleared local image session data after selecting Drive folder.")

    # Fetch image files from the selected folder
    if 'google_credentials' not in session:
        flash('Google session ended. Please login again.', 'warning')
        return redirect(url_for('login_google'))
    try:
        creds_dict = session['google_credentials']
        if not all(k in creds_dict for k in ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret', 'scopes']):
            app.logger.error("Stored Google credentials missing required fields when fetching folder content.")
            flash("Your Google session data is corrupted. Please log in again.", "error")
            session.pop('google_credentials', None)
            return redirect(url_for('login_google'))

        credentials = google.oauth2.credentials.Credentials(**creds_dict)
        if credentials.expired and credentials.refresh_token:
            req = google.auth.transport.requests.Request()
            credentials.refresh(req)
            session['google_credentials'] = {
                'token': credentials.token, 'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
                'client_secret': credentials.client_secret, 'scopes': credentials.scopes
            }
            app.logger.info("Refreshed Google token for fetching folder content.")

        service = build('drive', 'v3', credentials=credentials)
        query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/bmp' or mimeType='image/gif') and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        items = results.get('files', [])

        session['drive_image_files'] = [{'id': file['id'], 'name': file['name']} for file in items]
        if items:
            session['current_drive_image_index'] = 0
            flash(f"Selected folder '{folder_name}'. Found {len(items)} images.", 'success')
            app.logger.info(f"Found {len(items)} images in Drive folder '{folder_name}'.")
        else:
            session['current_drive_image_index'] = -1
            flash(f"Selected folder '{folder_name}'. No images found in this folder.", 'info')
            app.logger.info(f"No images found in Drive folder '{folder_name}'.")

    except HttpError as error:
        app.logger.error(f"Google Drive API HttpError while listing images in folder: {error}", exc_info=True)
        flash(f"Error accessing folder '{folder_name}': {error._get_reason()}", 'danger')
        if error.resp.status == 401 or error.resp.status == 403:
             session.pop('google_credentials', None)
             return redirect(url_for('login_google'))
        # Keep selected folder ID, but clear images
        session['drive_image_files'] = []
        session['current_drive_image_index'] = -1
    except Exception as e:
        app.logger.error(f"Unexpected error listing images in Drive folder: {e}", exc_info=True)
        flash(f"An unexpected error occurred while fetching images from folder '{folder_name}'.", 'danger')
        session['drive_image_files'] = []
        session['current_drive_image_index'] = -1

    return redirect(url_for('index'))

def extract_folder_id_from_url(url):
    """Extracts a Google Drive folder ID from various common URL formats.

    This utility function uses regular expressions to parse a URL string and find
    the folder ID. It supports formats like:
    - `.../folders/FOLDER_ID`
    - `.../drive/u/0/folders/FOLDER_ID`
    - `.../open?id=FOLDER_ID`

    Args:
        url (str): The Google Drive URL to parse.

    Returns:
        str | None: The extracted folder ID if found, otherwise None.
    """
    if not url:
        return None
    # Handles /folders/ID and /u/X/folders/ID
    match_path = re.search(r"folders/([-\w]{25,})", url)
    if match_path:
        return match_path.group(1)
    
    # Handles drive.google.com/open?id=ID or drive.google.com/folderview?id=ID
    match_id_param = re.search(r"[?&]id=([-\w]{25,})", url)
    if match_id_param:
        return match_id_param.group(1)
        
    return None

@app.route('/process_drive_link', methods=['POST'])
def process_drive_link():
    """Processes a Google Drive folder link submitted by the user.

    This is an API endpoint that receives a Drive folder URL in a POST request.
    It extracts the folder ID, fetches the folder's metadata (like its name) and
    its image contents from the Google Drive API, and then sets up the session
    for "Drive mode" just like `drive_select_folder`.

    Returns:
        flask.Response: A JSON response indicating success or failure.
            On success, it includes the number of images found and the folder name.
            On failure, it includes an error message and an appropriate HTTP status code.
    """
    if 'google_credentials' not in session:
        app.logger.warning("Attempt to process Drive link without Google credentials.")
        return jsonify({'success': False, 'error': 'Not logged into Google. Please login first.', 'redirect': url_for('login_google')}), 401

    data = request.get_json()
    if not data or 'drive_link' not in data:
        app.logger.warning("Process Drive link request missing 'drive_link' in JSON payload.")
        return jsonify({'success': False, 'error': 'Drive link not provided.'}), 400

    drive_link = data['drive_link']
    folder_id = extract_folder_id_from_url(drive_link)

    if not folder_id:
        app.logger.warning(f"Could not extract folder ID from Drive link: {drive_link}")
        return jsonify({'success': False, 'error': 'Invalid Google Drive folder link format.'}), 400

    app.logger.info(f"Processing Drive link for folder ID: {folder_id}")

    # Clear local file session variables
    session.pop('image_paths', None)
    session.pop('current_index', None)
    session.pop('server_image_files', None) # New
    session.pop('is_server_mode', None) # New
    session.pop('current_server_image_index', None) # New
    app.logger.info("Cleared local image session data for Drive link processing.")

    try:
        creds_dict = session['google_credentials']
        if not all(k in creds_dict for k in ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret', 'scopes']):
            app.logger.error("Stored Google credentials missing required fields for process_drive_link.")
            session.pop('google_credentials', None)
            return jsonify({'success': False, 'error': 'Google session data corrupted. Please log in again.', 'redirect': url_for('login_google')}), 401

        credentials = google.oauth2.credentials.Credentials(**creds_dict)
        if credentials.expired and credentials.refresh_token:
            req = google.auth.transport.requests.Request()
            credentials.refresh(req)
            session['google_credentials'] = {
                'token': credentials.token, 'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
                'client_secret': credentials.client_secret, 'scopes': credentials.scopes
            }
            app.logger.info("Refreshed Google token for processing Drive link.")

        service = build('drive', 'v3', credentials=credentials)

        # Get folder name
        folder_metadata = service.files().get(fileId=folder_id, fields='id, name').execute()
        folder_name = folder_metadata.get('name', 'Unknown Folder')

        session['selected_google_drive_folder_id'] = folder_id
        session['selected_google_drive_folder_name'] = folder_name

        query = f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/bmp' or mimeType='image/gif') and trashed=false"
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        items = results.get('files', [])

        session['drive_image_files'] = [{'id': file['id'], 'name': file['name']} for file in items]
        session['current_drive_image_index'] = 0 if items else -1

        app.logger.info(f"Successfully processed Drive link. Folder: '{folder_name}', Images found: {len(items)}")
        return jsonify({'success': True, 'image_count': len(items), 'folder_name': folder_name})

    except HttpError as error:
        app.logger.error(f"Google Drive API HttpError processing link for folder ID {folder_id}: {error}", exc_info=True)
        error_message = f"Error accessing Google Drive: {error._get_reason()}"
        if error.resp.status == 401 or error.resp.status == 403:
             session.pop('google_credentials', None) # Force re-login
             error_message = 'Google session invalid or expired. Please log in again.'
        return jsonify({'success': False, 'error': error_message, 'redirect': url_for('login_google') if error.resp.status in [401,403] else None}), error.resp.status
    except Exception as e:
        app.logger.error(f"Unexpected error processing Drive link for folder ID {folder_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'An unexpected error occurred.'}), 500

@app.route('/authorize/google')
def authorize_google():
    """Handles the OAuth 2.0 callback from Google.

    After a user authorizes the application, Google redirects them to this URL.
    This function validates the 'state' parameter to prevent CSRF attacks, then
    exchanges the authorization code (from the request URL) for an access token
    and a refresh token. These credentials are then stored securely in the user's
    session.

    Returns:
        flask.Response: A redirect to the main index page on success.
        On error (e.g., state mismatch, token fetch failure), it returns an
        error message or renders an error page.
    """
    state = session.get('state')
    if not state or state != request.args.get('state'):
        app.logger.error("State mismatch during Google OAuth callback.")
        return "Error: State mismatch. Please try logging in again.", 400

    try:
        redirect_uri_for_google = url_for('authorize_google', _external=True)
        flow = load_google_flow(scopes=SCOPES, redirect_uri=redirect_uri_for_google, state=state)
        flow.fetch_token(authorization_response=request.url)

        # Store credentials in session
        credentials = flow.credentials
        session['google_credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        app.logger.info("Successfully fetched Google OAuth token and stored in session.")
        return redirect(url_for('index')) # Or a 'logged_in_success.html' page
    except FileNotFoundError:
        app.logger.error(f"OAuth2 client secrets configuration not found during token fetch. Neither GOOGLE_OAUTH_CREDENTIALS env var nor '{CLIENT_SECRETS_FILE}' file were successfully loaded.")
        return render_template('error.html', message=f"OAuth2 client secrets configuration not found. Ensure GOOGLE_OAUTH_CREDENTIALS is set correctly or '{CLIENT_SECRETS_FILE}' is available."), 500
    except Exception as e:
        app.logger.error(f"Error fetching Google OAuth token: {e}", exc_info=True)
        return render_template('error.html', message="Could not fetch Google authentication token. Please try again."), 500

@app.route('/select_server_images', methods=['POST'])
def select_server_images():
    """API endpoint to select images from a pre-configured server directory.

    This function scans the `SERVER_IMAGES_FOLDER` for image files, stores their
    filenames in the session, and sets the application's state to "Server Mode".
    It clears any existing Local or Google Drive session data.

    Returns:
        flask.Response: A JSON response indicating success or failure,
            including the count of images found.
    """
    app.logger.info("Received request to select server images.")
    # Clear other session variables to switch to server mode
    session.pop('image_paths', None)
    session.pop('current_index', None)
    session.pop('selected_google_drive_folder_id', None)
    session.pop('selected_google_drive_folder_name', None)
    session.pop('drive_image_files', None)
    session.pop('current_drive_image_index', None)
    app.logger.info("Cleared local and Google Drive session data for server image selection.")

    server_image_files = []
    server_images_dir = app.config['SERVER_IMAGES_FOLDER']
    app.logger.info(f"Scanning directory for server images: {server_images_dir}")

    if not os.path.isdir(server_images_dir):
        app.logger.error(f"Server images directory does not exist or is not a directory: {server_images_dir}")
        return jsonify({'success': False, 'error': f'Server image directory not found: {server_images_dir}'}), 500

    try:
        # Recursively scan the directory for image files
        for root, _, files in os.walk(server_images_dir):
            for filename in files:
                if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                    # Store the path relative to the base server images directory
                    relative_path = os.path.relpath(os.path.join(root, filename), server_images_dir)
                    server_image_files.append(relative_path)
        server_image_files.sort() # Sort all found images alphabetically
        app.logger.info(f"Found {len(server_image_files)} images in server directory.")

        session['server_image_files'] = server_image_files
        session['is_server_mode'] = True
        session['current_server_image_index'] = 0 if server_image_files else -1

        return jsonify({
            'success': True,
            'image_count': len(server_image_files)
        })
    except Exception as e:
        app.logger.error(f"Error scanning server image directory {server_images_dir}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': f'Failed to scan server image directory: {e}'}), 500

@app.route('/upload', methods=['POST'])
def upload_files():
    """Handles the uploading of multiple local image files.

    This is an API endpoint for the file upload form. It receives a list of files,
    clears any existing Google Drive session data, saves the valid image files to
    the configured `UPLOAD_FOLDER`, and stores their filenames in the session.

    Returns:
        flask.Response: A JSON response containing:
            - 'success' (bool): True if the operation was successful.
            - 'image_count' (int): The number of valid images successfully uploaded.
            - 'images' (list[str]): A list of the filenames of the uploaded images.
            Returns a JSON error response if no files are provided.
    """
    # Clear Drive session variables if local files are uploaded
    session.pop('selected_google_drive_folder_id', None)
    session.pop('selected_google_drive_folder_name', None)
    session.pop('drive_image_files', None)
    session.pop('current_drive_image_index', None)
    session.pop('server_image_files', None) # New
    session.pop('is_server_mode', None) # New
    session.pop('current_server_image_index', None) # New
    app.logger.info("Cleared Google Drive session variables due to local file upload.")

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
    """API endpoint to process an image at a specific index.

    This route serves as a public API wrapper for the `get_processed_image_data`
    helper function. It takes an integer index and returns the processed image
    data as a JSON response. This is called by the frontend JavaScript to
    display and update the image viewer.

    Args:
        index (int): The zero-based index of the image to process.

    Returns:
        flask.Response: A JSON response containing the processed image data and
            navigation state, along with the appropriate HTTP status code.
    """
    app.logger.info(f"Process image route invoked for index: {index}.")
    data, status_code = get_processed_image_data(index)
    # Flash messages are generally for page loads/redirects, not direct AJAX responses.
    # The frontend should handle errors from the JSON data.
    return jsonify(data), status_code

@app.route('/navigate/<direction>')
def navigate(direction):
    """API endpoint to navigate to the next or previous image.
 
    This route handles requests to move through the image sequence. It determines
    the current source (local, Drive, or Server), calculates the new index based on the
    `direction` parameter ('next' or 'prev'), and then calls the `get_processed_image_data`
    function to fetch and process the new image.
 
    Args:
        direction (str): The direction to navigate, either 'next' or 'prev'.
 
    Returns:
        flask.Response: A JSON response containing the data for the new image,
            identical in format to the response from `/process/<index>`.
    """
    app.logger.info(f"Navigation request received: {direction}.")
    source = 'local' # Default source
 
    if session.get('selected_google_drive_folder_id') and session.get('drive_image_files') is not None:
        source = 'drive'
        current_index = session.get('current_drive_image_index', 0)
        total_images = len(session.get('drive_image_files', []))
        app.logger.debug(f"Drive Navigation: Current index: {current_index}, Total Drive images: {total_images}.")
        if direction == 'next':
            new_index = current_index + 1 if current_index < total_images - 1 else current_index
        elif direction == 'prev':
            new_index = current_index - 1 if current_index > 0 else current_index
        else:
            app.logger.warning(f"Invalid Drive navigation direction: {direction}.")
            return jsonify({'error': 'Invalid navigation direction'}), 400
    elif session.get('is_server_mode') and session.get('server_image_files') is not None:
        source = 'server'
        current_index = session.get('current_server_image_index', 0)
        total_images = len(session.get('server_image_files', []))
        app.logger.debug(f"Server Navigation: Current index: {current_index}, Total Server images: {total_images}.")
        if direction == 'next':
            new_index = current_index + 1 if current_index < total_images - 1 else current_index
        elif direction == 'prev':
            new_index = current_index - 1 if current_index > 0 else current_index
        else:
            app.logger.warning(f"Invalid Server navigation direction: {direction}.")
            return jsonify({'error': 'Invalid navigation direction'}), 400
    else: # Local mode
        current_index = session.get('current_index', 0)
        image_paths = session.get('image_paths', [])
        total_images = len(image_paths)
        app.logger.debug(f"Local Navigation: Current index: {current_index}, Total local images: {total_images}.")
        if direction == 'next':
            new_index = current_index + 1 if current_index < total_images - 1 else current_index
        elif direction == 'prev':
            new_index = current_index - 1 if current_index > 0 else current_index
        else:
            app.logger.warning(f"Invalid local navigation direction: {direction}.")
            return jsonify({'error': 'Invalid navigation direction'}), 400
 
    # If new_index is same as current_index (at a boundary), still fetch data to be consistent.
    # The frontend JS should ideally use 'has_next'/'has_prev' to disable buttons.
    app.logger.info(f"Navigating to image at index: {new_index} (Source: {source.capitalize()}).")
    data, status_code = get_processed_image_data(new_index)
    return jsonify(data), status_code

@app.route('/save_processed_image', methods=['POST'])
def save_processed_image():
    """API endpoint to save the currently processed image to the server.

    This function re-processes the current image to get the raw OpenCV image object,
    creates a designated subfolder if it doesn't exist, and saves the image there.

    Returns:
        flask.Response: A JSON response indicating success or failure,
            including the path to the saved image if successful.
    """
    app.logger.info("Received request to save processed image.")

    # Determine the current index and source
    source = None
    index = -1
    filename = None

    if session.get('selected_google_drive_folder_id') and session.get('drive_image_files') is not None:
        source = 'drive'
        index = session.get('current_drive_image_index', -1)
        if index != -1:
            filename = session['drive_image_files'][index]['name']
    elif session.get('is_server_mode') and session.get('server_image_files') is not None:
        source = 'server'
        index = session.get('current_server_image_index', -1)
        if index != -1:
            filename = session['server_image_files'][index]
    elif session.get('image_paths') is not None:
        source = 'local'
        index = session.get('current_index', -1)
        if index != -1:
            filename = session['image_paths'][index]

    if index == -1 or filename is None:
        app.logger.warning("Save request failed: No image is currently being processed.")
        return jsonify({'success': False, 'error': 'No active image to save.'}), 400

    # This part is a bit tricky as get_processed_image_data is designed to return JSON.
    # We need the raw image. We'll have to get the image path and process it again.
    # This is a simplified version of the logic in get_processed_image_data.

    image_path = None
    temp_image_path = None # For Drive files

    try:
        if source == 'drive':
            # This requires downloading the file again.
            # This logic is duplicated from get_processed_image_data and could be refactored.
            creds_dict = session.get('google_credentials')
            if not creds_dict:
                return jsonify({'success': False, 'error': 'Google session ended.', 'redirect': url_for('login_google')}), 401

            credentials = google.oauth2.credentials.Credentials(**creds_dict)
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(google.auth.transport.requests.Request())
                session['google_credentials'] = {
                    'token': credentials.token, 'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri, 'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret, 'scopes': credentials.scopes
                }

            service = build('drive', 'v3', credentials=credentials)
            file_id = session['drive_image_files'][index]['id']
            secure_file_name = secure_filename(filename)
            temp_image_path = os.path.join(app.config['DRIVE_TEMP_FOLDER'], secure_file_name)

            drive_request = service.files().get_media(fileId=file_id)
            with io.FileIO(temp_image_path, 'wb') as fh:
                downloader = googleapiclient.http.MediaIoBaseDownload(fh, drive_request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            image_path = temp_image_path

        elif source == 'server':
            image_path = os.path.join(app.config['SERVER_IMAGES_FOLDER'], filename)
        else: # local
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        if not os.path.exists(image_path):
            app.logger.error(f"Save failed: Image file not found at path: {image_path}")
            return jsonify({'success': False, 'error': 'Image file not found.'}), 404

        # Re-process the image to get the cv2 object
        processed_cv_image = process_image(image_path, return_image_object=True)

        if processed_cv_image is None:
            app.logger.error(f"Save failed: Processing the image for saving returned None.")
            return jsonify({'success': False, 'error': 'Failed to process image for saving.'}), 500

        # Define save path
        processed_images_subfolder = 'proc_imgs'
        save_dir = os.path.join(app.config['SERVER_IMAGES_FOLDER'], processed_images_subfolder)
        os.makedirs(save_dir, exist_ok=True)

        # Create a new filename for the processed image
        base_filename, ext = os.path.splitext(filename)
        # Sanitize base_filename further if it contains path components (from recursive server scan)
        base_filename = os.path.basename(base_filename)
        processed_filename = f"{base_filename}_processed.jpg" # Save as JPG
        save_path = os.path.join(save_dir, processed_filename)

        # Save the image
        success = cv2.imwrite(save_path, processed_cv_image)
        if not success:
            app.logger.error(f"Failed to save processed image to {save_path}")
            return jsonify({'success': False, 'error': 'Failed to write image file to disk.'}), 500

        app.logger.info(f"Successfully saved processed image to: {save_path}")
        # Return a path relative to the shared folder for user feedback
        user_friendly_path = os.path.join(processed_images_subfolder, processed_filename)
        return jsonify({'success': True, 'message': f'Image saved to {user_friendly_path}', 'path': user_friendly_path})

    except HttpError as error:
        app.logger.error(f"Google Drive API HttpError during save: {error}", exc_info=True)
        return jsonify({'success': False, 'error': 'Google Drive API error while preparing to save.'}), 500
    except Exception as e:
        app.logger.error(f"An unexpected error occurred during save: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'An unexpected error occurred.'}), 500
    finally:
        # Clean up temporary file if it was created
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)


if __name__ == '__main__':
    # Flask's logger is configured above. This basicConfig would be for other modules if needed.
    app.logger.info("Starting Flask application...")
    app.logger.info("Build #42")
    # Use the PORT environment variable provided by Cloud Run, defaulting to 8080 for local dev
    port = int(os.environ.get("PORT", 8080))
    app.logger.info("******* IN DEV ENVIRONMENT USE http://mylocaldomain.com:8080 *****")
    app.run(debug=False, host='0.0.0.0', port=port)
