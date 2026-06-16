# syntax=docker/dockerfile:1
# Railway all-in-one on the official Hermes Agent image (s6 PID 1 + supervised services).
#
# Build:  docker build --build-arg HERMES_IMAGE=nousresearch/hermes-agent:latest .
# Pin:    HERMES_IMAGE=nousresearch/hermes-agent:<tag>

ARG HERMES_IMAGE=nousresearch/hermes-agent:v2026.6.5
FROM ${HERMES_IMAGE}

USER root

WORKDIR /app

COPY vendor/hermes-webui /app/vendor/hermes-webui
COPY control_plane /app/control_plane
COPY requirements-control-plane.txt /app/requirements-control-plane.txt
COPY docker/s6-rc.d/ /etc/s6-overlay/s6-rc.d/
COPY docker/cont-init.d/ /etc/cont-init.d/
COPY docker/sshd/ /etc/ssh/sshd_config.d/
COPY docker/scripts/ /app/docker/scripts/

ARG HERMES_WEBUI_VERSION=unknown

# Tailscale userspace mode (no TUN): optional tailnet access on Railway. See README § Tailscale.
RUN curl -fsSL https://tailscale.com/install.sh | sh

# docker exec shell: micro editor, zsh + Oh My Zsh (root and hermes).
# OMZ/plugins match hermes-agent-docker/Dockerfile (RUNZSH=no … zsh-syntax-highlighting).
ARG MICRO_VERSION=2.0.14
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        zsh git curl ca-certificates openssh-server \
    && ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
         amd64) MICRO_DIR="micro-${MICRO_VERSION}-linux64" ;; \
         arm64) MICRO_DIR="micro-${MICRO_VERSION}-linux-arm64" ;; \
         *) echo "unsupported architecture for micro: $ARCH" >&2; exit 1 ;; \
       esac \
    && curl -fsSL "https://github.com/zyedidia/micro/releases/download/v${MICRO_VERSION}/${MICRO_DIR}.tar.gz" \
        | tar -xzO "micro-${MICRO_VERSION}/micro" > /usr/local/bin/micro \
    && chmod 0755 /usr/local/bin/micro \
    && mkdir -p /opt/data \
    && chown hermes:hermes /opt/data \
    && for OMZ_HOME in /root /opt/data; do \
         HOME="${OMZ_HOME}" RUNZSH=no CHSH=no KEEP_ZSHRC=yes \
           sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" \
         && ZSH_CUSTOM="${OMZ_HOME}/.oh-my-zsh/custom" \
         && git clone --depth=1 https://github.com/zsh-users/zsh-autosuggestions "${ZSH_CUSTOM}/plugins/zsh-autosuggestions" \
         && git clone --depth=1 https://github.com/zsh-users/zsh-syntax-highlighting "${ZSH_CUSTOM}/plugins/zsh-syntax-highlighting" \
         && sed -i 's/^plugins=(git)/plugins=(sudo history colored-man-pages zsh-autosuggestions zsh-syntax-highlighting)/' "${OMZ_HOME}/.zshrc"; \
       done \
    && chown -R hermes:hermes /opt/data/.oh-my-zsh /opt/data/.zshrc \
    && chsh -s "$(command -v zsh)" root \
    && chsh -s "$(command -v zsh)" hermes \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# fastapi + uvicorn[standard] are the `hermes dashboard` deps: keep them in sync
# with the tool.dashboard pins in vendor/hermes-agent/tools/lazy_deps.py.
# uvicorn[standard] (not plain uvicorn) is required — it pulls in `websockets`,
# which the dashboard's /api/pty and /api/ws WebSocket endpoints depend on.
# chown the venv to hermes so the non-root user can run lazy installs at runtime.
RUN printf "__version__ = '%s'\n" "$HERMES_WEBUI_VERSION" > /app/vendor/hermes-webui/api/_version.py \
    && uv pip install --python /opt/hermes/.venv/bin/python --no-cache-dir \
        -r /app/vendor/hermes-webui/requirements.txt \
        -r /app/requirements-control-plane.txt \
        "mcp>=1.24.0" \
        "fastapi==0.133.1" \
        "uvicorn[standard]==0.41.0" \
    && chown -R hermes:hermes /opt/hermes/.venv \
    && chmod +x /etc/cont-init.d/03-all-in-one-setup \
    && chmod +x /etc/cont-init.d/04-tailscale-env \
    && chmod +x /etc/cont-init.d/05-hermes-path \
    && chmod +x /etc/cont-init.d/06-tailscale-ssh-dir \
    && chmod +x /etc/s6-overlay/s6-rc.d/control-plane/run \
    && chmod +x /etc/s6-overlay/s6-rc.d/hermes-webui/run \
    && chmod +x /etc/s6-overlay/s6-rc.d/tailscaled/run \
    && chmod +x /app/docker/scripts/gateway_autostart.py \
    && mkdir -p /opt/data \
    && chown hermes:hermes /opt/data \
    && chmod 755 /opt/data

# Volume at /opt/data; agent state under /opt/data/.hermes (see cont-init migration).
# /usr/local/bin: Node 22 from the base image (TUI, npm tools). cont-init 05-hermes-path
# also patches PATH for railway ssh shells that inherit a minimal PATH.
ENV PATH="/usr/local/bin:/opt/hermes/bin:/opt/hermes/.venv/bin:/opt/data/.local/bin:${PATH}" \
    HERMES_NODE=/usr/local/bin/node \
    HOME=/opt/data \
    SHELL=/bin/zsh \
    HERMES_DATA_DIR=/opt/data \
    HERMES_HOME=/opt/data/.hermes \
    HERMES_CONFIG_PATH=/opt/data/.hermes/config.yaml \
    HERMES_WEBUI_STATE_DIR=/opt/data/webui \
    HERMES_WEBUI_AGENT_DIR=/opt/hermes \
    HERMES_WORKSPACE_DIR=/opt/data/workspace \
    CONTROL_PLANE_INTERNAL_WEBUI_HOST=127.0.0.1 \
    CONTROL_PLANE_INTERNAL_WEBUI_PORT=8788 \
    CONTROL_PLANE_HOST=0.0.0.0 \
    CONTROL_PLANE_RUNTIME=s6 \
    HERMES_GATEWAY_AUTOSTART=auto \
    HERMES_DASHBOARD=0 \
    PYTHONPATH=/app

EXPOSE 8787

# Inherits ENTRYPOINT ["/init", "/opt/hermes/docker/main-wrapper.sh"] from the base image.
# Hold the container open while s6 supervises control-plane, hermes-webui, and gateways.
CMD ["sleep", "infinity"]
