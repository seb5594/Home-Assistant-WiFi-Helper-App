ARG BUILD_FROM=@@BASE_IMAGE@@
FROM ${BUILD_FROM}
ARG BUILD_VERSION=@@VERSION@@
RUN apk add --no-cache @@RUNTIME_PACKAGES@@
COPY app/ /opt/helper/
COPY run.sh /run.sh
RUN chmod 755 /run.sh
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/helper
LABEL io.hass.name="WiFi App Helper" io.hass.description="Dedicated radio namespace broker" \
    io.hass.type="addon" io.hass.version="${BUILD_VERSION}" \
    org.opencontainers.image.title="Home Assistant App: WiFi App Helper" \
    org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.source="https://github.com/seb5594/Home-Assistant-WiFi-Helper-App"
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/run.sh"]
