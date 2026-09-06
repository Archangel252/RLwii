#!/bin/bash
set -e

# Dolphin's Qt frontend needs a display even when rendering to Null.
Xvfb :99 -screen 0 640x480x24 >/dev/null 2>&1 &
for _ in $(seq 20); do
  xdpyinfo -display :99 >/dev/null 2>&1 && break
  sleep 0.5
done

# Write Dolphin's config and create the input FIFO.
/venv/bin/python -m src.provision

exec "$@"
