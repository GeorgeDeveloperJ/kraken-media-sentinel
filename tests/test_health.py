import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from src.config import Config
from src.health import HealthChecker


class TestHealth(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            target_uuid="test-uuid-1234",
            mount_point=Path("/mnt/media"),
            canary_file=".mount_canary",
        )
        self.checker = HealthChecker(self.config)

    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="sysfs /sys sysfs rw 0 0\n/dev/sda1 /ext4 rw 0 0\n",
    )
    def test_tier1_not_mounted(self, mock_file):
        """Should fail Tier 1 when mount point is missing from /proc/mounts."""

        status = self.checker.check_health()

        self.assertFalse(status.is_healthy)
        self.assertEqual(status.tier, 1)
        self.assertIn("not mounted", (status.error_message or "").lower())

    @patch.object(HealthChecker, "check_mount_table", return_value="/dev/sdb1")
    @patch.object(HealthChecker, "check_device_uuid", return_value=False)
    def test_tier2_uuid_mismatch(self, mock_uuid, mock_mount):
        """Should return Tier and Device attributes when Tier 2 check fails."""
        status = self.checker.check_health()

        self.assertFalse(status.is_healthy)
        self.assertEqual(status.tier, 2)
        self.assertEqual(status.device, "/dev/sdb1")
        self.assertIn("uuid mismatch", (status.error_message or "").lower())

    @patch.object(HealthChecker, "check_mount_table", return_value="/dev/sdb1")
    @patch.object(HealthChecker, "check_device_uuid", return_value=True)
    @patch.object(HealthChecker, "check_canary_io", return_value=False)
    def test_tier3_io_failure(self, mock_canary, mock_uuid, mock_mount):
        """Should return Tier and Device attributes when Tier 3 check fails."""
        status = self.checker.check_health()

        self.assertFalse(status.is_healthy)
        self.assertEqual(status.tier, 3)
        self.assertEqual(status.device, "/dev/sdb1")
        self.assertIn("i/o", (status.error_message or "").lower())

    @patch.object(HealthChecker, "check_mount_table", return_value="/dev/sdb1")
    @patch.object(HealthChecker, "check_device_uuid", return_value=True)
    @patch.object(HealthChecker, "check_canary_io", return_value=True)
    def test_all_tiers_healthy(self, mock_canary, mock_uuid, mock_mount):
        """Should return Tier 0 and no errors when no tiers failed."""
        status = self.checker.check_health()

        self.assertTrue(status.is_healthy)
        self.assertEqual(status.tier, 0)
        self.assertEqual(status.device, "/dev/sdb1")
        self.assertIsNone(status.error_message)
