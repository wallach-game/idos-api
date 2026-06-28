# Base image
FROM python:3.12-slim

# Environment variables for noVNC
ENV NOVNC_HOME=/opt/novnc
ENV WEB_PORT=6080

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    git \
    curl \
    x11vnc \
    xvfb \
    fluxbox \
    net-tools \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright and FastAPI dependencies
RUN pip install --no-cache-dir fastapi uvicorn[standard] playwright

# Install browsers for Playwright
RUN playwright install

# Install noVNC
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc
RUN git clone https://github.com/novnc/websockify.git /opt/novnc/utils/websockify

RUN playwright install-deps

# Copy app
WORKDIR /app
COPY ./app.py .

# Expose ports
EXPOSE 8000 5900 6080

# Start Xvfb, x11vnc, noVNC and FastAPI
CMD bash -c "\
    Xvfb :0 -screen 0 1280x720x24 & \
    fluxbox & \
    x11vnc -display :0 -nopw -forever -shared & \
    /opt/novnc/utils/novnc_proxy --vnc localhost:5900 --listen $WEB_PORT & \
    xvfb-run -a uvicorn app:app --host 0.0.0.0 --port 8000"
