from unittest.mock import patch, MagicMock, mock_open, call
import os
import shutil
import json
import io
from flask import session, url_for, Flask
from werkzeug.datastructures import FileStorage
import google.oauth2.credentials # Used for spec and storing original class
from googleapiclient.errors import HttpError as RealHttpError # For raising actual HttpError
import tempfile, unittest # unittest is needed for unittest.main
import cv2 as real_cv2 # For accessing cv2 constants

# Ensure the 'code' directory is in sys.path to import 'app'
import sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from app import app, cv_image_to_base64, process_image as app_process_image, extract_folder_id_from_url, get_processed_image_data, CLIENT_SECRETS_FILE, SCOPES, CHARUCO_CONFIG

# Dummy client_secret.json content
DUMMY_CLIENT_SECRET_CONTENT = {
    "web": {
        "client_id": "dummy_client_id", "project_id": "dummy_project_id",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "dummy_client_secret",
        "redirect_uris": ["http://localhost:8000/authorize/google"]
    }
}

# Mock external image processing libraries
mock_cv2_imread = MagicMock()
mock_cv2_cvtColor = MagicMock(side_effect=lambda img, code: img) # Pass through
mock_pil_image_fromarray = MagicMock()
mock_pil_image_instance = MagicMock()
mock_pil_image_fromarray.return_value = mock_pil_image_instance

# Store the original Credentials class before any patching
_OriginalGoogleCredentials = google.oauth2.credentials.Credentials

mock_detect_qrcodes = MagicMock(return_value=([], [], []))
mock_detect_charuco = MagicMock(return_value=(MagicMock(name="charuco_output_image"), None, None, None, None)) # Return a mock image for charuco_output

