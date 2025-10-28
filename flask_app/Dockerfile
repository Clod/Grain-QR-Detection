# Stage 1: Builder
# This stage installs Python dependencies into a virtual environment
# and pre-downloads necessary models to keep the final image clean.
FROM python:3.11-slim-bookworm AS builder

# Prevent Python from writing .pyc files and buffer logs
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Install OS dependencies required by opencv-python and pyzbar (dependencies of qreader)
# before installing Python packages. This is needed for the model pre-download step.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libzbar0 \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install dependencies first to leverage Docker's layer caching.
WORKDIR /app
COPY requirements.txt .

# Create a virtual environment and install packages into it.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download QReader models. They will be stored within the venv.
RUN python -c "from qreader import QReader; print('Pre-downloading QReader models...'); QReader(); print('Model download complete.')"


# Stage 2: Final Application Image
# This stage builds the final image using the artifacts from the builder stage.
FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and buffer logs
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Install only essential runtime OS dependencies.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libzbar0 \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for enhanced security.
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid 1001 --shell /bin/bash --create-home appuser

# Copy the virtual environment with all dependencies from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Set the PATH to include the virtual environment's binaries.
ENV PATH="/opt/venv/bin:$PATH"

# Create and set the working directory.
WORKDIR /app
# Copy application code from the build context. Assumes a .dockerignore file is present.
# Create directories that the appuser will need to write to at runtime
RUN mkdir -p /app/uploads /app/drive_temp_downloads /app/shared_data && \
    chown -R appuser:appgroup /app/uploads /app/drive_temp_downloads /app/shared_data

COPY --chown=appuser:appgroup . .

# Set environment variable for Ultralytics config to be in user's home.
ENV YOLO_CONFIG_DIR=/home/appuser/.config/Ultralytics

EXPOSE 8080

# Switch to the non-root user
USER appuser

# Use Gunicorn for production.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--worker-class", "gthread", "--timeout", "300", "app:app"]