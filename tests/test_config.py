import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.config import Config, load_config, validate_config


class TestConfig(unittest.TestCase):
    def test_default_config_validation(self):
        """Default config should have empty target_uuid and fail validation."""
        config = load_config(environ={})

        self.assertIsInstance(config, Config)
        self.assertEqual(config.target_uuid, "")
        self.assertEqual(config.mount_point, Path("/mnt/media"))
        self.assertIsNone(config.compose_file)
        self.assertEqual(config.mount_user, "root")
        self.assertEqual(config.mount_group, "root")
        self.assertEqual(
            config.fstab_options, "defaults,nofail,x-systemd.device-timeout=15s"
        )
        self.assertEqual(config.systemd_mount_unit, "")

        self.assertEqual(config.check_interval_seconds, 30)
        self.assertEqual(config.max_retries, 3)
        self.assertEqual(config.retry_delay_seconds, 10)
        self.assertEqual(config.canary_file, ".mount_canary")
        self.assertIsNone(config.telegram_bot_token)
        self.assertIsNone(config.telegram_chat_id)
        self.assertIsNone(config.discord_webhook_url)

        errors = validate_config(config)
        self.assertIn("TARGET_UUID is required and cannot be empty", errors)

    def test_load_from_env_file(self):
        """Should parse KEY=VALUE, strip quotes, and ignore comments."""
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / "test.env"
            env_path.write_text(
                "# Sample config\n"
                "TARGET_UUID='test-uuid-1234'\n"
                'MOUNT_POINT="/custom/media"\n'
                "CHECK_INTERVAL_SECONDS=45\n"
                "DISCORD_WEBHOOK_URL=https://discord.mock/webhook\n"
            )

            config = load_config(env_file=env_path, environ={})
            self.assertEqual(config.target_uuid, "test-uuid-1234")
            self.assertEqual(config.mount_point, Path("/custom/media"))
            self.assertEqual(config.check_interval_seconds, 45)
            self.assertEqual(config.discord_webhook_url, "https://discord.mock/webhook")
            self.assertEqual(validate_config(config), [])

    def test_environ_overrides_file(self):
        """Process environment variables must take precedence over env file."""
        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / "test.env"
            env_path.write_text("TARGET_UUID=file-uuid\n")

            config = load_config(
                env_file=env_path, environ={"TARGET_UUID": "override-uuid"}
            )

            self.assertEqual(config.target_uuid, "override-uuid")

    def test_invalid_int_fallback(self):
        """Malformed integer strings should safely back to defaults."""
        config = load_config(
            environ={"CHECK_INTERVAL_SECONDS": "not-a-number", "MAX_RETRIES": "bad"}
        )

        self.assertEqual(config.check_interval_seconds, 30)
        self.assertEqual(config.max_retries, 3)

    def test_telegram_validation(self):
        """Telegram bot token requires chat ID."""
        config = load_config(
            environ={"TARGET_UUID": "1234", "TELEGRAM_BOT_TOKEN": "bot_token"}
        )

        errors = validate_config(config)

        self.assertIn(
            "TELEGRAM_CHAT_ID is required when TELEGRAM_BOT_TOKEN is provided", errors
        )
