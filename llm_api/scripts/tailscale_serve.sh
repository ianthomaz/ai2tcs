#!/usr/bin/env bash
# Expose LLM API (port 28471) for INTERNAL Tailscale network only. Run on the Mac where the API runs.
# Access: other machines on your tailnet (e.g. http://<mac-name>:28471 or http://100.x.x.x:28471).
# Do NOT use Funnel — this is internal access only, not public internet.
# Requires: tailscale, and permission in Tailscale admin for "Serve" on this device.
set -e
PORT="${API_PORT:-28471}"
echo "Exposing port $PORT for internal Tailscale network (no Funnel)..."
tailscale serve --bg "http://127.0.0.1:$PORT"
tailscale serve status
