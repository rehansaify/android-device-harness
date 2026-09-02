"""Unit tests for the command-line interface."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from harness.cli import build_parser, main
from harness.exceptions import HarnessError, MultipleDevicesError
from harness.models import (
    DeviceInfo,
    DeviceState,
    HealthReport,
    HealthResult,
    RecoveryReport,
    TestResult,
)


@pytest.fixture
def mock_device_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_health_monitor() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_recovery_engine() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_executor() -> MagicMock:
    return MagicMock()


@pytest.fixture
def patch_framework(
    mock_device_manager: MagicMock,
    mock_health_monitor: MagicMock,
    mock_recovery_engine: MagicMock,
    mock_executor: MagicMock,
) -> Any:
    with (
        patch("harness.cli.DeviceManager", return_value=mock_device_manager),
        patch("harness.cli.DeviceHealthMonitor", return_value=mock_health_monitor),
        patch("harness.cli.RecoveryEngine", return_value=mock_recovery_engine),
        patch("harness.cli.TestExecutor", return_value=mock_executor),
    ):
        yield {
            "device_manager": mock_device_manager,
            "health_monitor": mock_health_monitor,
            "recovery_engine": mock_recovery_engine,
            "executor": mock_executor,
        }


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    # argparse raises SystemExit on --help
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(["--help"])
    assert e.value.code == 0

    # main catches SystemExit from parse_args
    assert main(["--help"]) == 0
    captured = capsys.readouterr()
    assert "Android Device Harness" in captured.out


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    captured = capsys.readouterr()
    assert "android-device-harness" in captured.out


def test_cli_devices_one_device(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.list_devices.return_value = [
        DeviceInfo(serial="123", state=DeviceState.ONLINE, model="Pixel 7")
    ]

    assert main(["devices"]) == 0
    captured = capsys.readouterr()
    assert "123" in captured.out
    assert "Pixel 7" in captured.out
    assert "online" in captured.out


def test_cli_devices_no_devices(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.list_devices.return_value = []

    assert main(["devices"]) == 0
    captured = capsys.readouterr()
    assert "No devices connected" in captured.out


def test_cli_devices_json(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.list_devices.return_value = [DeviceInfo(serial="123", state=DeviceState.ONLINE)]

    assert main(["devices", "--output", "json"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 1
    assert data[0]["serial"] == "123"
    assert data[0]["state"] == "online"


def test_cli_devices_error(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.list_devices.side_effect = HarnessError("ADB ded")

    assert main(["devices"]) == 3
    captured = capsys.readouterr()
    assert "ADB ded" in captured.err


def test_cli_health_success(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    health_mon = patch_framework["health_monitor"]

    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    health_mon.check_health.return_value = HealthReport(
        "123", [HealthResult("chk", True, 10, "OK")], 10
    )

    assert main(["health"]) == 0
    captured = capsys.readouterr()
    assert "Healthy" in captured.out


def test_cli_health_failure(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    health_mon = patch_framework["health_monitor"]

    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    health_mon.check_health.return_value = HealthReport(
        "123", [HealthResult("chk", False, 10, "FAIL")], 10
    )

    assert main(["health", "--serial", "123"]) == 1
    captured = capsys.readouterr()
    assert "Unhealthy" in captured.out


def test_cli_health_multiple_devices_error(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.get_device.side_effect = MultipleDevicesError("Too many")

    assert main(["health"]) == 2
    captured = capsys.readouterr()
    assert "Too many" in captured.err
    assert "Please specify --serial" in captured.err


def test_cli_health_report_output(patch_framework: dict, tmp_path: Any) -> None:
    mgr = patch_framework["device_manager"]
    health_mon = patch_framework["health_monitor"]
    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device
    health_mon.check_health.return_value = HealthReport(
        "123", [HealthResult("chk", True, 10, "OK")], 10
    )

    report_file = tmp_path / "report.json"
    assert main(["health", "--report", str(report_file)]) == 0
    assert report_file.exists()


def test_cli_recover_success(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    health_mon = patch_framework["health_monitor"]
    rec_eng = patch_framework["recovery_engine"]

    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    health = HealthReport("123", [], 0)
    health_mon.check_health.return_value = health

    rec_eng.recover.return_value = RecoveryReport("123", True, [], health, 0)

    assert main(["recover", "--serial", "123"]) == 0
    captured = capsys.readouterr()
    assert "recovered after failure" in captured.out


def test_cli_recover_failure(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    rec_eng = patch_framework["recovery_engine"]

    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    health = HealthReport("123", [], 0)
    rec_eng.recover.return_value = RecoveryReport("123", False, [], health, 0)

    assert main(["recover", "--serial", "123"]) == 1
    captured = capsys.readouterr()
    assert "recovery failed" in captured.out


def test_cli_run_success(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    executor = patch_framework["executor"]
    executor.run_tests.return_value = [TestResult("t1", True, 100)]

    assert main(["run", "t1"]) == 0
    captured = capsys.readouterr()
    assert "Passed:  1" in captured.out
    assert "Failed:  0" in captured.out


def test_cli_run_failure(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    executor = patch_framework["executor"]
    executor.run_tests.return_value = [
        TestResult("t1", False, 100, error_message="boom")
    ]

    assert main(["run", "t1"]) == 1
    captured = capsys.readouterr()
    assert "Failed:  1" in captured.out


def test_cli_run_harness_error(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    executor = patch_framework["executor"]
    executor.run_tests.side_effect = HarnessError("ADB broken")

    assert main(["run", "t1", "--verbose"]) == 3
    captured = capsys.readouterr()
    assert "Execution Error: ADB broken" in captured.err


def test_cli_unexpected_exception(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.list_devices.side_effect = RuntimeError("Something terrible")

    assert main(["devices"]) == 3
    captured = capsys.readouterr()
    assert (
        "Unexpected framework error" not in captured.err
    )  # we print traceback directly now
    assert "RuntimeError: Something terrible" in captured.err


def test_cli_invalid_args() -> None:
    assert main(["not-a-command"]) == 2


def test_cli_get_version_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.metadata

    def mock_version(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError()

    monkeypatch.setattr(importlib.metadata, "version", mock_version)
    from harness.cli import get_version

    assert get_version() == "unknown"


def test_cli_devices_missing_info(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.list_devices.return_value = [
        DeviceInfo(serial="123", state=DeviceState.OFFLINE)
    ]

    assert main(["devices"]) == 0
    captured = capsys.readouterr()
    assert "✗ 123" in captured.out


def test_cli_health_json_and_report(
    patch_framework: dict, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    health_mon = patch_framework["health_monitor"]
    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device
    health_mon.check_health.return_value = HealthReport(
        "123", [HealthResult("chk", True, 10, "OK")], 10
    )

    report_file = tmp_path / "report.json"
    assert (
        main(
            [
                "health",
                "--serial",
                "123",
                "--output",
                "json",
                "--report",
                str(report_file),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert "summary" in captured.out
    assert report_file.exists()


def test_cli_health_harness_error(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.get_device.side_effect = HarnessError("Fail")

    assert main(["health", "--serial", "123"]) == 3
    captured = capsys.readouterr()
    assert "Fail" in captured.err


def test_cli_recover_json_and_report(
    patch_framework: dict, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    health_mon = patch_framework["health_monitor"]
    rec_eng = patch_framework["recovery_engine"]

    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    health = HealthReport("123", [], 0)
    health_mon.check_health.return_value = health

    rec_eng.recover.return_value = RecoveryReport("123", True, [], health, 0)

    report_file = tmp_path / "report_rec.json"
    assert (
        main(
            [
                "recover",
                "--serial",
                "123",
                "--output",
                "json",
                "--report",
                str(report_file),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert "successful" in captured.out
    assert report_file.exists()


def test_cli_recover_errors(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.get_device.side_effect = MultipleDevicesError("Too many")
    assert main(["recover"]) == 2

    mgr.get_device.side_effect = HarnessError("Fail")
    assert main(["recover", "--serial", "123"]) == 3


def test_cli_run_json_and_report(
    patch_framework: dict, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    device = MagicMock()
    device.serial = "123"
    mgr.get_device.return_value = device

    executor = patch_framework["executor"]
    executor.run_tests.return_value = [TestResult("t1", True, 100)]

    report_file = tmp_path / "report_run.json"
    assert (
        main(
            [
                "run",
                "t1",
                "--serial",
                "123",
                "--output",
                "json",
                "--report",
                str(report_file),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert "t1" in captured.out
    assert report_file.exists()


def test_cli_run_errors(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.get_device.side_effect = MultipleDevicesError("Too many")
    assert main(["run", "t1"]) == 2

    executor = patch_framework["executor"]
    executor.run_tests.side_effect = HarnessError("Fail")
    assert main(["run", "t1", "--serial", "123"]) == 3


def test_cli_main_not_called_directly() -> None:
    # Just to touch the __main__ block for coverage, but we can't easily mock __name__ in a clean way without subprocess.
    # It's usually fine to skip coverage on `if __name__ == "__main__":`
    pass


def test_cli_devices_all_info(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.list_devices.return_value = [
        DeviceInfo(
            serial="123",
            state=DeviceState.ONLINE,
            model="M",
            os_version="12",
            api_level=31,
        )
    ]
    assert main(["devices"]) == 0
    assert "Android: 12" in capsys.readouterr().out


def test_cli_recover_harness_error(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.get_device.side_effect = HarnessError("Fail")
    assert main(["recover"]) == 3


def test_cli_run_get_device_harness_error(
    patch_framework: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    mgr = patch_framework["device_manager"]
    mgr.get_device.side_effect = HarnessError("Fail")
    assert main(["run", "t1"]) == 3
