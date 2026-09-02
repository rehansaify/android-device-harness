"""Unit tests for the execution engine."""

from unittest.mock import MagicMock, create_autospec

import pytest

from harness.device import AndroidDevice, DeviceManager
from harness.exceptions import HarnessError
from harness.executor import InstrumentationTestRunner, TestExecutor
from harness.health import DeviceHealthMonitor
from harness.models import HealthReport, HealthResult, RecoveryReport, TestResult
from harness.recovery import RecoveryEngine


@pytest.fixture
def mock_device() -> MagicMock:
    device = create_autospec(AndroidDevice, instance=True)
    device.serial = "123"
    return device


@pytest.fixture
def mock_device_manager(mock_device: MagicMock) -> MagicMock:
    manager = MagicMock(spec=DeviceManager)
    manager.get_device.return_value = mock_device
    return manager


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


def test_instrumentation_test_runner_success(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.monotonic", lambda: 0.0)
    mock_device.shell.return_value = "OK (1 test)"

    runner = InstrumentationTestRunner(timeout=10.0)
    result = runner.run(mock_device, "com.example.test")

    assert result.passed is True
    assert result.test_name == "com.example.test"
    assert result.error_message is None
    assert result.logs == "OK (1 test)"
    mock_device.shell.assert_called_once_with(
        ["am", "instrument", "-w", "com.example.test"], timeout=10.0
    )


def test_instrumentation_test_runner_failure(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.monotonic", lambda: 0.0)
    mock_device.shell.return_value = "FAILURES!!! Tests run: 1,  Failures: 1"

    runner = InstrumentationTestRunner()
    result = runner.run(mock_device, "com.example.test")

    assert result.passed is False
    assert result.error_message is not None
    assert "failures" in result.error_message.lower()


def test_instrumentation_test_runner_exception(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.monotonic", lambda: 0.0)
    mock_device.shell.return_value = "java.lang.Exception: Process crashed."

    runner = InstrumentationTestRunner()
    result = runner.run(mock_device, "com.example.test")

    assert result.passed is False


def test_instrumentation_test_runner_adb_error(
    mock_device: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.monotonic", lambda: 0.0)
    mock_device.shell.side_effect = HarnessError("Timeout")

    runner = InstrumentationTestRunner()
    result = runner.run(mock_device, "com.example.test")

    assert result.passed is False
    assert "Execution failed" in result.error_message


def test_executor_device_acquisition_failure(
    mock_device_manager: MagicMock,
) -> None:
    mock_device_manager.get_device.side_effect = HarnessError("No devices")

    executor = TestExecutor(device_manager=mock_device_manager)
    results = executor.run_tests(None, ["test1", "test2"])

    assert len(results) == 2
    assert not results[0].passed
    assert "Device acquisition failed" in results[0].error_message


def test_executor_healthy_run(
    mock_device_manager: MagicMock,
    mock_device: MagicMock,
    healthy_report: HealthReport,
) -> None:
    mock_health = MagicMock(spec=DeviceHealthMonitor)
    mock_health.check_health.return_value = healthy_report

    mock_recovery = MagicMock(spec=RecoveryEngine)
    mock_runner = MagicMock()
    mock_runner.run.return_value = TestResult("test1", True, 100)

    executor = TestExecutor(
        device_manager=mock_device_manager,
        health_monitor=mock_health,
        recovery_engine=mock_recovery,
        test_runner=mock_runner,
    )
    results = executor.run_tests("123", ["test1"])

    assert len(results) == 1
    assert results[0].passed is True
    mock_health.check_health.assert_called_once_with(mock_device)
    mock_recovery.recover.assert_not_called()
    mock_runner.run.assert_called_once_with(mock_device, "test1")


def test_executor_unhealthy_recovery_success(
    mock_device_manager: MagicMock,
    mock_device: MagicMock,
    unhealthy_report: HealthReport,
    healthy_report: HealthReport,
) -> None:
    mock_health = MagicMock(spec=DeviceHealthMonitor)
    mock_health.check_health.return_value = unhealthy_report

    mock_recovery = MagicMock(spec=RecoveryEngine)
    mock_recovery.recover.return_value = RecoveryReport(
        serial="123",
        successful=True,
        steps=[],
        final_health=healthy_report,
        total_duration_ms=100,
    )

    mock_runner = MagicMock()
    mock_runner.run.return_value = TestResult("test1", True, 100)

    executor = TestExecutor(
        device_manager=mock_device_manager,
        health_monitor=mock_health,
        recovery_engine=mock_recovery,
        test_runner=mock_runner,
    )
    results = executor.run_tests("123", ["test1"])

    assert len(results) == 1
    assert results[0].passed is True
    mock_health.check_health.assert_called_once_with(mock_device)
    mock_recovery.recover.assert_called_once_with(mock_device, unhealthy_report)
    mock_runner.run.assert_called_once_with(mock_device, "test1")


def test_executor_unhealthy_recovery_failure(
    mock_device_manager: MagicMock,
    mock_device: MagicMock,
    unhealthy_report: HealthReport,
) -> None:
    mock_health = MagicMock(spec=DeviceHealthMonitor)
    mock_health.check_health.return_value = unhealthy_report

    mock_recovery = MagicMock(spec=RecoveryEngine)
    mock_recovery.recover.return_value = RecoveryReport(
        serial="123",
        successful=False,
        steps=[],
        final_health=unhealthy_report,
        total_duration_ms=100,
    )

    mock_runner = MagicMock()

    executor = TestExecutor(
        device_manager=mock_device_manager,
        health_monitor=mock_health,
        recovery_engine=mock_recovery,
        test_runner=mock_runner,
    )
    results = executor.run_tests("123", ["test1", "test2"])

    assert len(results) == 2
    assert not results[0].passed
    assert "recovery failed" in results[0].error_message
    mock_health.check_health.assert_called_once_with(mock_device)
    mock_recovery.recover.assert_called_once_with(mock_device, unhealthy_report)
    mock_runner.run.assert_not_called()
