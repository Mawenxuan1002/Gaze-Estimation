FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt cython

# Copy source code
COPY *.py ./
COPY rooms.json .

# Compile to .pyc (basic protection)
RUN python -m compileall -b . && find . -name "*.py" -delete && find . -name "*.pyc" -not -name "*.pyb" -delete

# Create directories
RUN mkdir -p /app/status /app/outputs

# Environment variables with defaults
ENV DEMO_PORT=8081
ENV ROOMS_CONFIG=/app/rooms.json
ENV API_URL=http://192.168.1.90:8081
ENV GAZE_USERNAME=admin
ENV GAZE_PASSWORD=admin123

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${DEMO_PORT}/health')" || exit 1

EXPOSE ${DEMO_PORT}

CMD ["python", "multi_stream.py"]
