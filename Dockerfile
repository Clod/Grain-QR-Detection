# Stage 1 – application image
FROM python:3.11-slim-bookworm

# Update package index, upgrade existing packages, install dependencies, and clean up
# Added libsm6, libxext6, libxrender1 as potential missing dependencies for opencv-python-headless
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libzbar0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Prevent Python byte-code files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Create work directory
WORKDIR /app

# Create a non-root user and group
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser

# Install build dependencies first to leverage cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download QReader models (as root) to prevent permission issues when run as appuser.
# QReader's QRDetector downloads models to its site-packages subdirectory.
RUN python -c "from qreader import QReader; print('Attempting to instantiate QReader to pre-download models...'); QReader(); print('QReader instantiated, models should be downloaded.')"

# Copy source code last (so code changes don’t bust earlier layers)
COPY static /app/static
COPY templates /app/templates
COPY detect_and_draw_qr.py /app/detect_and_draw_qr.py
COPY charuco_detector.py /app/charuco_detector.py
COPY app.py /app/app.py

# Diagnostic step: try to import the module and then the function during build
# This will show a detailed traceback if the import fails.
RUN python -c "import detect_and_draw_qr; print('Successfully imported detect_and_draw_qr module')"
RUN python -c "from detect_and_draw_qr import detect_and_draw_qrcodes; print('Successfully imported detect_and_draw_qrcodes function')"

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appgroup /app

# Set environment variable for Ultralytics config to be in user's home.
# This should allow Ultralytics (a dependency of qreader) to write its config without permission errors.
ENV YOLO_CONFIG_DIR=/home/appuser/.config/Ultralytics

# Tell Flask to listen on all interfaces
ENV FLASK_RUN_HOST=0.0.0.0

# Expose the port your app listens on
EXPOSE 8080

# Switch to the non-root user
USER appuser

# Start the dev server (swap for Gunicorn in prod)
# CMD ["flask", "run", "--port", "8000"]
CMD ["python", "app.py"]