"""Unit tests for the recovery engine."""

from unittest.mock import MagicMock, call

import pytest

from harness.device import AndroidDevice
from harness.exceptions import HarnessError
from harness.health import DeviceHealthMonitor
from harness.models import HealthReport, HealthResult, RecoveryStepResult
from harness.recovery import (
    RebootDeviceStep,
    ReconnectAdbStep,
    RecoveryEngine,
    RestartFrameworkStep,
)


@pytest.fixture
def mock_device() -> MagicMock:
    device = MagicMock(spec=AndroidDevice)
    device.serial = "123"
    device.adb = MagicMock()
    return device


@pytest.fixture
def mock_health_monitor() -> MagicMock:
    return MagicMock(spec=DeviceHealthMonitor)


@pytest.fixture
def healthy_report() -> HealthReport:
    return HealthReport(
        serial="123",
        results=[
            HealthResult(
                check_name="dummy", is_healthy=True, duration_ms=10, message="OK"
            )
        ],
        total_duration_ms=10,
    )


@pytest.fixture
def unhealthy_report() -> HealthReport:
    return HealthReport(
        serial="123",
        results=[
            HealthResult(
                check_name="dummy", is_healthy=False, duration_ms=10, message="FAIL"
            )
        ],
        total_duration_ms=10,
    )


def test_recovery_engine_healthy_initial(
    mock_device: MagicMock, mock_health_monitor: MagicMock, healthy_report: HealthReport
) -> None:
    engine = RecoveryEngine(mock_health_monitor)
    report = engine.recover(mock_device, healthy_report)

    assert report.successful is True
    assert len(report.steps) == 0
    assert report.final_health == healthy_report
    mock_health_monitor.check_health.assert_not_called()


def test_recovery_engine_successful_first_stage(
    mock_device: MagicMock,
    mock_health_monitor: MagicMock,
    healthy_report: HealthReport,
    unhealthy_report: HealthReport,
) -> None:
    # First health check after step 1 returns healthy
    mock_health_monitor.check_health.return_value = healthy_report

    step1 = MagicMock()
    step1.name = "step1"
    step1.run.return_value = RecoveryStepResult("step1", True, 100, "OK")

    step2 = MagicMock()
    step2.name = "step2"

    engine = RecoveryEngine(mock_health_monitor, steps=[step1, step2])
    report = engine.recover(mock_device, unhealthy_report)

    assert report.successful is True
    assert len(report.steps) == 1
    assert report.steps[0].step_name == "step1"
    assert report.final_health == healthy_report

    step1.run.assert_called_once_with(mock_device)
    step2.run.assert_not_called()
    mock_health_monitor.check_health.assert_called_once_with(mock_device)


def test_recovery_engine_escalation(
    mock_device: MagicMock,
    mock_health_monitor: MagicMock,
    healthy_report: HealthReport,
    unhealthy_report: HealthReport,
) -> None:
    # First check returns unhealthy, second check returns healthy
    mock_health_monitor.check_health.side_effect = [unhealthy_report, healthy_report]

    step1 = MagicMock()
    step1.name = "step1"
    step1.run.return_value = RecoveryStepResult("step1", False, 100, "FAIL")

    step2 = MagicMock()
    step2.name = "step2"
    step2.run.return_value = RecoveryStepResult("step2", True, 100, "OK")

    engine = RecoveryEngine(mock_health_monitor, steps=[step1, step2])
    report = engine.recover(mock_device, unhealthy_report)

    assert report.successful is True
    assert len(report.steps) == 2
    assert report.steps[0].step_name == "step1"
    assert report.steps[1].step_name == "step2"
    assert report.final_health == healthy_report

    step1.run.assert_called_once_with(mock_device)
    step2.run.assert_called_once_with(mock_device)
    assert mock_health_monitor.check_health.call_count == 2


def test_recovery_engine_complete_failure(
    mock_device: MagicMock,
    mock_health_monitor: MagicMock,
    unhealthy_report: HealthReport,
) -> None:
    # Always returns unhealthy
    mock_health_monitor.check_health.return_value = unhealthy_report

    step1 = MagicMock()
    step1.name = "step1"
    step1.run.return_value = RecoveryStepResult("step1", False, 100, "FAIL")

    engine = RecoveryEngine(mock_health_monitor, steps=[step1])
    report = engine.recover(mock_device, unhealthy_report)

    assert report.successful is False
    assert len(report.steps) == 1
    assert report.final_health == unhealthy_report
    step1.run.assert_called_once_with(mock_device)
    mock_health_monitor.check_health.assert_called_once_with(mock_device)


