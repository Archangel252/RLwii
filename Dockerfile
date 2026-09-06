# Dolphin + the training stack, for running on a cloud VM.
#
# Uses the Qt dolphin-emu binary under Xvfb rather than dolphin-emu-nogui:
# the headless frontend's main loop has no hotkey polling, so save states can
# never be loaded there, and reset() depends on that.
# Debian packages dolphin-emu; Ubuntu does not, and the old PPA is gone.
# amd64 explicitly: cloud VMs are x86, and there is no arm64 Dolphin package.
FROM --platform=linux/amd64 debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN sed -i 's/ main$/ main contrib non-free/' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        dolphin-emu \
        xvfb \
        python3 python3-pip python3-venv \
        procps \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps first so code changes don't rebuild the torch layer.
COPY requirements.txt .
# CPU-only torch: the default wheel drags in ~2.5GB of CUDA libraries that a
# cloud CPU instance can never use.
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple torch \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Dolphin's user dir; mounted volumes supply the game and save states.
# Debian installs Dolphin under /usr/games, which is not on PATH for
# non-interactive shells.
ENV PATH="/usr/games:${PATH}" \
    DOLPHIN_USER_DIR=/root/.config/dolphin-emu \
    DOLPHIN_BINARY=/usr/games/dolphin-emu \
    DOLPHIN_PIPE_NAME=test \
    PYTHONPATH=/app \
    DISPLAY=:99

VOLUME ["/app/Games", "/app/models", "/app/logs"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/venv/bin/python", "-m", "src.train", "--steps", "50000"]
