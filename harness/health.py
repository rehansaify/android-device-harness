"""Device health checking."""

import logging
import time
from typing import List, Optional, Protocol, Sequence

from harness.device import AndroidDevice
from harness.exceptions import HarnessError
from harness.models import DeviceState, HealthReport, HealthResult

logger = logging.getLogger(__name__)


class HealthCheck(Protocol):
    """Protocol for a health check."""

    name: str
    timeout: float

    def run(self, device: AndroidDevice) -> HealthResult:
        """Executes the health check."""
        ...


class AdbConnectivityCheck:
    name = "adb_connectivity"
    timeout = 10.0

    def run(self, device: AndroidDevice) -> HealthResult:
        start = time.monotonic()
        try:
            # We bypass device.is_online() here to grab the actual raw state for logging
            state = device.adb.get_state(device.serial)
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, True, duration, f"ADB connected. State: {state}"
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, False, duration, "ADB connection failed", str(e)
            )


class DeviceStateCheck:
    name = "device_state"
    timeout = 5.0

    def run(self, device: AndroidDevice) -> HealthResult:
        start = time.monotonic()
        try:
            device.refresh_info()
            duration = int((time.monotonic() - start) * 1000)
            if device.state == DeviceState.ONLINE:
                return HealthResult(self.name, True, duration, "Device is online")
            return HealthResult(
                self.name, False, duration, f"Device state is {device.state.value}"
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, False, duration, "Failed to get device state", str(e)
            )


class BootCompletedCheck:
    name = "boot_completed"
    timeout = 10.0

    def run(self, device: AndroidDevice) -> HealthResult:
        start = time.monotonic()
        try:
            val = device.getprop("sys.boot_completed")
            duration = int((time.monotonic() - start) * 1000)
            if val == "1":
                return HealthResult(self.name, True, duration, "Boot completed")
            return HealthResult(
                self.name, False, duration, f"Boot not completed (val={val})"
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, False, duration, "Failed to check boot property", str(e)
            )


class PackageManagerCheck:
    name = "package_manager"
    timeout = 15.0

    def run(self, device: AndroidDevice) -> HealthResult:
        start = time.monotonic()
        try:
            # Bounded check to see if PM can resolve 'android' package
            out = device.shell(["pm", "path", "android"])
            duration = int((time.monotonic() - start) * 1000)
            if "package:" in out:
                return HealthResult(
                    self.name, True, duration, "Package manager is responsive"
                )
            return HealthResult(
                self.name,
                False,
                duration,
                "Package manager did not return expected output",
                out,
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, False, duration, "Package manager check failed", str(e)
            )


class SystemServerCheck:
    name = "system_server"
    timeout = 10.0

    def run(self, device: AndroidDevice) -> HealthResult:
        start = time.monotonic()
        try:
            pid = device.pidof("system_server")
            duration = int((time.monotonic() - start) * 1000)
            if pid is not None:
                return HealthResult(
                    self.name, True, duration, f"system_server running with PID {pid}"
                )
            return HealthResult(
                self.name, False, duration, "system_server process not found"
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, False, duration, "Failed to check system_server PID", str(e)
            )


class UiResponsivenessCheck:
    name = "ui_responsiveness"
    timeout = 15.0

    def run(self, device: AndroidDevice) -> HealthResult:
        start = time.monotonic()
        try:
            # Check window manager service via binder. If it's deadlocked, this will fail/timeout.
            out = device.shell(["service", "check", "window"])
            duration = int((time.monotonic() - start) * 1000)
            if "Service window: found" in out:
                return HealthResult(
                    self.name, True, duration, "UI WindowManager service is responsive"
                )
            return HealthResult(
                self.name,
                False,
                duration,
                "WindowManager service not found or unresponsive",
                out,
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, False, duration, "Failed to check UI responsiveness", str(e)
            )


class NetworkConnectivityCheck:
    name = "network_connectivity"
    timeout = 10.0

    def run(self, device: AndroidDevice) -> HealthResult:
        start = time.monotonic()
        try:
            # -c 1 (1 ping), -W 2 (2 seconds timeout max for the ping itself)
            out = device.shell(["ping", "-c", "1", "-W", "2", "8.8.8.8"])
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, True, duration, "Network connectivity verified", out
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return HealthResult(
                self.name, False, duration, "Network ping failed", str(e)
            )


DEFAULT_CHECKS: List[HealthCheck] = [
    AdbConnectivityCheck(),
    DeviceStateCheck(),
    BootCompletedCheck(),
    PackageManagerCheck(),
    SystemServerCheck(),
    UiResponsivenessCheck(),
    NetworkConnectivityCheck(),
]


class DeviceHealthMonitor:
    """Monitors device health by running a series of checks."""

    def __init__(self, checks: Optional[Sequence[HealthCheck]] = None) -> None:
        self.checks = checks if checks is not None else DEFAULT_CHECKS

    def check_health(self, device: AndroidDevice) -> HealthReport:
        """Runs all configured checks and returns a comprehensive health report."""
        results: List[HealthResult] = []
        overall_start = time.monotonic()

        for check in self.checks:
            check_start = time.monotonic()
            try:
                result = check.run(device)
                results.append(result)
            except Exception as e:
                logger.exception("Unexpected error in health check %s", check.name)
                duration = int((time.monotonic() - check_start) * 1000)
                results.append(
                    HealthResult(
                        check_name=check.name,
                        is_healthy=False,
                        duration_ms=duration,
                        message="Unexpected internal error during check",
                        details=str(e),
                    )
                )

        total_duration = int((time.monotonic() - overall_start) * 1000)
        return HealthReport(
            serial=device.serial,
            results=results,
            total_duration_ms=total_duration,
        )
