import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # Hardware and mounts
    target_uuid: str = ""
    mount_point: Path = Path("/mnt/media")
    compose_file: Path | None = None
    mount_user: str = "root"
    mount_group: str = "root"
    fstab_options: str = "defaults,nofail,x-systemd.device-timeout=15s"
    systemd_mount_unit: str = ""

    # Tuning
    check_interval_seconds: int = 30
    max_retries: int = 3
    retry_delay_seconds: int = 10
    canary_file: str = ".mount_canary"

    # Notifications
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None


def validate_config(config: Config) -> list[str]:
    errors = []
    if not config.target_uuid:
        errors.append("TARGET_UUID is required and cannot be empty")
    if config.telegram_bot_token and not config.telegram_chat_id:
        errors.append(
            "TELEGRAM_CHAT_ID is required when TELEGRAM_BOT_TOKEN is provided"
        )
    return errors


def load_env(env_file: Path) -> dict[str, str]:
    data = {}
    if not env_file.is_file():
        return data

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip("'\"")

    return data


def load_config(
    env_file: (str | Path) | None = None, environ: dict | None = None
) -> Config:
    file_vars: dict[str, str] = {}
    if env_file:
        file_vars = load_env(Path(env_file))

    env_source = dict(os.environ) if environ is None else environ
    merged: dict[str, str] = {**file_vars, **env_source}

    def get_str(key: str, default: str = "") -> str:
        return merged.get(key.upper(), merged.get(key.lower(), default))

    def get_optional_str(key: str) -> str | None:
        val = merged.get(key.upper(), merged.get(key.lower()))
        return val if val else None

    def parse_int(key: str, default: int) -> int:
        val = get_optional_str(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    compose_raw = get_optional_str("compose_file")
    compose_path = Path(compose_raw) if compose_raw else None

    return Config(
        target_uuid=get_str("target_uuid", ""),
        mount_point=Path(get_str("mount_point", "/mnt/media")),
        compose_file=compose_path,
        mount_user=get_str("mount_user", "root"),
        mount_group=get_str("mount_group", "root"),
        fstab_options=get_str(
            "fstab_options", "defaults,nofail,x-systemd.device-timeout=15s"
        ),
        systemd_mount_unit=get_str("systemd_mount_unit", ""),
        check_interval_seconds=parse_int("check_interval_seconds", 30),
        max_retries=parse_int("max_retries", 3),
        retry_delay_seconds=parse_int("retry_delay_seconds", 10),
        canary_file=get_str("canary_file", ".mount_canary"),
        telegram_bot_token=get_optional_str("telegram_bot_token"),
        telegram_chat_id=get_optional_str("telegram_chat_id"),
        discord_webhook_url=get_optional_str("discord_webhook_url"),
    )
