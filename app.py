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


os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

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
app.config['DRIVE_TEMP_FOLDER'] = 'drive_temp_downloads' # Added

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DRIVE_TEMP_FOLDER'], exist_ok=True) # Added

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
        'qr_codes': [],
        'qr_codes_json': []
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

def get_processed_image_data(index):
    """Helper function to fetch and process image data for a given index."""
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
    """Main page."""
    app.logger.info("Main page '/' accessed.")
    drive_image_files = session.get('drive_image_files', [])
    drive_images_count = len(drive_image_files)
    is_drive_mode = bool(session.get('selected_google_drive_folder_id') and drive_image_files is not None)

    # If in drive mode and no images, or index is bad, try to reset/clarify state
    if is_drive_mode:
        current_drive_index = session.get('current_drive_image_index', -1)
        if not drive_image_files or current_drive_index == -1 : # No images, or explicitly set to no valid image
             app.logger.info("Drive mode active but no images or invalid index, ensuring clean state for JS.")
             # This helps JS initialize correctly if user selected an empty folder or an error occurred fetching images.
        elif current_drive_index >= drive_images_count: # Index out of bounds
            app.logger.warning(f"Drive index {current_drive_index} out of bounds for {drive_images_count} images. Resetting index.")
            session['current_drive_image_index'] = 0 if drive_images_count > 0 else -1


    return render_template('index.html',
                           drive_images_count=drive_images_count,
                           is_drive_mode=is_drive_mode)

@app.route('/login/google')
def login_google():
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=url_for('authorize_google', _external=True)
        )
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        session['state'] = state
        app.logger.info(f"Redirecting to Google for authorization. State: {state}")
        return redirect(authorization_url)
    except FileNotFoundError:
        app.logger.error(f"Client secrets file '{CLIENT_SECRETS_FILE}' not found.")
        return render_template('error.html', message=f"OAuth2 client secrets file ({CLIENT_SECRETS_FILE}) not found. Please configure Google API access."), 500
    except Exception as e:
        app.logger.error(f"Error during Google login initiation: {e}", exc_info=True)
        return render_template('error.html', message="An error occurred during Google login."), 500

@app.route('/logout/google')
def logout_google():
    session.pop('google_credentials', None)
    session.pop('state', None)
    session.pop('selected_google_drive_folder_id', None)
    session.pop('selected_google_drive_folder_name', None)
    session.pop('drive_image_files', None) # Added
    session.pop('current_drive_image_index', None) # Added
    app.logger.info("User logged out from Google, session cleared for Drive items as well.")
    flash('You have been logged out from Google.', 'info')
    return redirect(url_for('index'))

@app.route('/drive/folders')
def drive_folders():
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
    if 'google_credentials' not in session:
        flash('Please login with Google first.', 'warning')
        return redirect(url_for('login_google'))

    session['selected_google_drive_folder_id'] = folder_id
    session['selected_google_drive_folder_name'] = folder_name
    app.logger.info(f"User selected Google Drive folder: ID={folder_id}, Name='{folder_name}'")

    # Clear local file session variables
    session.pop('image_paths', None)
    session.pop('current_index', None)
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
@app.route('/authorize/google')
def authorize_google():
    state = session.get('state')
    if not state or state != request.args.get('state'):
        app.logger.error("State mismatch during Google OAuth callback.")
        return "Error: State mismatch. Please try logging in again.", 400

    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=url_for('authorize_google', _external=True)
        )
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
        app.logger.error(f"Client secrets file '{CLIENT_SECRETS_FILE}' not found during token fetch.")
        return render_template('error.html', message=f"OAuth2 client secrets file ({CLIENT_SECRETS_FILE}) not found. Please configure Google API access."), 500
    except Exception as e:
        app.logger.error(f"Error fetching Google OAuth token: {e}", exc_info=True)
        return render_template('error.html', message="Could not fetch Google authentication token. Please try again."), 500

@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle multiple file uploads."""
    # Clear Drive session variables if local files are uploaded
    session.pop('selected_google_drive_folder_id', None)
    session.pop('selected_google_drive_folder_name', None)
    session.pop('drive_image_files', None)
    session.pop('current_drive_image_index', None)
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
    """Process image at given index from local or Drive."""
    app.logger.info(f"Process image route invoked for index: {index}.")
    data, status_code = get_processed_image_data(index)
    # Flash messages are generally for page loads/redirects, not direct AJAX responses.
    # The frontend should handle errors from the JSON data.
    return jsonify(data), status_code

@app.route('/navigate/<direction>')
def navigate(direction):
    """Navigate to next/previous image, supporting both local and Drive sources."""
    app.logger.info(f"Navigation request received: {direction}.")

    if session.get('selected_google_drive_folder_id') and session.get('drive_image_files') is not None:
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
    else:
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
    app.logger.info(f"Navigating to image at index: {new_index} (Source: {'Drive' if session.get('selected_google_drive_folder_id') else 'Local'}).")
    data, status_code = get_processed_image_data(new_index)
    return jsonify(data), status_code


if __name__ == '__main__':
    # Flask's logger is configured above. This basicConfig would be for other modules if needed.
    app.logger.info("Starting Flask application...")
    app.run(debug=True, host='0.0.0.0', port=8000)
