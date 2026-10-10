#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "[ERROR] Please run install.sh with sudo / root permissions."
    exit 1
fi

INSTALL_DIR="/opt/kraken-lab/scripts/media-monitor"
CONFIG_DIR="/etc/kraken-media-manager"

echo "[1/5] Creating directories..."
mkdir -p "${INSTALL_DIR}"
mkdir -p "${CONFIG_DIR}"

echo "[2/5] Copying application files to ${INSTALL_DIR}..."
cp -r src "${INSTALL_DIR}/"
cp -n config.env.example "${INSTALL_DIR}/config.env.example"

echo "[3/5] Setting up configuration template in ${CONFIG_DIR}..."
if [[ ! -f "${CONFIG_DIR}/config.env" ]]; then
    cp config.env.example "${CONFIG_DIR}/config.env"
    chmod 600 "${CONFIG_DIR}/config.env"
    echo "[INFO] Created ${CONFIG_DIR}/config.env (chmod 600). Be sure to edit your UUID and tokens!"
else
    echo "[INFO] Existing ${CONFIG_DIR}/config.env preserved."
fi

echo "[4/5] Installing systemd service..."
cp systemd/kraken-media-sentinel.service /etc/systemd/system/
systemctl daemon-reload

echo "[5/5] Creating global CLI symlink /usr/local/bin/kraken-media-sentinel..."
chmod +x "${INSTALL_DIR}/src/monitor.py"
ln -sf "${INSTALL_DIR}/src/monitor.py" /usr/local/bin/kraken-media-sentinel

echo "=========================================================="
echo "Kraken Media Sentinel installed successfully!"
echo ""
echo "Next steps on the server:"
echo "  1. Edit config:  sudo nano ${CONFIG_DIR}/config.env"
echo "  2. Test health:  sudo kraken-media-sentinel --check"
echo "  3. Start daemon: sudo systemctl enable --now kraken-media-sentinel.service"
echo "  4. View logs:    sudo journalctl -u kraken-media-sentinel.service -f"
echo "=========================================================="
