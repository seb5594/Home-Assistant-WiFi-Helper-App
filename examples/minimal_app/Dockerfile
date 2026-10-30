FROM ghcr.io/home-assistant/base-python:3.13-alpine3.24@sha256:c7d34ae22a87275d46deb65bcb0511b389d7bc6eb8dccb28d44dd7cb8616e603
RUN apk add --no-cache iw=6.17-r0 iproute2=7.0.0-r0
# Vendor the reviewed SDK into this example app's build context before building.
COPY vendor/wifi_helper/ /opt/sdk/wifi_helper/
COPY app.py /opt/example/app.py
ENV PYTHONPATH=/opt/sdk PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "/opt/example/app.py"]
