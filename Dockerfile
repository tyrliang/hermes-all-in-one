# syntax=docker/dockerfile:1
# Railway all-in-one on the official Hermes Agent image (s6 PID 1 + supervised services).
#
# Build:  docker build --build-arg HERMES_IMAGE=nousresearch/hermes-agent:latest .
# Pin:    HERMES_IMAGE=nousresearch/hermes-agent:<tag>

ARG HERMES_IMAGE=nousresearch/hermes-agent:latest
FROM ${HERMES_IMAGE}

USER root

WORKDIR /app

COPY vendor/hermes-webui /app/vendor/hermes-webui
COPY control_plane /app/control_plane
COPY requirements-control-plane.txt /app/requirements-control-plane.txt
COPY docker/s6-rc.d/ /etc/s6-overlay/s6-rc.d/
COPY docker/cont-init.d/ /etc/cont-init.d/
COPY docker/scripts/ /app/docker/scripts/

ARG HERMES_WEBUI_VERSION=unknown

RUN printf "__version__ = '%s'\n" "$HERMES_WEBUI_VERSION" > /app/vendor/hermes-webui/api/_version.py \
    && uv pip install --python /opt/hermes/.venv/bin/python --no-cache-dir \
        -r /app/vendor/hermes-webui/requirements.txt \
        -r /app/requirements-control-plane.txt \
        "mcp>=1.24.0" \
    && chmod +x /etc/cont-init.d/03-all-in-one-setup \
    && chmod +x /etc/s6-overlay/s6-rc.d/control-plane/run \
    && chmod +x /etc/s6-overlay/s6-rc.d/hermes-webui/run \
    && chmod +x /app/docker/scripts/gateway_autostart.py

# Official layout: persistent state on /opt/data (not /data/.hermes).
ENV HOME=/opt/data \
    HERMES_HOME=/opt/data \
    HERMES_DATA_DIR=/opt/data \
    HERMES_CONFIG_PATH=/opt/data/config.yaml \
    HERMES_WEBUI_STATE_DIR=/opt/data/webui \
    HERMES_WEBUI_AGENT_DIR=/opt/hermes \
    HERMES_WORKSPACE_DIR=/opt/data/workspace \
    CONTROL_PLANE_INTERNAL_WEBUI_HOST=127.0.0.1 \
    CONTROL_PLANE_INTERNAL_WEBUI_PORT=8788 \
    CONTROL_PLANE_RUNTIME=s6 \
    HERMES_GATEWAY_AUTOSTART=auto \
    HERMES_DASHBOARD=0 \
    PORT=8787 \
    PYTHONPATH=/app

EXPOSE 8787

# Inherits ENTRYPOINT ["/init", "/opt/hermes/docker/main-wrapper.sh"] from the base image.
# Hold the container open while s6 supervises control-plane, hermes-webui, and gateways.
CMD ["sleep", "infinity"]
