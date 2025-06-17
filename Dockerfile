# Stage 1 – application image
FROM python:3.11-slim-bookworm

# Update Python package index, upgrade installed packages, and install OpenCV & GLib dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y libgl1-mesa-glx libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# Prevent Python byte-code files and enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Create work directory
WORKDIR /app

# Install build dependencies first to leverage cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code last (so code changes don’t bust earlier layers)
COPY static /app/static
COPY templates /app/templates
COPY app.py /app/app.py
COPY charuco_detector.py /app/charuco_detector.py
COPY detect_and_draw_qr.py /app/detect_and_draw_qr.py 

# Tell Flask to listen on all interfaces
ENV FLASK_RUN_HOST=0.0.0.0

# Expose the port your app listens on
EXPOSE 8000

# Start the dev server (swap for Gunicorn in prod)
CMD ["flask", "run", "--port", "8000"]
