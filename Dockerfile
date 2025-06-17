# Stage 1 – application image
FROM python:3.11-slim-bookworm

# Update package index, upgrade existing packages, install dependencies, and clean up
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends libgl1-mesa-glx libglib2.0-0 && \
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

# Copy source code last (so code changes don’t bust earlier layers)
COPY static /app/static
COPY templates /app/templates
COPY app.py /app/app.py

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appgroup /app

# Tell Flask to listen on all interfaces
ENV FLASK_RUN_HOST=0.0.0.0

# Expose the port your app listens on
EXPOSE 8000

# Switch to the non-root user
USER appuser

# Start the dev server (swap for Gunicorn in prod)
CMD ["flask", "run", "--port", "8000"]
