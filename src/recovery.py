import logging
import time
from dataclasses import dataclass
from pathlib import Path
from subprocess import CalledProcessError, run

from src.config import Config
from src.health import HealthChecker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryResult:
    """Represents the outcome of a recovery sequence.

    Attributes:
        success: True if the storage passed health check after recovery.
        attempts: Number of recovery cycles executed (1..max_retries).
        error_message: Description of the failure if recovery did not succeed.
    """

    success: bool
    attempts: int
    error_message: str | None = None


class RecoveryEngine:
    """Orchestrates the 6-stage remount and service recovery pipeline."""

    def __init__(self, config: Config, health_checker: HealthChecker):
        """Initializes the recovery engine with configuration and health checker.

        Args:
            config: Application configuration containing paths, UUIDs, timeouts,
                and tuning parameters.
            health_checker: HealthChecker instance used to verify filesystem
                health after recovery cycles.
        """
        self.config = config
        self.health_checker = health_checker

    def stop_docker(self) -> bool:
        "Executes 'docker compose stop' if compose_file its configured."
        compose_file = self.config.compose_file
        if not compose_file:
            logger.info("No compose file configured, skipping Docker Stop.")
            return True
        if not compose_file.is_file():
            logger.warning(
                "Configured compose file %s does not exist, skipping.", compose_file
            )
            return False

        project_dir = compose_file.parent

        try:
            run(
                ["docker", "compose", "-f", str(compose_file), "stop"],
                cwd=project_dir,
                check=True,
                capture_output=True,
                text=True,
            )

        except CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            logger.error("Failed to stop Docker media stack: %s", err)
            return False
        except FileNotFoundError:
            logger.error("Docker executable not found in system PATH")
            return False

        return True

    def clear_mounts(self) -> bool:
        "Stops systemd mount unit and performs lazy umount."
        unit = self.config.systemd_mount_unit or (
            str(self.config.mount_point).strip("/").replace("/", "-") + ".mount"
        )

        run(["systemctl", "stop", unit], capture_output=True, check=False)

        result = run(
            ["umount", "-l", str(self.config.mount_point)],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0 or "not mounted" in result.stderr.lower():
            return True

        logger.error(
            "Failed to unmount %s: %s", self.config.mount_point, result.stderr.strip()
        )
        return False

    def device_is_connected(self) -> bool:
        """Checks if the target block device UUID is physically present."""
        uuid_node = Path("/dev/disk/by-uuid") / self.config.target_uuid
        if not uuid_node.exists():
            logger.warning(
                "Target device with UUID %s not detected in /dev/disk/by-uuid",
                self.config.target_uuid,
            )
            return False

        return True

    def mount_storage(self) -> bool:
        """Executes mount on the target mount point."""
        res = run(
            ["mount", str(self.config.mount_point)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return True
        logger.error(
            "Failed to mount %s: %s", self.config.mount_point, res.stderr.strip()
        )
        return False

    def restore_permissions(self) -> bool:
        """Enforces chown and chmod 775 on mount point."""
        target = str(self.config.mount_point)
        user_group = f"{self.config.mount_user}:{self.config.mount_group}"

        chown_res = run(
            ["chown", "-R", user_group, target],
            capture_output=True,
            text=True,
            check=False,
        )
        chmod_res = run(
            ["chmod", "775", target], capture_output=True, text=True, check=False
        )

        if chown_res.returncode == 0 and chmod_res.returncode == 0:
            return True

        logger.error("Failed to restore permissions on %s", target)
        return False

    def start_docker(self) -> bool:
        """Executes 'docker compose up -d' if compose_file is configured."""
        compose_file = self.config.compose_file
        if not compose_file:
            logger.info("No compose file configured, skipping Docker Up.")
            return True
        if not compose_file.is_file():
            logger.warning(
                "Configured compose file %s does not exist, skipping.", compose_file
            )
            return False

        project_dir = compose_file.parent

        try:
            run(
                ["docker", "compose", "-f", str(compose_file), "up", "-d"],
                cwd=project_dir,
                check=True,
                capture_output=True,
                text=True,
            )

        except CalledProcessError as e:
            err = e.stderr.strip() if e.stderr else str(e)
            logger.error("Failed to get up Docker media stack: %s", err)
            return False
        except FileNotFoundError:
            logger.error("Docker executable not found in system PATH")
            return False

        return True

    def run_recovery_cycle(self) -> bool:
        """Executes a single 6-stage recovery cycle in sequential order.

        Stops Docker, clears stale mounts, verifies block device existence,
        mounts the filesystem, restores permissions, resumes Docker, and
        validates filesystem health.

        Returns:
            True if all stages completed and HealthChecker reports healthy,
            False if any stage failed or the filesystem remains unhealthy.
        """

        if not self.stop_docker():
            return False
        if not self.clear_mounts():
            return False
        if not self.device_is_connected():
            return False
        if not self.mount_storage():
            return False
        if not self.restore_permissions():
            return False
        if not self.start_docker():
            return False

        return self.health_checker.check_health().is_healthy

    def recover(self) -> RecoveryResult:
        """Executes the recovery sequence with retry escalation.

        Attempts recovery up to max_retries times, pausing for retry_delay_seconds
        between failed attempts. Halts immediately once health is restored.

        Returns:
            A RecoveryResult detailing whether recovery succeeded, total
            attempts executed, and any failure error message.
        """
        for attempt in range(1, self.config.max_retries + 1):
            logger.info(
                "Attempting recovery (%d/%d)...", attempt, self.config.max_retries
            )
            if self.run_recovery_cycle():
                return RecoveryResult(success=True, attempts=attempt)

            if attempt < self.config.max_retries:
                time.sleep(self.config.retry_delay_seconds)

        return RecoveryResult(
            success=False,
            attempts=self.config.max_retries,
            error_message="Storage recovery failed all attempts",
        )
