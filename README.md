# Grain-QD-Detection

## Overview

This project is a web application designed for the detection and analysis of quality control markers in images, specifically focusing on ChArUco patterns and QR codes. It provides a user-friendly interface to process images either from a local source or directly from a user's Google Drive, making it a versatile tool for image-based quality inspection and data extraction.

The application analyzes images to identify these markers, overlays visual feedback onto the processed image, and extracts valuable data, such as the content of QR codes.

## Key Features

*   **Dual Marker Detection:** Capable of identifying both ChArUco board patterns and QR codes within the same image.
*   **Rich Data Extraction:** Decodes QR code data, including validation and parsing of JSON-formatted content, and reports the status of ChArUco detection.
*   **Visual Feedback:** Overlays colored polygons on the detected markers for clear visual confirmation and displays extracted information in a dedicated panel.
*   **Flexible Image Sourcing:** Supports processing images uploaded from a local computer or fetching them from a specified Google Drive folder.
*   **Web-Based UI:** A clean and interactive web interface built with the Flask framework, allowing for easy image loading, navigation, and data visualization.
*   **Google Integration:** Securely authenticates with Google via OAuth 2.0 to access user-specified image folders in Google Drive.
*   **Containerized Deployment:** Fully containerized using Docker and includes scripts to facilitate deployment to Google Cloud Platform (GCP), specifically Cloud Run.

## How It Works

The application provides two main workflows for image processing:

1.  **Local File Processing:** A user can upload one or more images from their computer. The application processes the first image and displays the original, the processed version with markers highlighted, and an information panel. Navigation buttons allow the user to cycle through the entire batch of uploaded images.

2.  **Google Drive Processing:** A user can log in with their Google account and provide a link to a folder in their Google Drive. The application then fetches the images from this folder and processes them sequentially, offering the same navigation and analysis experience as the local processing flow.

## Technical Details

*   **Backend:** The application is built on the **Flask** web framework. For production environments (like the Docker container), it is served by **Gunicorn** for robustness and scalability.
*   **Image Processing:** Core image analysis is performed using the **OpenCV** library, which provides the functions for ChArUco and QR code detection.
*   **Deployment:** The application is designed for cloud-native deployment. It includes a `Dockerfile` for building a container image and helper scripts to automate building, running locally, and deploying to **Google Cloud Run**.
*   **Configuration:** Google API credentials can be configured either through a `client_secret.json` file for local development or via environment variables for secure deployment in a cloud environment, with support for GCP Secret Manager.

## Session Management and Data Handling

The application relies on server-side sessions to manage user state and handle data securely and efficiently across multiple requests. This is crucial for both the Google Drive integration and for navigating through batches of images.

### Session Mechanism

The application utilizes Flask's built-in session management. These sessions are cookie-based but signed cryptographically. The session data itself is stored on the server, and only a secure identifier is sent to the client's browser in a cookie. This prevents client-side tampering and keeps sensitive information like API tokens from being exposed.

### Handling Google Authentication

The session is fundamental to the "Login with Google" feature. The authentication flow is as follows:

1.  **Initiation:** The user clicks the login button, and the Flask backend initiates the Google OAuth 2.0 flow, redirecting the user to Google.
2.  **Authorization:** The user is prompted by Google's consent screen to grant the application permission to view their Google Drive files.
3.  **Token Exchange:** Upon successful authorization, Google redirects the user back to the application with an authorization code. The backend securely exchanges this code for an **access token** and a **refresh token**.
4.  **Session Storage:** These critical tokens are stored in the user's server-side session. The access token is used to make authenticated API calls to Google Drive on the user's behalf.
5.  **Logout:** When the user logs out, the application explicitly clears these credentials from the session, effectively revoking its access and invalidating the user's authenticated state for the application.

### Handling Image Data and Navigation

The session is also used to maintain the context of the user's current task, such as processing a folder of images. This creates a stateful experience.

*   **Local Uploads:** When a user uploads multiple files, the application stores a list of temporary file paths in the session. An index, also stored in the session, keeps track of which image is currently being viewed.
*   **Google Drive Batches:** When a user connects a Google Drive folder, the application fetches a list of file IDs for all images in that folder. This list of IDs and the current navigation index are stored in the session.
*   **Navigation:** When the user clicks "Next" or "Previous", the backend uses the session's index to retrieve the next file path or ID from the list. It then fetches the corresponding image data (either from local storage or by making an API call to Google Drive), processes it, and returns the results. This makes the multi-image processing workflow seamless and stateful.

## Setup and Deployment

### Prerequisites

*   Docker installed on your local machine.
*   A Google Cloud Platform project with the **Secret Manager** and **Cloud Run** APIs enabled.
*   The `gcloud` CLI installed and configured for your GCP project.

### Google Credentials Setup

1.  In the Google Cloud Console, create OAuth 2.0 credentials for a **Web application**.
2.  Add the necessary authorized redirect URIs. For local development, this is typically `http://localhost:8080/oauth2callback`. For your deployed app, it will be `https://<your-cloud-run-url>/oauth2callback`.
3.  **For local development:** Download the credentials as `client_secret.json` and place it in the project root.
4.  **For cloud deployment:** It is highly recommended to store the entire content of the `client_secret.json` file in **GCP Secret Manager**. The application is configured to read these credentials from an environment variable that points to the secret's resource name.

### Local Development

The project includes a script to simplify local setup. This script builds the Docker image and runs it in a local container, exposing the application on port 8080.

```bash
# From the project root
sh ./scripts/build_and_run_locally.sh
```

You can then access the application at `http://localhost:8080`.

### Google Cloud Deployment

A deployment script automates the process of building the Docker image, pushing it to Google Artifact Registry, and deploying it as a new service on Cloud Run.

```bash
# Make sure to edit the script with your GCP project details first
sh ./scripts/upload_to_gcp.sh
```

This script ensures that the correct environment variables (like the one for Google credentials) are set for the Cloud Run service during deployment.