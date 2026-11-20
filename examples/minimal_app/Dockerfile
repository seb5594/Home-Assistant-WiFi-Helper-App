FROM ghcr.io/seb5594/home-assistant-base-python:3.14-alpine3.24-2026.11.0
RUN apk add --no-cache iw iproute2

# Vendor the reviewed SDK into this example app's build context before building.
COPY vendor/wifi_helper/ /opt/sdk/wifi_helper/
COPY app.py /opt/example/app.py
ENV PYTHONPATH=/opt/sdk PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/opt/example/app.py"]
