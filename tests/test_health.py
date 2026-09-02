"""Unit tests for the health module."""

from unittest.mock import MagicMock

import pytest

from harness.device import AndroidDevice
from harness.exceptions import AdbCommandError
from harness.health import (
    AdbConnectivityCheck,
    BootCompletedCheck,
    DeviceHealthMonitor,
    DeviceStateCheck,
    HealthCheck,
    NetworkConnectivityCheck,
    PackageManagerCheck,
    SystemServerCheck,
    UiResponsivenessCheck,
)
from harness.models import DeviceState, HealthResult


@pytest.fixture  # type: ignore
def mock_device() -> MagicMock:
    device = MagicMock(spec=AndroidDevice)
    device.serial = "12345"
    device.state = DeviceState.ONLINE

    # Default healthy state for all methods
    device.adb = MagicMock()
    device.adb.get_state.return_value = "device"

    device.getprop.return_value = "1"  # boot completed
    device.shell.side_effect = lambda cmd: (
        "package:android"
        if "pm" in cmd
        else (
            "Service window: found"
            if "service" in cmd
            else "64 bytes from 8.8.8.8" if "ping" in cmd else ""
        )
    )
    device.pidof.return_value = 1000  # system_server PID

    return device


def test_all_checks_healthy(mock_device: MagicMock) -> None:
    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert report.serial == "12345"
    assert report.is_healthy
    assert len(report.failed_checks) == 0
    assert report.total_duration_ms >= 0

    for result in report.results:
        assert result.is_healthy
        assert result.duration_ms >= 0


def test_boot_not_completed(mock_device: MagicMock) -> None:
    mock_device.getprop.return_value = "0"

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert not report.is_healthy
    assert len(report.failed_checks) == 1
    assert report.has_failure("boot_completed")

    failure = report.failed_checks[0]
    assert failure.message.startswith("Boot not completed")


def test_package_manager_unavailable(mock_device: MagicMock) -> None:
    def shell_side_effect(cmd: list[str]) -> str:
        if "pm" in cmd:
            return "cmd: pm: not found"
        return "Service window: found"

    mock_device.shell.side_effect = shell_side_effect

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert not report.is_healthy
    assert report.has_failure("package_manager")


def test_system_server_missing(mock_device: MagicMock) -> None:
    mock_device.pidof.return_value = None

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert not report.is_healthy
    assert report.has_failure("system_server")
    failure = report.failed_checks[0]
    assert failure.message == "system_server process not found"


def test_ui_responsiveness_failure(mock_device: MagicMock) -> None:
    def shell_side_effect(cmd: list[str]) -> str:
        if "service" in cmd:
            return "Service window: not found"
        return "package:android"

    mock_device.shell.side_effect = shell_side_effect

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert not report.is_healthy
    assert report.has_failure("ui_responsiveness")


def test_network_failure(mock_device: MagicMock) -> None:
    def shell_side_effect(cmd: list[str]) -> str:
        if "ping" in cmd:
            raise AdbCommandError("ping timeout")
        return "Service window: found" if "service" in cmd else "package:android"

    mock_device.shell.side_effect = shell_side_effect

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert not report.is_healthy
    assert report.has_failure("network_connectivity")
    failure = next(r for r in report.results if r.check_name == "network_connectivity")
    assert failure.details == "ping timeout"


def test_device_offline(mock_device: MagicMock) -> None:
    mock_device.adb.get_state.return_value = "offline"
    mock_device.state = DeviceState.OFFLINE

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert not report.is_healthy
    assert not report.has_failure("adb_connectivity")
    assert report.has_failure("device_state")


def test_check_timeout_or_adb_failure(mock_device: MagicMock) -> None:
    mock_device.getprop.side_effect = AdbCommandError("Command timed out")

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert report.has_failure("boot_completed")
    failure = next(r for r in report.results if r.check_name == "boot_completed")
    assert "Failed to check boot property" in failure.message
    assert "Command timed out" in str(failure.details)


