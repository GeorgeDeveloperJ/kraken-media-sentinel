# Kraken Media Sentinel

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg?style=for-the-badge&logo=linux&logoColor=white)](https://kernel.org)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-standard--library-success.svg?style=for-the-badge)](https://docs.python.org/3/library/)
[![Init System](https://img.shields.io/badge/systemd-daemon-informational.svg?style=for-the-badge&logo=linux&logoColor=white)](https://systemd.io/)
[![Containers](https://img.shields.io/badge/docker-compose-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Alerts](https://img.shields.io/badge/alerts-Telegram%20%7C%20Discord-5865F2.svg?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com)
[![Tests](https://img.shields.io/badge/tests-unittest-brightgreen.svg?style=for-the-badge&logo=python&logoColor=white)](https://docs.python.org/3/library/unittest.html)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

A lightweight, zero-dependency background daemon managed by `systemd` that continuously monitors external USB media storage, automatically recovers from stale or disconnected mounts without corrupting active Docker services, and broadcasts alerts to Telegram and Discord.

---

## Key Features

- **Zero External Dependencies**: Implemented entirely with the Python 3 standard library (`urllib.request`, `pathlib`, `subprocess`, `dataclasses`). No virtual environments or external `pip` packages required.
- **3-Tier Failure Detection**:
  - `/proc/mounts` verification to detect dropped mount points.
  - Kernel block device UUID validation via `blkid` to prevent mounting the wrong drive if device nodes shift (`/dev/sdb` $\rightarrow$ `/dev/sdc`).
  - I/O canary file read to catch unresponsive or frozen USB bus states.
- **Docker-Aware Recovery Sequence**: Gracefully stops dependent media containers (e.g. Jellyfin, Radarr, Sonarr, qBittorrent) to release open file descriptors before issuing a lazy unmount (`umount -l`), remounting, restoring permissions (`chown`/`chmod`), and restarting the stack.
- **Multi-Channel Alerting**: Dispatches instant status and recovery notifications with rich embeds to Discord webhooks and formatted HTML alerts to Telegram.
- **Alert Throttling & Quiet Mode**: Escalates up to 3 recovery attempts. If hardware is physically detached, it emits a single critical alert, enters quiet standby, and notifies only when the drive is restored.
- **Production Systemd Service**: Built to run as a reliable root `systemd` system service with automatic restarts.

---

## Tech Stack

- **Language & Runtime**: Python 3.10+ (Standard Library only)
- **Service Management**: `systemd`
- **Container Runtime**: Docker & Docker Compose
- **Alert Protocols**: Telegram Bot API & Discord Webhooks

---

## Prerequisites

- Linux host running `systemd`
- Python 3.10+
- Root / `sudo` privileges (required for `mount`, `umount`, and filesystem permission management)
- Target drive UUID (obtainable via `lsblk -f` or `blkid`)
- Media Docker Compose stack (optional, if automating container stops during remounts)

---

## Getting Started

### 1. Clone & Configure

```bash
git clone https://github.com/george-santana/kraken-media-manager.git
cd kraken-media-manager

# Create active configuration from the template
cp config.env.example config.env
chmod 600 config.env
```

### 2. Configure Environment Variables

Edit `config.env` with your system's parameters:

```ini
# Target Storage (Run: blkid to find your disk UUID)
TARGET_UUID=cc8b5c2a-3683-4a3c-b0e3-6a30c6f43b41
MOUNT_POINT=/home/user/media
COMPOSE_FILE=/opt/kraken-lab/media/docker-compose.yml
MOUNT_USER=user
MOUNT_GROUP=user

# Polling & Recovery Tuning
CHECK_INTERVAL_SECONDS=30
MAX_RETRIES=3
RETRY_DELAY_SECONDS=10
CANARY_FILE=.mount_canary

# Notifications (Optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DISCORD_WEBHOOK_URL=
```

---

## Verification & CLI Testing

Run the automated unit test suite to verify configuration loading, health checks, notifiers, and recovery invariants:

```bash
python3 -m unittest discover -s tests -v
```

Execute one-off CLI commands:

```bash
# Perform a health check diagnosis (exit code 0 = healthy, 1 = degraded)
python3 src/monitor.py --check

# Test Telegram and Discord notifications
python3 src/monitor.py --test-notifications

# Manually trigger a remount recovery sequence
sudo python3 src/monitor.py --remount
```

---

## Installation & Deployment

### Quick Install (Automated)

Run the included installation script to set up directories, configuration template, systemd unit, and global CLI symlink:

```bash
sudo ./install.sh
```

### Manual Systemd Installation

1. Copy the service unit to systemd:

   ```bash
   sudo cp systemd/kraken-media-sentinel.service /etc/systemd/system/
   ```

2. Secure the configuration file in `/etc`:

   ```bash
   sudo mkdir -p /etc/kraken-media-manager
   sudo cp config.env /etc/kraken-media-manager/config.env
   sudo chmod 600 /etc/kraken-media-manager/config.env
   ```

3. Reload and start the daemon:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now kraken-media-sentinel.service
   ```

4. Inspect live status and logs:

   ```bash
   sudo systemctl status kraken-media-sentinel.service
   sudo journalctl -u kraken-media-sentinel.service -f
   ```

---

## License

This project is licensed under the MIT License.
