#!/bin/bash

# This script builds the Docker image, fetches a secret from Google Secret Manager,
# and then runs the image locally with the secret as an environment variable.

echo "Before running this script, ensure you have the following prerequisites:"
echo "- Docker installed and running"
echo "- Google Cloud SDK installed and authenticated (gcloud auth login)"
echo "- Access to the Google Cloud project and Secret Manager"
echo
echo "Starting the build and run process..."

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
# Docker image details
IMAGE_NAME="image-viewer-mac"
TAG="latest"
FULL_IMAGE_NAME="${IMAGE_NAME}:${TAG}"

# Google Cloud Secret Manager details
# Replace with your actual project ID and secret name/version
PROJECT_ID="utn-granos"
SECRET_NAME="oauth-client"
SECRET_VERSION="latest" # or a specific version number

# Docker Volume details
# This is the named volume that holds the images for the "Select Server Images" feature.
# Ensure this volume exists and is populated with your images.
VOLUME_NAME="code_shared_ftp_data"
# --- End Configuration ---

# --- Build Step ---
echo "Building Docker image: ${FULL_IMAGE_NAME}..."
docker build -t "${FULL_IMAGE_NAME}" .

# --- Secret Fetching Step ---
echo "Fetching secret '$SECRET_NAME' from Google Secret Manager..."
# Ensure the gcloud user is authenticated (gcloud auth login) and has the
# 'Secret Manager Secret Accessor' role on the secret.
SECRET_CONTENT=$(gcloud secrets versions access "$SECRET_VERSION" --secret="$SECRET_NAME" --project="$PROJECT_ID")

# Check if fetching was successful
if [ -z "$SECRET_CONTENT" ]; then
  echo "Error: Failed to fetch secret '$SECRET_NAME' from Google Secret Manager." >&2
  echo "Please ensure you are authenticated with gcloud ('gcloud auth login') and have the correct permissions." >&2
  exit 1
fi
echo "Secret fetched successfully."

# --- Run Step ---
echo "Running Docker container..."
echo "Application will be available at http://localhost:8080"
echo "Press Ctrl+C to stop the container."
# Run the Docker container, passing the fetched secret as an environment variable.
docker run \
  --rm \
  -p 8080:8080 \
  -e GOOGLE_OAUTH_CREDENTIALS="$SECRET_CONTENT" \
  -v "${VOLUME_NAME}:/app/shared_data" \
  "${FULL_IMAGE_NAME}"