FROM docker.m.daocloud.io/library/python:3.10-slim AS builder

WORKDIR /build

RUN sed -i \
    -e 's|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
    -e 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
    /etc/apt/sources.list.d/debian.sources

RUN apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::https::Timeout=30 install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir "Cython>=3.0,<4" \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY setup_cython.py .
COPY gaze_tracker ./gaze_tracker
RUN python setup_cython.py build_ext --inplace \
    && find gaze_tracker -type f -name '*.py' \
       ! -name '__init__.py' ! -name '__main__.py' -delete \
    && find gaze_tracker -type f \( -name '*.c' -o -name '*.html' -o -name '*.pyc' \) -delete \
    && rm -rf gaze_tracker/__pycache__ build

FROM docker.m.daocloud.io/library/python:3.10-slim

WORKDIR /app

RUN sed -i \
    -e 's|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' \
    -e 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' \
    /etc/apt/sources.list.d/debian.sources

RUN apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update \
    && apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::https::Timeout=30 install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libegl1 \
    libgles2 \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY --from=builder /build/gaze_tracker ./gaze_tracker
COPY models ./models
COPY config ./config

RUN mkdir -p /app/status /app/outputs \
    && test -z "$(find /app/gaze_tracker -type f -name '*.py' ! -name '__init__.py' ! -name '__main__.py' -print -quit)"

ENV DEMO_PORT=8081 \
    GAZE_CONFIG=/app/config/rooms.json \
    GAZE_CALIBRATION=/app/config/calib_config.json \
    GAZE_MODEL=/app/models/face_landmarker.task \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8081

CMD ["python", "-m", "gaze_tracker"]
