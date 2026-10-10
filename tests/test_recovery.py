import logging
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import Config
from src.health import HealthChecker
from src.recovery import RecoveryEngine, RecoveryResult


class TestRecovery(unittest.TestCase):
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
            mount_user="george",
            mount_group="george",
            systemd_mount_unit="mnt-media.mount",
            max_retries=3,
            retry_delay_seconds=10,
        )
        self.mock_health = MagicMock(spec=HealthChecker)
        self.engine = RecoveryEngine(self.config, self.mock_health)

    @patch("src.recovery.run")
    @patch("src.recovery.Path.is_file", return_value=True)
    def test_stop_docker_success(self, mock_is_file, mock_run):
        """Should stop Docker stack when compose file is configured."""
        mock_run.return_value = MagicMock(returncode=0)

        result = self.engine.stop_docker()

        self.assertTrue(result)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(args, ["docker", "compose", "-f", str(self.config.compose_file), "stop"])

    def test_stop_docker_no_compose_file(self):
        """Should skip Docker stop when compose file is None."""
        config = Config(compose_file=None)
        engine = RecoveryEngine(config, self.mock_health)

        self.assertTrue(engine.stop_docker())

    @patch("src.recovery.run")
    def test_clear_mounts_success(self, mock_run):
        """Should lazy unmount and report success when unmount succeeds."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        result = self.engine.clear_mounts()

        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 2)

    @patch("src.recovery.run")
    def test_clear_mounts_already_unmounted(self, mock_run):
        """Should consider already unmounted state as a clean success."""
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=32, stderr="umount: /mnt/media: not mounted"),
        ]

        result = self.engine.clear_mounts()

        self.assertTrue(result)

    @patch("src.recovery.Path.exists")
    def test_device_is_connected(self, mock_exists):
        """Should return True when target block UUID exists in /dev/disk/by-uuid."""
        mock_exists.return_value = True
        self.assertTrue(self.engine.device_is_connected())

        mock_exists.return_value = False
        self.assertFalse(self.engine.device_is_connected())

    @patch("src.recovery.run")
    def test_mount_storage(self, mock_run):
        """Should mount storage and return True on successful exit code."""
        mock_run.return_value = MagicMock(returncode=0)

        self.assertTrue(self.engine.mount_storage())
        mock_run.assert_called_once_with(
            ["mount", str(self.config.mount_point)],
            capture_output=True,
            text=True,
            check=False,
        )

    @patch("src.recovery.run")
    def test_restore_permissions(self, mock_run):
        """Should apply chown and chmod 775 to restore storage permissions."""
        mock_run.return_value = MagicMock(returncode=0)

        self.assertTrue(self.engine.restore_permissions())
        self.assertEqual(mock_run.call_count, 2)

    @patch("src.recovery.run")
    @patch("src.recovery.Path.is_file", return_value=True)
    def test_start_docker_success(self, mock_is_file, mock_run):
        """Should restart Docker compose services with up -d."""
        mock_run.return_value = MagicMock(returncode=0)

        result = self.engine.start_docker()

        self.assertTrue(result)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertEqual(
            args,
            ["docker", "compose", "-f", str(self.config.compose_file), "up", "-d"],
        )

    @patch.object(RecoveryEngine, "stop_docker", return_value=True)
    @patch.object(RecoveryEngine, "clear_mounts", return_value=True)
    @patch.object(RecoveryEngine, "device_is_connected", return_value=False)
    @patch.object(RecoveryEngine, "mount_storage")
    def test_run_recovery_cycle_aborts_if_device_missing(
        self, mock_mount, mock_device, mock_clear, mock_docker
    ):
        """Should abort recovery cycle early if block device is disconnected."""
        result = self.engine.run_recovery_cycle()

        self.assertFalse(result)
        mock_mount.assert_not_called()

    @patch.object(RecoveryEngine, "run_recovery_cycle", return_value=True)
    def test_recover_success_first_attempt(self, mock_cycle):
        """Should succeed on first recovery cycle without retry sleep."""
        result = self.engine.recover()

        self.assertIsInstance(result, RecoveryResult)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 1)
        self.assertIsNone(result.error_message)

    @patch("src.recovery.time.sleep")
    @patch.object(RecoveryEngine, "run_recovery_cycle", side_effect=[False, True])
    def test_recover_retry_escalation(self, mock_cycle, mock_sleep):
        """Should escalate retries and succeed on subsequent cycle."""
        result = self.engine.recover()

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        mock_sleep.assert_called_once_with(10)

    @patch("src.recovery.time.sleep")
    @patch.object(RecoveryEngine, "run_recovery_cycle", return_value=False)
    def test_recover_all_attempts_fail(self, mock_cycle, mock_sleep):
        """Should exhaust all retries and return failure when recovery fails."""
        result = self.engine.recover()

        self.assertFalse(result.success)
        self.assertEqual(result.attempts, 3)
        self.assertIsNotNone(result.error_message)
        self.assertEqual(mock_sleep.call_count, 2)
