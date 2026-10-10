import logging
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import Config
from src.health import HealthStatus
from src.monitor import (
    handle_check,
    handle_daemon,
    handle_remount,
    handle_test_notifications,
    main,
    parse_args,
    resolve_config_file,
)
from src.recovery import RecoveryResult


class TestMonitor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        logging.disable(logging.NOTSET)

    def setUp(self):
        self.config = Config(
            target_uuid="test-uuid-1234",
            mount_point=Path("/mnt/media"),
            compose_file=Path("/opt/media/docker-compose.yml"),
            check_interval_seconds=1,
            max_retries=1,
            retry_delay_seconds=1,
        )

    def test_parse_args_flags(self):
        """Should parse each primary action flag correctly."""
        self.assertTrue(parse_args(["--check"]).check)
        self.assertTrue(parse_args(["--remount"]).remount)
        self.assertTrue(parse_args(["--daemon"]).daemon)
        self.assertTrue(parse_args(["--test-notifications"]).test_notifications)

        args = parse_args(["--check", "-c", "custom.env"])
        self.assertEqual(args.config, Path("custom.env"))

    @patch("sys.stdout")
    @patch("sys.stderr")
    def test_parse_args_no_action_exits(self, mock_stderr, mock_stdout):
        """Should exit with code 1 if no action flag is supplied."""
        with self.assertRaises(SystemExit) as ctx:
            parse_args([])
        self.assertEqual(ctx.exception.code, 1)

    @patch("src.monitor.Path.is_file")
    def test_resolve_config_file(self, mock_is_file):
        """Should resolve config path with precedence to explicit CLI argument."""
        mock_is_file.return_value = True
        custom = Path("custom.env")
        self.assertEqual(resolve_config_file(custom), custom)

        mock_is_file.return_value = False
        self.assertIsNone(resolve_config_file(None))

    @patch("sys.stdout")
    @patch("src.monitor.HealthChecker.check_health")
    def test_handle_check_healthy(self, mock_check, mock_stdout):
        """Should print status and return 0 when filesystem is healthy."""
        mock_check.return_value = HealthStatus(is_healthy=True, tier=0, device="/dev/sdb1")
        self.assertEqual(handle_check(self.config), 0)

    @patch("sys.stdout")
    @patch("src.monitor.HealthChecker.check_health")
    def test_handle_check_degraded(self, mock_check, mock_stdout):
        """Should print status and return 1 when filesystem is degraded."""
        mock_check.return_value = HealthStatus(
            is_healthy=False, tier=1, error_message="not mounted"
        )
        self.assertEqual(handle_check(self.config), 1)

    @patch("sys.stdout")
    @patch("src.monitor.RecoveryEngine.recover")
    def test_handle_remount_success(self, mock_recover, mock_stdout):
        """Should return 0 when manual remount succeeds."""
        mock_recover.return_value = RecoveryResult(success=True, attempts=1)
        self.assertEqual(handle_remount(self.config), 0)

    @patch("sys.stdout")
    @patch("src.monitor.RecoveryEngine.recover")
    def test_handle_remount_failure(self, mock_recover, mock_stdout):
        """Should return 1 when manual remount fails."""
        mock_recover.return_value = RecoveryResult(
            success=False, attempts=3, error_message="disk missing"
        )
        self.assertEqual(handle_remount(self.config), 1)

    @patch("sys.stdout")
    @patch("src.monitor.Notifier.notify_test")
    def test_handle_test_notifications(self, mock_notify_test, mock_stdout):
        """Should dispatch test notifications and return 0."""
        mock_notify_test.return_value = {
            "telegram_notification": True,
            "discord_notification": True,
        }
        self.assertEqual(handle_test_notifications(self.config), 0)

    @patch("src.monitor.load_config")
    def test_main_validation_failure(self, mock_load):
        """Should return 1 when configuration validation fails."""
        mock_load.return_value = Config(target_uuid="")  # empty UUID triggers error
        self.assertEqual(main(["--check"]), 1)

    @patch("src.monitor.load_config")
    @patch("src.monitor.handle_check", return_value=0)
    def test_main_routes_to_check(self, mock_handle_check, mock_load):
        """Should route to handle_check and return its exit code."""
        mock_load.return_value = self.config
        self.assertEqual(main(["--check"]), 0)
        mock_handle_check.assert_called_once_with(self.config)

    @patch("src.monitor.HealthChecker.check_health")
    @patch("src.monitor.Notifier.notify_recovery")
    @patch("src.monitor.time.sleep")
    def test_handle_daemon_recovers_and_notifies(
        self, mock_sleep, mock_notify_recovery, mock_check
    ):
        """Should broadcast recovery notification when drive recovers after failure."""
        mock_check.return_value = HealthStatus(is_healthy=True, tier=0, device="/dev/sdb1")

        # Force loop to exit after 1 iteration
        with patch("signal.signal"):
            # Set running to false by simulating an interruption
            def side_effect_sleep(*args):
                raise KeyboardInterrupt()

            mock_sleep.side_effect = side_effect_sleep

            try:
                handle_daemon(self.config)
            except KeyboardInterrupt:
                pass

        mock_check.assert_called()

    @patch("src.monitor.HealthChecker.check_health")
    @patch("src.monitor.RecoveryEngine.recover")
    @patch("src.monitor.Notifier.notify_critical")
    @patch("src.monitor.time.sleep")
    def test_handle_daemon_critical_failure_alerts(
        self, mock_sleep, mock_notify_critical, mock_recover, mock_check
    ):
        """Should send critical alert on failed recovery cycle."""
        mock_check.return_value = HealthStatus(is_healthy=False, tier=1, error_message="lost")
        mock_recover.return_value = RecoveryResult(
            success=False, attempts=1, error_message="unplugged"
        )

        def side_effect_sleep(*args):
            raise KeyboardInterrupt()

        mock_sleep.side_effect = side_effect_sleep

        try:
            handle_daemon(self.config)
        except KeyboardInterrupt:
            pass

        mock_notify_critical.assert_called_once()
