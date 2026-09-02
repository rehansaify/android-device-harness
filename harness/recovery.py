"""Recovery layer for healing unhealthy Android devices."""

import logging
import time
from typing import List, Optional, Protocol, Sequence

from harness.device import AndroidDevice
from harness.exceptions import HarnessError
from harness.health import DeviceHealthMonitor
from harness.models import HealthReport, RecoveryReport, RecoveryStepResult

logger = logging.getLogger(__name__)


class RecoveryStep(Protocol):
    """Protocol for a single recovery step."""

    name: str

    def run(self, device: AndroidDevice) -> RecoveryStepResult:
        """Executes the recovery step."""
        ...


class ReconnectAdbStep:
    """Restarts the ADB server and reconnects to the device."""

    name = "reconnect_adb"

    def run(self, device: AndroidDevice) -> RecoveryStepResult:
        start = time.monotonic()
        try:
            device.adb.kill_server()
            device.adb.start_server()
            device.adb.wait_for_device(device.serial, timeout=10.0)
            duration = int((time.monotonic() - start) * 1000)
            return RecoveryStepResult(
                self.name, True, duration, "ADB server restarted and device found"
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return RecoveryStepResult(
                self.name, False, duration, "Failed to reconnect ADB", str(e)
            )


class RestartFrameworkStep:
    """Restarts the Android application framework (soft reboot)."""

    name = "restart_framework"

    def run(self, device: AndroidDevice) -> RecoveryStepResult:
        start = time.monotonic()
        try:
            # Stop the framework
            device.shell(["stop"], timeout=10.0)
            time.sleep(2.0)
            # Start the framework
            device.shell(["start"], timeout=10.0)

            # Wait for boot completion
            timeout = time.monotonic() + 30.0
            booted = False
            while time.monotonic() < timeout:
                try:
                    if device.getprop("sys.boot_completed") == "1":
                        booted = True
                        break
                except HarnessError:
                    pass
                time.sleep(2.0)

            duration = int((time.monotonic() - start) * 1000)
            if booted:
                return RecoveryStepResult(
                    self.name,
                    True,
                    duration,
                    "Android framework restarted successfully",
                )
            return RecoveryStepResult(
                self.name,
                False,
                duration,
                "Android framework did not complete boot after restart",
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return RecoveryStepResult(
                self.name, False, duration, "Failed to restart framework", str(e)
            )


class RebootDeviceStep:
    """Hard reboots the Android device."""

    name = "reboot_device"

    def run(self, device: AndroidDevice) -> RecoveryStepResult:
        start = time.monotonic()
        try:
            device.reboot()
            device.adb.wait_for_device(device.serial, timeout=60.0)

            timeout = time.monotonic() + 60.0
            booted = False
            while time.monotonic() < timeout:
                try:
                    if device.getprop("sys.boot_completed") == "1":
                        booted = True
                        break
                except HarnessError:
                    pass
                time.sleep(2.0)

            duration = int((time.monotonic() - start) * 1000)
            if booted:
                return RecoveryStepResult(
                    self.name, True, duration, "Device rebooted successfully"
                )
            return RecoveryStepResult(
                self.name, False, duration, "Device rebooted but boot not completed"
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return RecoveryStepResult(
                self.name, False, duration, "Failed to reboot device", str(e)
            )


DEFAULT_STEPS: List[RecoveryStep] = [
    ReconnectAdbStep(),
    RestartFrameworkStep(),
    RebootDeviceStep(),
]


class RecoveryEngine:
    """Escalating recovery engine for unhealthy Android devices."""

    def __init__(
        self,
        health_monitor: DeviceHealthMonitor,
        steps: Optional[Sequence[RecoveryStep]] = None,
    ) -> None:
        self.health_monitor = health_monitor
        self.steps = steps if steps is not None else DEFAULT_STEPS

    def recover(
        self, device: AndroidDevice, initial_health: HealthReport
    ) -> RecoveryReport:
        """Attempts to recover a device using an escalating strategy."""
        overall_start = time.monotonic()

        if initial_health.is_healthy:
            return RecoveryReport(
                serial=device.serial,
                successful=True,
                steps=[],
                final_health=initial_health,
                total_duration_ms=int((time.monotonic() - overall_start) * 1000),
            )

        current_health = initial_health
        step_results: List[RecoveryStepResult] = []

        for step in self.steps:
            logger.info("Attempting recovery step: %s", step.name)
            step_start = time.monotonic()
            try:
                step_result = step.run(device)
            except Exception as e:
                # Catch-all to prevent recovery engine crash
                logger.exception("Unexpected error in recovery step %s", step.name)
                duration = int((time.monotonic() - step_start) * 1000)
                step_result = RecoveryStepResult(
                    step_name=step.name,
                    success=False,
                    duration_ms=duration,
                    message="Unexpected internal error during recovery step",
                    details=str(e),
                )

            step_results.append(step_result)

            # Always re-check health after a step, regardless of whether the step thought it succeeded.
            current_health = self.health_monitor.check_health(device)
            if current_health.is_healthy:
                break

        total_duration = int((time.monotonic() - overall_start) * 1000)
        return RecoveryReport(
            serial=device.serial,
            successful=current_health.is_healthy,
            steps=step_results,
            final_health=current_health,
            total_duration_ms=total_duration,
        )