def test_recovery_engine_handles_step_exception(
    mock_device: MagicMock,
    mock_health_monitor: MagicMock,
    unhealthy_report: HealthReport,
) -> None:
    mock_health_monitor.check_health.return_value = unhealthy_report

    step1 = MagicMock()
    step1.name = "step1"
    step1.run.side_effect = RuntimeError("Crash")

    engine = RecoveryEngine(mock_health_monitor, steps=[step1])
    report = engine.recover(mock_device, unhealthy_report)

    assert report.successful is False
    assert len(report.steps) == 1
    assert report.steps[0].success is False
    assert "Unexpected internal error" in report.steps[0].message
    assert "Crash" in str(report.steps[0].details)


def test_reconnect_adb_step_success(mock_device: MagicMock) -> None:
    step = ReconnectAdbStep()
    result = step.run(mock_device)

    assert result.success is True
    mock_device.adb.kill_server.assert_called_once()
    mock_device.adb.start_server.assert_called_once()
    mock_device.adb.wait_for_device.assert_called_once_with("123", timeout=10.0)


def test_reconnect_adb_step_failure(mock_device: MagicMock) -> None:
    mock_device.adb.wait_for_device.side_effect = HarnessError("Timeout")
    step = ReconnectAdbStep()
    result = step.run(mock_device)

    assert result.success is False
    assert "Timeout" in str(result.details)


def test_restart_framework_step_success(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mock time.sleep to avoid waiting during tests
    monkeypatch.setattr("time.sleep", lambda x: None)

    # Mock getprop to simulate immediate boot completion
    mock_device.getprop.return_value = "1"

    step = RestartFrameworkStep()
    result = step.run(mock_device)

    assert result.success is True
    mock_device.shell.assert_has_calls(
        [call(["stop"], timeout=10.0), call(["start"], timeout=10.0)]
    )


def test_restart_framework_step_timeout(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    # Fast-forward time to simulate timeout
    import time

    original_monotonic = time.monotonic
    times = [0.0, 0.0, 31.0]  # start, first loop check, timeout check
    monkeypatch.setattr("time.monotonic", lambda: times.pop(0) if times else 32.0)

    mock_device.getprop.return_value = "0"

    step = RestartFrameworkStep()
    result = step.run(mock_device)

    assert result.success is False
    assert "did not complete boot" in result.message


def test_restart_framework_step_harness_error(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)
    mock_device.shell.side_effect = HarnessError("Command failed")

    step = RestartFrameworkStep()
    result = step.run(mock_device)

    assert result.success is False
    assert "Command failed" in str(result.details)


def test_reboot_device_step_success(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)
    mock_device.getprop.return_value = "1"

    step = RebootDeviceStep()
    result = step.run(mock_device)

    assert result.success is True
    mock_device.reboot.assert_called_once()
    mock_device.adb.wait_for_device.assert_called_once_with("123", timeout=60.0)


def test_reboot_device_step_harness_error_on_boot_check(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)

    import time

    times = [
        0.0,
        0.0,
        0.0,
        61.0,
    ]  # start, wait_for_device start, first loop check, timeout check
    monkeypatch.setattr("time.monotonic", lambda: times.pop(0) if times else 62.0)

    # getprop throws error on first try, then it times out
    mock_device.getprop.side_effect = HarnessError("Device offline")

    step = RebootDeviceStep()
    result = step.run(mock_device)

    assert result.success is False
    assert "boot not completed" in result.message


def test_reboot_device_step_harness_error(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", lambda x: None)
    mock_device.reboot.side_effect = HarnessError("Reboot failed")

    step = RebootDeviceStep()
    result = step.run(mock_device)

    assert result.success is False
    assert "Failed to reboot device" in result.message


def test_restart_framework_step_timeout_and_error(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:

    monkeypatch.setattr("time.sleep", lambda x: None)

    import time

    times = [0.0, 0.0, 0.0, 31.0]

    monkeypatch.setattr("time.monotonic", lambda: times.pop(0) if times else 32.0)

    mock_device.getprop.side_effect = [HarnessError("Not ready"), "0", "0"]

    step = RestartFrameworkStep()

    result = step.run(mock_device)

    assert result.success is False
