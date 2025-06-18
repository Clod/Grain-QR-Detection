#!/bin/bash

# This script automates the process of building a Docker image, pushing it to
# Google Container Registry (GCR), and deploying it as a service on Google Cloud Run.
#
# Prerequisites:
# 1. gcloud CLI installed and authenticated (run `gcloud auth login` first).
# 2. Docker installed and running.
# 3. The necessary GCP project and permissions are set up.

# --- Configuration ---
# Exit immediately if a command exits with a non-zero status. This ensures
# that the script will stop if any step fails.
set -e

# --- Variables ---
# You can change these variables to match your project's configuration.

# The Google Cloud Project ID.
PROJECT_ID="utn-granos"

# The name of the Docker image.
IMAGE_NAME="image-viewer"

# The tag for the Docker image (e.g., 'latest', 'v1.0').
IMAGE_TAG="latest"

# The full URI for the image in Google Container Registry.
GCR_IMAGE_URI="gcr.io/${PROJECT_ID}/${IMAGE_NAME}:${IMAGE_TAG}"

# The name for the Cloud Run service.
SERVICE_NAME="image-viewer-deploy"

# The GCP region where the Cloud Run service will be deployed.
REGION="us-central1"

# The secret to be mounted as an environment variable in the Cloud Run service.
# The format is: ENV_VAR_NAME=SECRET_NAME:SECRET_VERSION
SECRET_CONFIG="GOOGLE_OAUTH_CREDENTIALS=oauth-client:latest"

# The memory to allocate to the Cloud Run service.
MEMORY="2Gi"

# --- Script Execution ---

echo "--- Step 1: Configuring Docker Credentials ---"
# This command configures Docker to use the gcloud CLI as a credential helper.
# This allows Docker to authenticate with Google Container Registry (GCR)
# using your GCP credentials. This is often a one-time setup per machine,
# but including it ensures the script works in fresh environments.
gcloud auth configure-docker --quiet

echo ""
echo "--- Step 2: Building the Docker Image ---"
# Build the Docker image from the Dockerfile in the current directory.
# The --platform linux/amd64 flag ensures the image is built for the
# architecture used by Cloud Run, which is important when building on
# machines with different architectures (like Apple M1/M2 chips).
# The -t flag tags the image with a local name (e.g., image-viewer:latest).
docker build --platform linux/amd64 -t "${IMAGE_NAME}:${IMAGE_TAG}" .

echo ""
echo "--- Step 3: Tagging the Image for GCR ---"
# Before pushing to GCR, the local image must be tagged with the registry name.
# The format is [hostname]/[project-id]/[image-name]:[tag].
# Here, we tag the local image we just built with its full GCR path.
docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${GCR_IMAGE_URI}"

echo ""
echo "--- Step 4: Pushing the Image to GCR ---"
# Push the tagged image to Google Container Registry.
# Once pushed, the image is available for services like Cloud Run to use.
docker push "${GCR_IMAGE_URI}"

echo ""
echo "--- Step 5: Deploying to Google Cloud Run ---"
# Deploy the new image version to the Cloud Run service.
# This command will create a new service if it doesn't exist or update
# the existing one with a new revision using the specified parameters.
gcloud run deploy "${SERVICE_NAME}" \
  --image="${GCR_IMAGE_URI}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --memory="${MEMORY}" \
  --update-secrets="${SECRET_CONFIG}" \
  --platform=managed \
  --allow-unauthenticated

echo ""
echo "✅ Deployment complete!"
echo "Service URL: $(gcloud run services describe ${SERVICE_NAME} --platform=managed --region=${REGION} --project=${PROJECT_ID} --format='value(status.url)')"