FROM ghcr.io/seb5594/home-assistant-base-python:3.14-alpine3.24-2026.11.0@sha256:807723c78eeeb57962063875e19b500571a5a6e89423977db6d1123832f1550e
RUN apk add --no-cache iw=6.17-r0 iproute2=7.0.0-r0
# Vendor the reviewed SDK into this example app's build context before building.
COPY vendor/wifi_helper/ /opt/sdk/wifi_helper/
COPY app.py /opt/example/app.py
ENV PYTHONPATH=/opt/sdk PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/opt/example/app.py"]
