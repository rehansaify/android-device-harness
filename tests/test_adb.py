"""Unit tests for the adb wrapper."""

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from harness.adb import AdbWrapper
from harness.exceptions import AdbCommandError


@pytest.fixture  # type: ignore
def adb() -> AdbWrapper:
    return AdbWrapper(adb_path="mock_adb", default_timeout=5.0)


def test_start_server(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adb.start_server()
        mock_run.assert_called_once_with(
            ["mock_adb", "start-server"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_kill_server(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adb.kill_server()
        mock_run.assert_called_once_with(
            ["mock_adb", "kill-server"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_devices(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="List of devices\n123 device\n", stderr=""
        )
        out = adb.devices()
        assert out == "List of devices\n123 device"
        mock_run.assert_called_once_with(
            ["mock_adb", "devices"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_get_state(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="device\n", stderr="")
        out = adb.get_state("123")
        assert out == "device"
        mock_run.assert_called_once_with(
            ["mock_adb", "-s", "123", "get-state"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_run_success(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="success\n", stderr="")
        result = adb._run(["mock_adb", "devices"])
        assert result.stdout.strip() == "success"
        mock_run.assert_called_once_with(
            ["mock_adb", "devices"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_run_missing_executable(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError(
            "No such file or directory: 'mock_adb'"
        )
        with pytest.raises(AdbCommandError) as exc:
            adb._run(["mock_adb", "devices"])
        assert "ADB executable not found" in str(exc.value)


def test_run_timeout(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["mock_adb", "devices"], timeout=5.0
        )
        with pytest.raises(AdbCommandError) as exc:
            adb._run(["mock_adb", "devices"])
        assert "Command timed out" in str(exc.value)


def test_run_nonzero_exit(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="some error")
        with pytest.raises(AdbCommandError) as exc:
            adb._run(["mock_adb", "devices"])
        assert "exit code 1" in str(exc.value)
        assert "some error" in str(exc.value)


def test_run_offline_device(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: device offline"
        )
        with pytest.raises(AdbCommandError) as exc:
            adb.shell("123", "ls")
        assert "Device offline" in str(exc.value)


def test_run_unauthorized_device(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: device unauthorized"
        )
        with pytest.raises(AdbCommandError) as exc:
            adb.shell("123", "ls")
        assert "Device unauthorized" in str(exc.value)


def test_getprop(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="30\n", stderr="")
        assert adb.getprop("123", "ro.build.version.sdk") == "30"
        mock_run.assert_called_once_with(
            ["mock_adb", "-s", "123", "shell", "getprop", "ro.build.version.sdk"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_pidof_found(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="1234 5678\n", stderr="")
        assert adb.pidof("123", "com.example.app") == 1234


def test_pidof_not_found(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        assert adb.pidof("123", "com.example.app") is None


def test_pidof_empty(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        assert adb.pidof("123", "com.example.app") is None


def test_kill_process(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adb.kill_process("123", 1234, signal=9)
        mock_run.assert_called_once_with(
            ["mock_adb", "-s", "123", "shell", "kill", "-9", "1234"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_force_stop(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adb.force_stop("123", "com.example.app")
        mock_run.assert_called_once_with(
            ["mock_adb", "-s", "123", "shell", "am", "force-stop", "com.example.app"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_start_app(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adb.start_app("123", "com.example.app")
        mock_run.assert_called_once_with(
            [
                "mock_adb",
                "-s",
                "123",
                "shell",
                "monkey",
                "-p",
                "com.example.app",
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_reboot(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adb.reboot("123")
        mock_run.assert_called_once_with(
            ["mock_adb", "-s", "123", "reboot"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_screenshot(adb: AdbWrapper, tmp_path: Any) -> None:
    with patch("subprocess.run") as mock_run:

        def mock_run_side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            if "stdout" in kwargs and hasattr(kwargs["stdout"], "write"):
                kwargs["stdout"].write(b"\x89PNG\r\n\x1a\nfake_image_data")
            return MagicMock(returncode=0, stdout=None, stderr=b"")

        mock_run.side_effect = mock_run_side_effect
        output_file = tmp_path / "screenshots" / "test.png"
        adb.screenshot("123", str(output_file))

        # Check call arguments
        call_args = mock_run.call_args[1]
        assert call_args["text"] is False
        assert call_args["capture_output"] is False
        assert "stdout" in call_args

        # Verify output was written to file and exactly matches the fake binary payload
        assert output_file.exists()
        content = output_file.read_bytes()
        assert content.startswith(b"\x89PNG\r\n\x1a\n")
        assert content == b"\x89PNG\r\n\x1a\nfake_image_data"


def test_wait_for_device(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        adb.wait_for_device("123", timeout=10.0)
        mock_run.assert_called_once_with(
            ["mock_adb", "-s", "123", "wait-for-device"],
            timeout=10.0,
            check=False,
            text=True,
            capture_output=True,
        )


def test_logcat(adb: AdbWrapper) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="log line 1\nlog line 2", stderr=""
        )
        out = adb.logcat("123", lines=2)
        assert out == "log line 1\nlog line 2"
        mock_run.assert_called_once_with(
            ["mock_adb", "-s", "123", "logcat", "-d", "-t", "2"],
            timeout=5.0,
            check=False,
            text=True,
            capture_output=True,
        )
