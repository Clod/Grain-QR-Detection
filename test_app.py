import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import json
from app import app  # Assuming your Flask app instance is named 'app' in 'app.py'
# Add any other necessary imports from your app or standard libraries

# Disable Flask logging for tests to keep output clean
import logging
app.logger.setLevel(logging.ERROR)

class AppTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key' # Consistent secret key for session
        # Use a temporary folder for uploads and drive downloads if needed for specific tests
        app.config['UPLOAD_FOLDER'] = 'test_uploads'
        app.config['DRIVE_TEMP_FOLDER'] = 'test_drive_temp'
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['DRIVE_TEMP_FOLDER'], exist_ok=True)
        self.client = app.test_client()
        # Clean session before each test
        with self.client.session_transaction() as sess:
            sess.clear()

    def tearDown(self):
        # Clean up test folders
        # Note: More robust cleanup might be needed if tests create nested dirs or many files
        for root, dirs, files in os.walk(app.config['UPLOAD_FOLDER'], topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass # Ignore if already removed or perm issues in CI perhaps
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
        try:
            os.rmdir(app.config['UPLOAD_FOLDER'])
        except OSError:
            pass

        for root, dirs, files in os.walk(app.config['DRIVE_TEMP_FOLDER'], topdown=False):
            for name in files:
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
        try:
            os.rmdir(app.config['DRIVE_TEMP_FOLDER'])
        except OSError:
            pass

    # --- Test Cases for Google Drive Integration ---

    @patch('app.Flow.from_client_secrets_file')
    def test_login_google_no_client_secret(self, mock_flow_from_secrets):
        mock_flow_from_secrets.side_effect = FileNotFoundError("client_secret.json not found")
        response = self.client.get('/login/google')
        # The app now renders an error template which should be a 200 OK response
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"OAuth2 client secrets file (client_secret.json) not found", response.data)

    @patch('app.Flow.from_client_secrets_file')
    def test_login_google_success_redirect(self, mock_flow_from_secrets):
        mock_flow_instance = MagicMock()
        mock_flow_instance.authorization_url.return_value = ('https://auth.example.com/auth', 'test_state')
        mock_flow_from_secrets.return_value = mock_flow_instance

        # Mock open for client_secret.json to prevent FileNotFoundError
        # This simulates the client_secret.json file being present and readable by Flow
        with patch('builtins.open', mock_open(read_data='{"web": {"client_id": "test_client_id", "client_secret": "test_client_secret", "auth_uri": "uri", "token_uri": "uri"}}')):
            response = self.client.get('/login/google')

        self.assertEqual(response.status_code, 302) # Redirect
        self.assertTrue(response.location.startswith('https://auth.example.com/auth'))
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('state'), 'test_state')

    def test_logout_google(self):
        with self.client.session_transaction() as sess:
            sess['google_credentials'] = {'token': 'dummy_token'}
            sess['selected_google_drive_folder_id'] = 'dummy_folder_id'
            sess['drive_image_files'] = [{'id': '1', 'name': 'a.jpg'}]
            sess['current_drive_image_index'] = 0
            sess['state'] = 'dummy_state'


        response = self.client.get('/logout/google', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login with Google to Use Drive Features', response.data)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('google_credentials'))
            self.assertIsNone(sess.get('selected_google_drive_folder_id'))
            self.assertIsNone(sess.get('drive_image_files'))
            self.assertIsNone(sess.get('current_drive_image_index'))
            self.assertIsNone(sess.get('state'))


    @patch('app.build') # Mocks googleapiclient.discovery.build
    @patch('app.google.oauth2.credentials.Credentials') # Mocks Credentials class
    def test_drive_folders_list_success(self, mock_credentials_class, mock_build):
        # Setup session with credentials
        with self.client.session_transaction() as sess:
            sess['google_credentials'] = {
                'token': 'fake_token', 'refresh_token': 'fake_refresh',
                'token_uri': 'uri', 'client_id': 'id',
                'client_secret': 'secret', 'scopes': ['scope1']
            }

        mock_creds_instance = MagicMock()
        mock_creds_instance.expired = False
        mock_credentials_class.return_value = mock_creds_instance

        mock_service = MagicMock()
        mock_files_list_result = MagicMock()
        mock_files_list_result.execute.return_value = {
            'files': [{'id': 'folder1', 'name': 'My Folder 1'}, {'id': 'folder2', 'name': 'My Folder 2'}]
        }
        # Correctly mock the chained calls: service.files().list().execute()
        mock_service.files.return_value.list.return_value = mock_files_list_result
        mock_build.return_value = mock_service

        response = self.client.get('/drive/folders')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My Folder 1', response.data)
        self.assertIn(b'folder1', response.data) # Check for ID as well
        self.assertIn(b'My Folder 2', response.data)
        self.assertIn(b'folder2', response.data)

    # Add more tests:
    # - test_drive_folders_list_api_error (e.g. HttpError)
    # - test_drive_select_folder_success (mocks API call for listing images in folder)
    # - test_process_image_route_drive_mode_success (mocks download, calls process_image, checks temp file deletion)
    # - test_process_image_route_drive_mode_download_error (e.g. 404 from Drive)
    # - test_upload_clears_drive_session

if __name__ == '__main__':
    unittest.main()
