#!/usr/bin/env python3
import argparse
import signal
import sys
import time
from logging import getLogger
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import Config, load_config, validate_config
from src.health import HealthChecker
from src.notifier import Notifier
from src.recovery import RecoveryEngine

logger = getLogger(__name__)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Kraken Media Sentinel, monitors media storage, remounts and recovers"
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="triggers health check and exit (code 0 = ok, 1 = degraded)",
    )

    parser.add_argument(
        "--remount",
        "-r",
        action="store_true",
        help="manual recovery cycle and exit (replaces old shell scripts).",
    )

    parser.add_argument(
        "--test-notifications",
        "-t",
        action="store_true",
        help="dispatches test messages to Telegram and Discord.",
    )

    parser.add_argument(
        "--daemon",
        "-d",
        action="store_true",
        help="runs the 24/7 baground monitoring loop",
    )

    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to configuration env file (default: checks local config.env, then /etc/kraken-media-manager/config.env",
    )

    args = parser.parse_args(argv)

    if not (args.check or args.remount or args.test_notifications or args.daemon):
        parser.print_help()
        sys.exit(1)

    return args


def resolve_config_file(cli_path: Path | None) -> Path | None:
    if cli_path and cli_path.is_file():
        return cli_path

    local_env = Path("config.env")
    if local_env.is_file():
        return local_env

    system_env = Path("/etc/kraken-media-manager/config.env")
    if system_env.is_file():
        return system_env

    return None


def handle_check(config: Config):
    checker = HealthChecker(config)
    status = checker.check_health()

    if status.is_healthy:
        print(f"OK: Storage healthy at {config.mount_point} ({status.device})")
        return 0
    print(f"DEGRADED: Tier {status.tier} failure: {status.error_message}")
    return 1


def handle_remount(config: Config):
    checker = HealthChecker(config)
    engine = RecoveryEngine(config, checker)
    result = engine.recover()

    if result.success:
        print(f"SUCCESS: Storage remounted ({result.attempts} attempts).")
        return 0
    print(f"FAILURE: Remount failed: {result.error_message}")
    return 1


def handle_test_notifications(config: Config):
    notifier = Notifier(config)
    res = notifier.notify_test("Kraken Media Sentinel notification test")

    print(f"Telegram sent: {res.get('telegram_notification', False)}")
    print(f"Discord sent:  {res.get('discord_notification', False)}")
    return 0


def handle_daemon(config: Config) -> None:
    logger.info(
        "Starting Kraken Media Sentinel daemon (polling every %ds)",
        config.check_interval_seconds,
    )
    checker = HealthChecker(config)
    engine = RecoveryEngine(config, checker)
    notifier = Notifier(config)

    in_failure_state = False
    running = True

    def stop_signal(sig, frame):
        nonlocal running
        logger.info("Received signal %d, shutting down cleanly...", sig)
        running = False

    signal.signal(signal.SIGINT, stop_signal)
    signal.signal(signal.SIGTERM, stop_signal)

    while running:
        status = checker.check_health()

        if status.is_healthy:
            if in_failure_state:
                logger.info("Storage restored. Sending recovery notification.")
                notifier.notify_recovery(
                    f"Storage at {config.mount_point} restored and healthy"
                )
                in_failure_state = False
        else:
            logger.warning(
                "Health check failed (Tier %d: %s). Initiating recovery...",
                status.tier,
                status.error_message,
            )
            res = engine.recover()

            if res.success:
                logger.info("Recovered on attempt %d.", res.attempts)
                if in_failure_state:
                    notifier.notify_recovery("Storage recovered after remount.")
                    in_failure_state = False
            else:
                logger.error("Recovery failed all attempts.")
                if not in_failure_state:
                    notifier.notify_critical(
                        f"Storage remount failed: {res.error_message}"
                    )
                    in_failure_state = True
        for _ in range(config.check_interval_seconds):
            if not running:
                break
            time.sleep(1)


def main(argv=None):
    args = parse_args(argv)

    config_path = resolve_config_file(args.config)
    config = load_config(env_file=config_path)

    errors = validate_config(config)
    if errors:
        for error in errors:
            logger.error("Configuration error: %s", error)
        return 1

    if args.check:
        return handle_check(config)
    if args.remount:
        return handle_remount(config)
    if args.test_notifications:
        return handle_test_notifications(config)
    if args.daemon:
        handle_daemon(config)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
