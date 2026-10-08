from dataclasses import dataclass
from pathlib import Path

from src.config import Config


@dataclass(frozen=True)
class HealthStatus:
    """Represents the diagnostic result of a 3-tier health check.

    Attributes:
        is_healthy: True if all 3 tiers passed, False if any tier failed.
        tier: 0 if healthy, or 1, 2, 3 indicating the specific failing tier.
        device: Active block device path (e.g., '/dev/sdb1') if detected.
        error_message: Human-readable diagnostic description of any failure.
    """

    is_healthy: bool
    tier: int
    device: str | None = None
    error_message: str | None = None


class HealthChecker:
    def __init__(self, config: Config):
        """Initializes the health checker with system and hardware configuration.

        Args:
            config: Application configuration containing target UUID, mount point,
                and tuning parameters.
        """
        self.config = config

    def check_mount_table(self) -> str | None:
        """Tier 1: Inspects /proc/mounts to verify the target directory is mounted.

        Returns:
            The backing block device path (e.g., '/dev/sdb1') if mounted,
            or None if the mount point is not registered in the kernel table.
        """

        mount_point = self.config.mount_point
        mount_dir = "/proc/mounts"
        path = None

        with open(mount_dir, "r") as f:
            for line in f:
                line = line.strip()
                output = line.split()
                device_node, mounted_path = output[0], output[1]
                if str(mount_point.resolve()) == mounted_path:
                    return device_node
        return path

    def check_device_uuid(self, device: str) -> bool:
        """Tier 2: Verifies that the mounted block device matches the target UUID.

        Catches ghost mounts caused by USB disconnections where the kernel
        re-enumerated the drive under a new device letter.

        Args:
            device: Active block device node path (e.g., '/dev/sdb1').

        Returns:
            True if the block device matches the configured target UUID,
            False if there is a mismatch or the UUID cannot be resolved.
        """
        target_symlink = Path("/dev/disk/by-uuid/") / self.config.target_uuid

        if not target_symlink.exists():
            return False

        return target_symlink.resolve() == Path(device).resolve()

    def check_canary_io(self) -> bool:
        """Tier 3: Performs a lightweight read operation to test filesystem responsiveness.

        Catches frozen USB bus controller states where the filesystem table is
        present but I/O operations hang or fail with EIO.

        Returns:
            True if the canary file or mount point directory can be read,
            False if an I/O error or filesystem exception occurs.
        """
        canary_path = self.config.mount_point / self.config.canary_file

        try:
            if canary_path.is_file():
                with open(canary_path, "rb") as f:
                    f.read(1)
            else:
                next(self.config.mount_point.iterdir(), None)

            return True

        except OSError:
            return False

    def check_health(self) -> HealthStatus:
        """Executes the 3-tier health check sequence in order of dependency.

        Evaluates Tier 1 (mount table), Tier 2 (device UUID identity), and
        Tier 3 (I/O responsiveness). Halts early on the first failing tier.

        Returns:
            A HealthStatus instance containing the overall health state, failing
            tier level (0 if all passed), and diagnostic message.
        """

        mount_table = self.check_mount_table()

        if not mount_table:
            return HealthStatus(
                is_healthy=False, tier=1, error_message="device not mounted"
            )

        if not self.check_device_uuid(mount_table):
            return HealthStatus(
                is_healthy=False,
                tier=2,
                device=mount_table,
                error_message="uuid mismatch",
            )

        if not self.check_canary_io():
            return HealthStatus(
                is_healthy=False,
                tier=3,
                device=mount_table,
                error_message="i/o error",
            )

        return HealthStatus(is_healthy=True, tier=0, device=mount_table)
