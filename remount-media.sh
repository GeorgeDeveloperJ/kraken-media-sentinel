#!/usr/bin/env bash
set -euo pipefail

# Kraken Media Sentinel - Remount Wrapper
# Delegates to the Python CLI with dynamic environment fallback.

MONITOR_SCRIPT="/opt/kraken-lab/scripts/media-monitor/src/monitor.py"
CONFIG_FILE="/etc/kraken-media-manager/config.env"

# 1. Primary path: Delegate to Python Sentinel CLI
if [[ -f "${MONITOR_SCRIPT}" ]] && command -v python3 >/dev/null 2>&1; then
  exec python3 "${MONITOR_SCRIPT}" --remount "$@"
fi

echo "[WARN] Python monitor not found at ${MONITOR_SCRIPT}. Executing emergency shell fallback..."

# 2. Emergency fallback: dynamically source config from server
if [[ -f "${CONFIG_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
  set +a
elif [[ -f "./config.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "./config.env"
  set +a
fi

# Fallback defaults if not set
MOUNT_POINT="${MOUNT_POINT:-/mnt/media}"
COMPOSE_FILE="${COMPOSE_FILE:-}"
MOUNT_USER="${MOUNT_USER:-root}"
MOUNT_GROUP="${MOUNT_GROUP:-root}"

# Stop containers if compose file exists
if [[ -n "${COMPOSE_FILE}" ]] && [[ -f "${COMPOSE_FILE}" ]]; then
  docker compose -f "${COMPOSE_FILE}" stop || true
fi

# Clear and remount
umount -l "${MOUNT_POINT}" 2>/dev/null || true
mount "${MOUNT_POINT}"
chown -R "${MOUNT_USER}:${MOUNT_GROUP}" "${MOUNT_POINT}"
chmod 775 "${MOUNT_POINT}"

# Resume containers
if [[ -n "${COMPOSE_FILE}" ]] && [[ -f "${COMPOSE_FILE}" ]]; then
  docker compose -f "${COMPOSE_FILE}" up -d
fi

echo "[SUCCESS] Emergency remount completed."