def test_multiple_checks_failed(mock_device: MagicMock) -> None:
    mock_device.getprop.return_value = "0"
    mock_device.pidof.return_value = None

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert not report.is_healthy
    assert len(report.failed_checks) == 2
    assert report.has_failure("boot_completed")
    assert report.has_failure("system_server")


def test_one_check_failing_does_not_prevent_later_checks(
    mock_device: MagicMock,
) -> None:
    mock_device.getprop.side_effect = Exception("Unexpected crash")

    monitor = DeviceHealthMonitor()
    report = monitor.check_health(mock_device)

    assert not report.is_healthy
    assert report.has_failure("boot_completed")

    # Later checks like system_server should still have run and passed
    assert not report.has_failure("system_server")
    assert next(r for r in report.results if r.check_name == "system_server").is_healthy


def test_custom_check_lists(mock_device: MagicMock) -> None:
    monitor = DeviceHealthMonitor([BootCompletedCheck(), SystemServerCheck()])
    report = monitor.check_health(mock_device)

    assert len(report.results) == 2
    assert report.results[0].check_name == "boot_completed"
    assert report.results[1].check_name == "system_server"


def test_configured_check_ordering(mock_device: MagicMock) -> None:
    monitor = DeviceHealthMonitor([SystemServerCheck(), BootCompletedCheck()])
    report = monitor.check_health(mock_device)

    assert len(report.results) == 2
    assert report.results[0].check_name == "system_server"
    assert report.results[1].check_name == "boot_completed"


def test_unexpected_exception_isolation(mock_device: MagicMock) -> None:
    class CrashingCheck(HealthCheck):
        name = "crashing_check"
        timeout = 5.0

        def run(self, device: AndroidDevice) -> HealthResult:
            raise ValueError("I crashed")

    monitor = DeviceHealthMonitor([CrashingCheck(), BootCompletedCheck()])
    report = monitor.check_health(mock_device)

    assert len(report.results) == 2
    assert report.has_failure("crashing_check")
    assert not report.has_failure("boot_completed")

    crash_result = report.results[0]
    assert crash_result.message == "Unexpected internal error during check"
    assert "I crashed" in str(crash_result.details)


def test_adb_connectivity_harness_error(mock_device: MagicMock) -> None:
    mock_device.adb.get_state.side_effect = AdbCommandError("ADB dead")
    monitor = DeviceHealthMonitor([AdbConnectivityCheck()])
    report = monitor.check_health(mock_device)
    assert not report.is_healthy
    assert report.has_failure("adb_connectivity")


def test_device_state_harness_error(mock_device: MagicMock) -> None:
    mock_device.refresh_info.side_effect = AdbCommandError("No device")
    monitor = DeviceHealthMonitor([DeviceStateCheck()])
    report = monitor.check_health(mock_device)
    assert not report.is_healthy
    assert report.has_failure("device_state")


def test_pm_harness_error(mock_device: MagicMock) -> None:
    mock_device.shell.side_effect = AdbCommandError("PM dead")
    monitor = DeviceHealthMonitor([PackageManagerCheck()])
    report = monitor.check_health(mock_device)
    assert not report.is_healthy
    assert report.has_failure("package_manager")


def test_system_server_harness_error(mock_device: MagicMock) -> None:
    mock_device.pidof.side_effect = AdbCommandError("PID check dead")
    monitor = DeviceHealthMonitor([SystemServerCheck()])
    report = monitor.check_health(mock_device)
    assert not report.is_healthy
    assert report.has_failure("system_server")


def test_ui_harness_error(mock_device: MagicMock) -> None:
    mock_device.shell.side_effect = AdbCommandError("UI dead")
    monitor = DeviceHealthMonitor([UiResponsivenessCheck()])
    report = monitor.check_health(mock_device)
    assert not report.is_healthy
    assert report.has_failure("ui_responsiveness")
