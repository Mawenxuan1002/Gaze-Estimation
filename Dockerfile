FROM docker.m.daocloud.io/library/python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libegl1 \
    libgles2 \
    libegl-mesa0 \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY gaze_tracker ./gaze_tracker
COPY models ./models
COPY config ./config

RUN mkdir -p /app/status /app/outputs

ENV DEMO_PORT=8081 \
    GAZE_CONFIG=/app/config/rooms.json \
    GAZE_CALIBRATION=/app/config/calib_config.json \
    GAZE_MODEL=/app/models/face_landmarker.task

CMD ["python", "-m", "gaze_tracker"]