@patch('app.detect_and_draw_qrcodes', new=mock_detect_qrcodes)
@patch('app.detect_charuco_board', new=mock_detect_charuco)
@patch('cv2.imread', new=mock_cv2_imread)
@patch('cv2.cvtColor', new=mock_cv2_cvtColor)
@patch('PIL.Image.fromarray', new=mock_pil_image_fromarray)
class AppTestCase(unittest.TestCase): # Inherit from unittest.TestCase

    @classmethod
    def setUpClass(cls):
        cls.original_upload_folder = app.config['UPLOAD_FOLDER']
        cls.original_drive_temp_folder = app.config['DRIVE_TEMP_FOLDER']

        cls.test_upload_dir = tempfile.mkdtemp(prefix="flask_test_uploads_")
        cls.test_drive_temp_dir = tempfile.mkdtemp(prefix="flask_test_drive_")

        app.config['UPLOAD_FOLDER'] = cls.test_upload_dir
        app.config['DRIVE_TEMP_FOLDER'] = cls.test_drive_temp_dir
        
        # Ensure these directories exist for the app's startup logic if it runs again
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['DRIVE_TEMP_FOLDER'], exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_upload_dir)
        shutil.rmtree(cls.test_drive_temp_dir)
        app.config['UPLOAD_FOLDER'] = cls.original_upload_folder
        app.config['DRIVE_TEMP_FOLDER'] = cls.original_drive_temp_folder


    def setUp(self):
        self.app = app.test_client()
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # If using Flask-WTF
        app.config['SECRET_KEY'] = 'test_secret_key'
        app.config['SERVER_NAME'] = 'localhost.test' # For url_for external=True

        # Reset mocks that might have state
        mock_cv2_imread.reset_mock()
        mock_cv2_cvtColor.reset_mock()
        mock_pil_image_fromarray.reset_mock()
        mock_pil_image_instance.reset_mock()
        mock_pil_image_instance.save = MagicMock()
        mock_detect_qrcodes.reset_mock(return_value=([], [], []))
        # Ensure charuco_output is a mock object that can be assigned to processed_image
        mock_detect_charuco.reset_mock(return_value=(MagicMock(), None, None, None, None))

        # Mock cv2.imread to return a dummy numpy array-like object
        self.dummy_cv_image = MagicMock() # Represents a numpy array
        self.dummy_cv_image.copy = MagicMock(return_value=self.dummy_cv_image)
        mock_cv2_imread.return_value = self.dummy_cv_image

    def tearDown(self):
        # Clear session manually after each test
        with app.test_request_context('/'):
            session.clear()

    # Helper methods for Google Auth mocking
    def _set_google_session_credentials(self, token='test_token', refresh_token='test_refresh_token',
                                        token_uri='http://example.com/token', client_id='ci',
                                        client_secret='cs', scopes=None):
        """Sets google_credentials in the Flask session."""
        if scopes is None:
            scopes = SCOPES # Use the global SCOPES from app context
        
        session_data = {
            'token': token, 'refresh_token': refresh_token, 'token_uri': token_uri,
            'client_id': client_id, 'client_secret': client_secret, 'scopes': scopes
        }
        with self.app.session_transaction() as sess:
            sess['google_credentials'] = session_data
        return session_data

    def _create_mock_google_credentials(self, cred_dict, expired=False,
                                        mock_refresh_updates_token_to=None):
        """
        Creates a mock google.oauth2.credentials.Credentials object.
        If mock_refresh_updates_token_to is provided, .refresh() will update .token.
        Also provides a basic .to_json() method reflecting the mock's state.
        """
        creds_obj = MagicMock(spec=_OriginalGoogleCredentials)
        creds_obj.expired = expired
        creds_obj.token = str(cred_dict.get('token')) # Ensure string for json.dumps
        creds_obj.refresh_token = cred_dict.get('refresh_token')
        creds_obj.token_uri = cred_dict.get('token_uri')
        creds_obj.client_id = cred_dict.get('client_id')
        creds_obj.client_secret = cred_dict.get('client_secret')
        creds_obj.scopes = cred_dict.get('scopes')
        creds_obj.universe_domain = "googleapis.com"

        def _refresh_side_effect(request):
            if mock_refresh_updates_token_to:
                creds_obj.token = mock_refresh_updates_token_to
                # If other fields like token_uri need to change on refresh for to_json:
                # creds_obj.token_uri = "new_refreshed_uri_if_needed"

        def _to_json_side_effect():
            return json.dumps({
                'token': creds_obj.token,
                'refresh_token': creds_obj.refresh_token,
                'token_uri': creds_obj.token_uri,
                'client_id': creds_obj.client_id,
                'client_secret': creds_obj.client_secret,
                'scopes': creds_obj.scopes,
                'universe_domain': creds_obj.universe_domain,
            })

        creds_obj.refresh = MagicMock(side_effect=_refresh_side_effect)
        creds_obj.to_json = MagicMock(side_effect=_to_json_side_effect)
        return creds_obj

    def test_001_index_route(self):
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Image Viewer and Processor', response.data)

    def test_002_upload_files_no_files(self):
        response = self.app.post('/upload', data={})
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'No files uploaded')

    def test_003_upload_files_valid_image(self):
        test_filename = "test.jpg"
        dummy_file = FileStorage(
            stream=io.BytesIO(b"dummy image data"),
            filename=test_filename,
            content_type="image/jpeg"
        )
        response = self.app.post('/upload', data={'files[]': [dummy_file]}, content_type='multipart/form-data')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['image_count'], 1)
        self.assertEqual(data['images'], [test_filename])

        with self.app.session_transaction() as sess:
            self.assertEqual(sess['image_paths'], [test_filename])
            self.assertEqual(sess['current_index'], 0)
            self.assertNotIn('selected_google_drive_folder_id', sess) # Check Drive session cleared
        self.assertTrue(os.path.exists(os.path.join(self.test_upload_dir, test_filename)))

    def test_004_upload_files_unsupported_extension(self):
        dummy_file = FileStorage(io.BytesIO(b"dummy data"), "test.txt", "text/plain")
        response = self.app.post('/upload', data={'files[]': [dummy_file]})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['image_count'], 0)
        with self.app.session_transaction() as sess:
            self.assertEqual(sess['current_index'], -1)

    @patch('app.process_image') # Mock the internal process_image function
    def test_005_process_image_route_local_valid_index(self, mock_process_image_func):
        mock_process_image_func.return_value = {
            'original_image': 'data:orig_base64',
            'processed_image': 'data:proc_base64',
            'charuco_detected': True,
            'qr_codes': ['qr1'],
            'qr_codes_json': [{'data': 'qr1_json'}]
        }
        # Simulate prior upload
        with self.app.session_transaction() as sess:
            sess['image_paths'] = ['test.jpg']
            sess['current_index'] = 0
        
        # Create dummy file in upload folder
        dummy_image_path = os.path.join(self.test_upload_dir, 'test.jpg')
        with open(dummy_image_path, 'w') as f: f.write('dummy')

        response = self.app.get('/process/0')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['original_image'], 'data:orig_base64')
        self.assertTrue(data['charuco_detected'])
        self.assertEqual(data['current_index'], 0)
        self.assertEqual(data['filename'], 'test.jpg')
        mock_process_image_func.assert_called_once_with(os.path.join(self.test_upload_dir, 'test.jpg'))

    def test_006_process_image_route_local_invalid_index(self):
        with self.app.session_transaction() as sess:
            sess['image_paths'] = ['test.jpg']
            sess['current_index'] = 0
        response = self.app.get('/process/1')
        self.assertEqual(response.status_code, 400)

    @patch('app.get_processed_image_data') # Mock the helper
    def test_007_navigate_local(self, mock_get_processed_image_data):
        mock_get_processed_image_data.return_value = ({'current_index': 1, 'filename': 'img2.jpg'}, 200)
        with self.app.session_transaction() as sess:
            sess['image_paths'] = ['img1.jpg', 'img2.jpg', 'img3.jpg']
            sess['current_index'] = 0

        response = self.app.get('/navigate/next')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['current_index'], 1)
        mock_get_processed_image_data.assert_called_with(1) # new_index for 'next' from 0 is 1

        # Configure mock for the 'prev' navigation call
        mock_get_processed_image_data.return_value = ({'current_index': 0, 'filename': 'img1.jpg'}, 200)
        with self.app.session_transaction() as sess: # Reset current_index for prev test
            sess['current_index'] = 1
        response = self.app.get('/navigate/prev') # Call the route directly
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['current_index'], 0)
        mock_get_processed_image_data.assert_called_with(0) # new_index for 'prev' from 1 is 0

    @patch('google_auth_oauthlib.flow.Flow.from_client_secrets_file')
    def test_008_login_google_route(self, mock_flow_from_secrets):
        mock_flow_instance = MagicMock()
        mock_flow_instance.authorization_url.return_value = ('https://auth_url', 'test_state')
        mock_flow_from_secrets.return_value = mock_flow_instance

        response = self.app.get('/login/google')

        self.assertEqual(response.status_code, 302) # Redirect
        self.assertEqual(response.location, 'https://auth_url')
        with self.app.application.app_context(): # Context for url_for in assertion
            mock_flow_from_secrets.assert_called_once_with(
                CLIENT_SECRETS_FILE,
                scopes=SCOPES,
                redirect_uri=url_for('authorize_google', _external=True)
            )
        mock_flow_instance.authorization_url.assert_called_once_with(
            access_type='offline',
            include_granted_scopes='true',
            prompt='select_account'
        )
        with self.app.session_transaction() as sess:
            self.assertEqual(sess['state'], 'test_state')

    @patch('google_auth_oauthlib.flow.Flow.from_client_secrets_file', side_effect=FileNotFoundError)
    def test_009_login_google_no_client_secret_file(self, mock_flow_from_secrets_error):
        response = self.app.get('/login/google')
        self.assertEqual(response.status_code, 500) # Should return 500 for FileNotFoundError
        # The response data will be the rendered error.html template
        self.assertIn(b"OAuth2 client secrets file (client_secret.json) not found", response.data)

    @patch('google_auth_oauthlib.flow.Flow.from_client_secrets_file')
    def test_010_authorize_google_route_success(self, mock_flow_from_secrets):
        mock_flow_instance = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.token = 'test_token'
        mock_credentials.refresh_token = 'test_refresh_token'
        mock_credentials.token_uri = 'uri'
        mock_credentials.client_id = 'id'
        mock_credentials.client_secret = 'secret'
        mock_credentials.scopes = SCOPES # Ensure scopes is JSON serializable
        mock_credentials.universe_domain = "googleapis.com" # Add universe_domain
        mock_flow_instance.credentials = mock_credentials
        mock_flow_from_secrets.return_value = mock_flow_instance

        with self.app.session_transaction() as sess:
            sess['state'] = 'test_state_val'

        response = self.app.get('/authorize/google?state=test_state_val&code=auth_code', base_url="http://localhost.test") # Use test server name

        self.assertEqual(response.status_code, 302) # Redirect to index
        with self.app.application.app_context(): # For url_for in assertion
            self.assertEqual(response.location, url_for('index', _external=False))
        mock_flow_instance.fetch_token.assert_called_once()
        with self.app.session_transaction() as sess:
            self.assertIn('google_credentials', sess)
            self.assertEqual(sess['google_credentials']['token'], 'test_token')

    def test_011_authorize_google_state_mismatch(self):
        with self.app.session_transaction() as sess:
            sess['state'] = 'original_state'
        response = self.app.get('/authorize/google?state=mismatched_state&code=auth_code')
        self.assertEqual(response.status_code, 400)

    def test_012_logout_google_route(self):
        with self.app.session_transaction() as sess:
            sess['google_credentials'] = {'token': 'xyz'}
            sess['state'] = 'abc'
            sess['selected_google_drive_folder_id'] = 'folder123'

        response = self.app.get('/logout/google', follow_redirects=True)
        
        self.assertEqual(response.status_code, 200) # After redirect
        self.assertIn(b'You have been logged out from Google.', response.data)
        with self.app.session_transaction() as sess:
            self.assertNotIn('google_credentials', sess)
            self.assertNotIn('state', sess)
            self.assertNotIn('selected_google_drive_folder_id', sess)

    def test_013_drive_folders_not_logged_in(self):
        with self.app.application.app_context(): # For url_for in redirect and flash
            expected_url = '/login/google' # Expect relative path as generated by redirect(url_for(...))
            response = self.app.get('/drive/folders') # follow_redirects=False is default
            self.assertEqual(response.status_code, 302) # Check for redirect status
            self.assertEqual(response.location, expected_url) # Check redirect location
            with self.app.session_transaction() as sess:
                self.assertTrue(any('Please login with Google first.' in message[1] for message in sess.get('_flashes', [])))

    @patch('googleapiclient.discovery.build')
    @patch('app.google.oauth2.credentials.Credentials') # Target where Credentials is used in app.py
    def test_014_drive_folders_logged_in_success(self, MockAppCredentials, mock_build_aliased_in_test_unused):
        creds_data = {
            'token': 't', 'refresh_token': 'rt', 'token_uri': 'tu',
            'client_id': 'ci', 'client_secret': 'cs', 'scopes': SCOPES
        }
        self._set_google_session_credentials(**creds_data)
        mock_creds_instance = self._create_mock_google_credentials(creds_data, expired=False)
        MockAppCredentials.return_value = mock_creds_instance
        
        # Patch 'app.build' as that's where 'build' is resolved in app.py
        with patch('app.build') as mock_app_build:
            mock_service = mock_app_build.return_value
            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': [{'id': 'folder1', 'name': 'My Folder'}]
            }

            response = self.app.get('/drive/folders')
            
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'My Folder', response.data)
            MockAppCredentials.assert_called_once_with(**creds_data)
            mock_app_build.assert_called_once_with('drive', 'v3', credentials=mock_creds_instance)

    @patch('googleapiclient.discovery.build')
    @patch('app.google.oauth2.credentials.Credentials') # Target where Credentials is used in app.py
    def test_015_drive_select_folder_success(self, MockAppCredentials, mock_build_aliased_in_test_unused):
        # mock_build_aliased_in_test_unused is not used directly because we patch app.build inside

        creds_data = {
            'token': 't', 'refresh_token': 'rt', 'token_uri': 'tu',
            'client_id': 'ci', 'client_secret': 'cs', 'scopes': SCOPES
        }
        self._set_google_session_credentials(**creds_data)
        mock_creds_instance = self._create_mock_google_credentials(creds_data, expired=False)
        MockAppCredentials.return_value = mock_creds_instance
        
        with patch('app.build') as mock_app_build:
            mock_service = mock_app_build.return_value
            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': [{'id': 'img1', 'name': 'Image One.jpg'}]
            }
            with self.app.session_transaction() as sess: # For checking other session vars
                sess['image_paths'] = ['local.jpg'] 

            # follow_redirects=False, as the final redirect is internal to index.html
            # The RuntimeError was due to 403 -> login -> external redirect.
            response = self.app.get('/drive/select_folder/folder123/TestFolder', follow_redirects=True)

            self.assertEqual(response.status_code, 200) # Should redirect to index, then render index
            self.assertIn(b'Selected folder &#39;TestFolder&#39;. Found 1 images.', response.data) # Flash message on index (HTML escaped quote)
            with self.app.session_transaction() as sess:
                self.assertEqual(sess['selected_google_drive_folder_id'], 'folder123')
                self.assertEqual(sess['selected_google_drive_folder_name'], 'TestFolder')
                self.assertEqual(len(sess['drive_image_files']), 1)
                self.assertEqual(sess['drive_image_files'][0]['name'], 'Image One.jpg')
                self.assertEqual(sess['current_drive_image_index'], 0)
                self.assertNotIn('image_paths', sess) # Local paths cleared
            MockAppCredentials.assert_called_once_with(**creds_data)

    def test_016_extract_folder_id_from_url(self):
        # Use IDs that are more realistic in length (typically 28 or 33 chars for folders)
        long_id_1 = "1234567890123456789012345" # 25 chars
        long_id_2 = "abcdefghijklmnopqrstuvwxy" # 25 chars
        self.assertEqual(extract_folder_id_from_url(f"https://drive.google.com/drive/folders/{long_id_1}"), long_id_1)
        self.assertEqual(extract_folder_id_from_url(f"https://drive.google.com/drive/u/0/folders/{long_id_2}"), long_id_2)
        self.assertEqual(extract_folder_id_from_url(f"https://drive.google.com/open?id={long_id_1}"), long_id_1)
        self.assertEqual(extract_folder_id_from_url(f"https://drive.google.com/folderview?id={long_id_2}&usp=sharing"), long_id_2)
        self.assertIsNone(extract_folder_id_from_url("invalid_url"))
        self.assertIsNone(extract_folder_id_from_url(None))

    @patch('googleapiclient.discovery.build')
    @patch('app.google.oauth2.credentials.Credentials') # Target where Credentials is used in app.py
    def test_017_process_drive_link_success(self, MockAppCredentials, mock_build_aliased_in_test_unused):
        creds_data = {
            'token': 't', 'refresh_token': 'rt', 'token_uri': 'tu',
            'client_id': 'ci', 'client_secret': 'cs', 'scopes': SCOPES
        }
        self._set_google_session_credentials(**creds_data)
        mock_creds_instance = self._create_mock_google_credentials(creds_data, expired=False)
        MockAppCredentials.return_value = mock_creds_instance

        with patch('app.build') as mock_app_build:
            mock_service = mock_app_build.return_value
            test_folder_id = "a_valid_looking_folder_id_25_chars"
            mock_service.files.return_value.get.return_value.execute.return_value = {'id': test_folder_id, 'name': 'Linked Folder'}
            mock_service.files.return_value.list.return_value.execute.return_value = {
                'files': [{'id': 'img_drive_1', 'name': 'Drive Image 1.png'}]
            }
            
            drive_link_data = {'drive_link': f'https://drive.google.com/drive/folders/{test_folder_id}'}
            response = self.app.post('/process_drive_link', json=drive_link_data)

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            self.assertEqual(data['image_count'], 1)
            self.assertEqual(data['folder_name'], 'Linked Folder')

            with self.app.session_transaction() as sess:
                self.assertEqual(sess['selected_google_drive_folder_id'], test_folder_id)
                self.assertEqual(sess['selected_google_drive_folder_name'], 'Linked Folder')
                self.assertEqual(len(sess['drive_image_files']), 1)
                self.assertEqual(sess['current_drive_image_index'], 0)
            MockAppCredentials.assert_called_once_with(**creds_data)

    def test_018_process_drive_link_not_logged_in(self):
        drive_link_data = {'drive_link': 'https://drive.google.com/drive/folders/folder_xyz'}
        response = self.app.post('/process_drive_link', json=drive_link_data)
        self.assertEqual(response.status_code, 401) # Unauthorized
        data = json.loads(response.data)
        self.assertIn('Not logged into Google', data['error'])

    def test_019_cv_image_to_base64_none_input(self):
        self.assertIsNone(cv_image_to_base64(None))

    def test_020_cv_image_to_base64_valid_input(self):
        # Mocks are already set up at class level for cv2 and PIL
        dummy_image_array = MagicMock() # Represents a numpy array
        
        result = cv_image_to_base64(dummy_image_array)

        mock_cv2_cvtColor.assert_called_once_with(dummy_image_array, real_cv2.COLOR_BGR2RGB)
        mock_pil_image_fromarray.assert_called_once_with(dummy_image_array) # Assuming cvtColor returns its input
        mock_pil_image_instance.save.assert_called_once()
        args, kwargs = mock_pil_image_instance.save.call_args
        self.assertIsInstance(args[0], io.BytesIO) # Check buffer type
        self.assertEqual(kwargs['format'], 'JPEG')
        self.assertEqual(kwargs['quality'], 85)
        self.assertTrue(result.startswith('data:image/jpeg;base64,'))

    @patch('app.cv_image_to_base64', return_value='data:base64_dummy_image_content')
    def test_021_process_image_function_basic_flow(self, mock_cv_to_b64):
        # Mocks for cv2.imread, detect_qrcodes, detect_charuco are at class level
        dummy_image_path = "dummy/path/to/image.jpg"
        # self.dummy_cv_image is already set as return_value for mock_cv2_imread in setUp
        
        # Ensure detection functions return expected structure
        mock_detect_qrcodes.return_value = ([self.dummy_cv_image], ["qr_text"], [{"data":"json_qr"}])
        # Ensure charuco_ids ("ids") is a list for len() check in app.py
        mock_detect_charuco.return_value = (self.dummy_cv_image, "corners", ["id1"], "mcorners", "mids")

        result = app_process_image(dummy_image_path)

        mock_cv2_imread.assert_called_once_with(dummy_image_path)
        self.dummy_cv_image.copy.assert_called_once() # Check that a copy is made
        
        # cv_image_to_base64 should be called for original and processed
        self.assertEqual(mock_cv_to_b64.call_count, 2)
        
        mock_detect_qrcodes.assert_called_once_with(self.dummy_cv_image)
        # The first argument to detect_charuco_board is the (potentially QR-modified) image
        mock_detect_charuco.assert_called_once_with(
            self.dummy_cv_image, # This would be qr_images[0]
            CHARUCO_CONFIG['SQUARES_X'], CHARUCO_CONFIG['SQUARES_Y'],
            CHARUCO_CONFIG['SQUARE_LENGTH_MM'], CHARUCO_CONFIG['MARKER_LENGTH_MM'],
            CHARUCO_CONFIG['DICTIONARY_NAME'], display=False
        )
        self.assertEqual(result['original_image'], 'data:base64_dummy_image_content')
        self.assertEqual(result['processed_image'], 'data:base64_dummy_image_content')
        self.assertTrue(result['charuco_detected']) # Because charuco_ids ("ids") is not None and not empty
        self.assertEqual(result['qr_codes'], ["qr_text"])
        self.assertEqual(result['qr_codes_json'], [{"data":"json_qr"}])

    def test_022_process_image_function_load_fail(self):
        mock_cv2_imread.return_value = None # Simulate imread failure
        result = app_process_image("bad/path.jpg")
        self.assertIsNone(result['original_image'])
        self.assertIsNone(result['processed_image']) # This will also be None as processing starts with original
        self.assertFalse(result['charuco_detected'])

    @patch('app.process_image') # Mock the actual image processing
    @patch('app.googleapiclient.http.MediaIoBaseDownload') # Target where MediaIoBaseDownload is used in app.py
    @patch('app.build') # Target where build is used
    @patch('app.google.oauth2.credentials.Credentials') # Target where Credentials is used
    @patch('app.io.FileIO') # Target where FileIO is used
    def test_023_get_processed_image_data_drive_success(self, MockAppFileIO, MockAppCredentials, mock_app_build, MockAppMediaDownload, mock_app_process_image_func):
        # Setup session for Drive mode
        creds_data = {
            'token': 'test_token', 'refresh_token': 'test_refresh_token', 
            'token_uri': 'http://example.com/token', 'client_id': 'ci', 
            'client_secret': 'cs', 'scopes': SCOPES
        }
        session_creds_data = self._set_google_session_credentials(**creds_data)
        mock_creds_instance = self._create_mock_google_credentials(session_creds_data, expired=False)
        MockAppCredentials.return_value = mock_creds_instance

        drive_files = [{'id': 'file_id_123', 'name': 'drive_image.jpg'}]
        with self.app.session_transaction() as sess:
            sess['selected_google_drive_folder_id'] = 'folder_abc'
            sess['drive_image_files'] = drive_files

        # Mock Drive service and download
        mock_service = mock_app_build.return_value
        # mock_service.files().get_media(fileId=file_id)
        mock_drive_request = MagicMock()
        mock_service.files.return_value.get_media.return_value = mock_drive_request
        
        mock_downloader = MockAppMediaDownload.return_value
        mock_downloader.next_chunk.side_effect = [(MagicMock(progress=lambda: 1.0), True)] # Simulate download completion

        # Mock process_image result
        mock_app_process_image_func.return_value = {'data': 'processed'}

        # Mock os.path.exists and os.remove
        with patch('os.path.exists', return_value=True), \
             patch('os.remove') as mock_os_remove:
            
            # Call the route, not the helper directly
            response = self.app.get('/process/0')
            result_data = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result_data['data'], 'processed') # From mock_app_process_image_func
        self.assertEqual(result_data['current_index'], 0)
        self.assertEqual(result_data['filename'], 'drive_image.jpg')
        self.assertEqual(result_data['source'], 'drive')

        MockAppCredentials.assert_called_once_with(**session_creds_data)
        mock_app_build.assert_called_once_with('drive', 'v3', credentials=mock_creds_instance)
        mock_service.files.return_value.get_media.assert_called_once_with(fileId='file_id_123')
        
        # Check that FileIO was called to write the downloaded file
        expected_temp_path = os.path.join(self.test_drive_temp_dir, 'drive_image.jpg')
        MockAppFileIO.assert_called_once_with(expected_temp_path, 'wb')
        MockAppMediaDownload.assert_called_once() # Check downloader was created
        
        mock_app_process_image_func.assert_called_once_with(expected_temp_path)
        mock_os_remove.assert_called_once_with(expected_temp_path) # Check temp file deleted

        with self.app.session_transaction() as sess:
            self.assertEqual(sess['current_drive_image_index'], 0)

    def test_024_get_processed_image_data_local_invalid_index(self):
        with self.app.session_transaction() as sess:
            sess['image_paths'] = ['local1.jpg']
        
        # Call the route, not the helper directly
        response = self.app.get('/process/5')
        result_data = json.loads(response.data)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Invalid local image index', result_data['error'])

    # REMOVE: @patch('googleapiclient.errors.HttpError')
    @patch('app.googleapiclient.http.MediaIoBaseDownload') # Added patch for MediaIoBaseDownload
    @patch('app.build') # Target where build is used in app.py
    @patch('app.google.oauth2.credentials.Credentials') # Target where Credentials is used in app.py
    def test_025_get_processed_image_data_drive_http_error_404(self, MockAppCredentials, mock_app_build, MockAppMediaDownload): # MockAppMediaDownload is now a param

        creds_data = {
            'token': 'test_token', 'refresh_token': 'test_refresh_token',
            'token_uri': 'http://example.com/token', 'client_id': 'ci',
            'client_secret': 'cs', 'scopes': SCOPES
        }
        session_creds_data = self._set_google_session_credentials(**creds_data)
        mock_creds_instance = self._create_mock_google_credentials(session_creds_data, expired=False) # Keep creds mock for build call assertion
        MockAppCredentials.return_value = mock_creds_instance

        drive_files = [{'id': 'file_id_404', 'name': 'notfound.jpg'}]
        with self.app.session_transaction() as sess:
            sess['selected_google_drive_folder_id'] = 'folder_abc'
            sess['drive_image_files'] = drive_files
        mock_service = mock_app_build.return_value

        # Simulate HttpError from service.files().get_media()
        # The HttpError needs a `resp` attribute which is a mock response object
        mock_resp = MagicMock()
        mock_resp.status = 404
        mock_resp.reason = "Not Found"
        # Create a real HttpError instance
        real_http_error_instance = RealHttpError(mock_resp, b'{"error": {"message": "File not found from API"}}', uri='some_uri')

        # Mock the downloader and its next_chunk method to raise the HttpError
        mock_drive_request = MagicMock()
        mock_service.files.return_value.get_media.return_value = mock_drive_request
        
        # MockAppMediaDownload is now the mock class from the decorator
        mock_downloader = MockAppMediaDownload.return_value
        mock_downloader.next_chunk.side_effect = real_http_error_instance # This will RAISE the error

        # Call the route, not the helper directly
        response = self.app.get('/process/0')
        result_data = json.loads(response.data)
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found on Google Drive (404)", result_data['error'])
        self.assertEqual(result_data['filename'], 'notfound.jpg')
        self.assertTrue(result_data['is_api_error'])
        # Check that build was called with the credentials, even though download failed
        mock_app_build.assert_called_once_with('drive', 'v3', credentials=mock_creds_instance)

    def test_026_413_error_handler(self):
        # This test is a bit indirect for the handler itself.
        # We can check if the handler is registered.
        from werkzeug.exceptions import RequestEntityTooLarge
        
        self.assertIn(None, app.error_handler_spec) # Check for default error handlers
        self.assertIn(413, app.error_handler_spec[None]) # Check for 413 specific handlers
        # The handler is registered for the specific exception class RequestEntityTooLarge
        handler_func = app.error_handler_spec[None][413].get(RequestEntityTooLarge)

        self.assertIsNotNone(handler_func, "413 error handler not found for default exception type.")
        
        # Directly call the handler function with a mock error
        mock_error_413 = MagicMock(description="Payload too large")
        with app.test_request_context('/', headers={'Content-Length': '100000000'}): # Large content length
            app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
            response, status_code = handler_func(mock_error_413)
        
        self.assertEqual(status_code, 413)
        data = json.loads(response.get_data(as_text=True))
        self.assertEqual(data['error'], 'Payload too large')
        self.assertIn("exceeds the maximum allowed size", data['message'])

    @patch('app.google.auth.transport.requests.Request') # Target where Request is used
    @patch('app.google.oauth2.credentials.Credentials') # Target where Credentials is used
    def test_027_credential_refresh_logic_in_drive_folders(self, MockAppCredentials, MockAppGoogleRequest):
        # Test token refresh path in /drive/folders
        initial_creds_data = {
            'token': 'old_token', 'refresh_token': 'valid_refresh_token',
            'token_uri': 'http://example.com/token', 'client_id': 'ci',
            'client_secret': 'cs', 'scopes': SCOPES
        }
        self._set_google_session_credentials(**initial_creds_data)

        mock_creds_instance = self._create_mock_google_credentials(
            initial_creds_data,
            expired=True,
            mock_refresh_updates_token_to='new_refreshed_token'
        )
        MockAppCredentials.return_value = mock_creds_instance
        
        mock_google_request_instance = MockAppGoogleRequest.return_value # For assert_called_with

        with patch('app.build') as mock_app_build: # Patch where 'build' is used in app.py
            mock_drive_service = mock_app_build.return_value
            mock_drive_service.files.return_value.list.return_value.execute.return_value = {'files': []} # Simulate successful call after refresh
            
            response = self.app.get('/drive/folders')

            self.assertEqual(response.status_code, 200)
            MockAppCredentials.assert_called_once_with(**initial_creds_data)
            mock_creds_instance.refresh.assert_called_once_with(mock_google_request_instance) # Refresh was called
            # The app does not call to_json() in this path, it manually reconstructs the session dict.
            # So, mock_creds_instance.to_json.assert_called_once() would fail.
        
        with self.app.session_transaction() as sess:
            self.assertEqual(sess['google_credentials']['token'], 'new_refreshed_token') # Token updated in session

    def test_028_index_route_drive_mode_no_images(self):
        with self.app.session_transaction() as sess:
            sess['selected_google_drive_folder_id'] = "drive_folder_123"
            sess['drive_image_files'] = [] # No images
            sess['current_drive_image_index'] = -1

        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"var isDriveModeActive = true;", response.data)
        self.assertIn(b"var initialDriveImageCount = 0;", response.data)
        # Check that current_drive_image_index remains -1 or is set appropriately
        with self.app.session_transaction() as sess:
            self.assertEqual(sess.get('current_drive_image_index'), -1)

    def test_029_index_route_drive_mode_with_images_bad_index_reset(self):
        with self.app.session_transaction() as sess:
            sess['selected_google_drive_folder_id'] = "drive_folder_123"
            sess['drive_image_files'] = [{'id': '1', 'name': 'a.jpg'}] 
            sess['current_drive_image_index'] = 5 # Out of bounds

        response = self.app.get('/') # This should trigger the index reset logic
        self.assertEqual(response.status_code, 200)
        with self.app.session_transaction() as sess:
            self.assertEqual(sess.get('current_drive_image_index'), 0) # Reset to 0

if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)