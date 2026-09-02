"""Unit tests for the device module."""

from unittest.mock import MagicMock

import pytest

from harness.adb import AdbWrapper
from harness.device import AndroidDevice, DeviceManager
from harness.exceptions import (
    AdbCommandError,
    DeviceNotFoundError,
    MultipleDevicesError,
)
from harness.models import DeviceState


@pytest.fixture  # type: ignore
def mock_adb() -> MagicMock:
    return MagicMock(spec=AdbWrapper)


@pytest.fixture  # type: ignore
def device_manager(mock_adb: MagicMock) -> DeviceManager:
    return DeviceManager(adb=mock_adb)


def test_list_devices_empty(device_manager: DeviceManager, mock_adb: MagicMock) -> None:
    mock_adb.devices.return_value = "List of devices attached\n"
    devices = device_manager.list_devices()
    assert len(devices) == 0


def test_list_devices_one(device_manager: DeviceManager, mock_adb: MagicMock) -> None:
    mock_adb.devices.return_value = "List of devices attached\n12345\tdevice\n"
    devices = device_manager.list_devices()
    assert len(devices) == 1
    assert devices[0].serial == "12345"
    assert devices[0].state == DeviceState.ONLINE
    assert not devices[0].is_emulator


def test_list_devices_multiple(
    device_manager: DeviceManager, mock_adb: MagicMock
) -> None:
    mock_adb.devices.return_value = (
        "List of devices attached\n"
        "12345\tdevice\n"
        "67890\toffline\n"
        "abcde\tunauthorized\n"
    )
    devices = device_manager.list_devices()
    assert len(devices) == 3
    assert devices[0].serial == "12345"
    assert devices[0].state == DeviceState.ONLINE

    assert devices[1].serial == "67890"
    assert devices[1].state == DeviceState.OFFLINE

    assert devices[2].serial == "abcde"
    assert devices[2].state == DeviceState.UNAUTHORIZED


def test_list_devices_emulator(
    device_manager: DeviceManager, mock_adb: MagicMock
) -> None:
    mock_adb.devices.return_value = (
        "List of devices attached\n"
        "emulator-5554\tdevice product:sdk_gphone model:sdk_gphone\n"
    )
    devices = device_manager.list_devices()
    assert len(devices) == 1
    assert devices[0].serial == "emulator-5554"
    assert devices[0].is_emulator
    assert devices[0].product == "sdk_gphone"
    assert devices[0].model == "sdk_gphone"


def test_list_devices_unknown_state_and_invalid_line(
    device_manager: DeviceManager, mock_adb: MagicMock
) -> None:
    mock_adb.devices.return_value = (
        "List of devices attached\n"
        "12345\n"  # Invalid line, len < 2
        "67890\tunknownstate\n"  # Unknown state
    )
    devices = device_manager.list_devices()
    assert len(devices) == 1
    assert devices[0].serial == "67890"
    assert devices[0].state == DeviceState.UNKNOWN


def test_get_device_explicit_serial(
    device_manager: DeviceManager, mock_adb: MagicMock
) -> None:
    mock_adb.devices.return_value = "List of devices attached\n12345\tdevice\n"
    device = device_manager.get_device("12345")
    assert device.serial == "12345"


def test_get_device_explicit_serial_not_found(
    device_manager: DeviceManager, mock_adb: MagicMock
) -> None:
    mock_adb.devices.return_value = "List of devices attached\n12345\tdevice\n"
    with pytest.raises(DeviceNotFoundError):
        device_manager.get_device("99999")


def test_get_device_auto_one_usable(
    device_manager: DeviceManager, mock_adb: MagicMock
) -> None:
    mock_adb.devices.return_value = (
        "List of devices attached\n" "12345\tdevice\n" "67890\toffline\n"
    )
    device = device_manager.get_device()
    assert device.serial == "12345"


def test_get_device_auto_zero_usable(
    device_manager: DeviceManager, mock_adb: MagicMock
) -> None:
    mock_adb.devices.return_value = "List of devices attached\n" "67890\toffline\n"
    with pytest.raises(DeviceNotFoundError):
        device_manager.get_device()


def test_get_device_auto_multiple_usable(
    device_manager: DeviceManager, mock_adb: MagicMock
) -> None:
    mock_adb.devices.return_value = (
        "List of devices attached\n" "12345\tdevice\n" "67890\tdevice\n"
    )
    with pytest.raises(MultipleDevicesError):
        device_manager.get_device()


def test_android_device_refresh_info_online(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)

    mock_adb.get_state.return_value = "device"

    def mock_getprop(serial: str, prop: str) -> str:
        props = {
            "ro.product.model": "Pixel 5",
            "ro.product.manufacturer": "Google",
            "ro.build.version.release": "12",
            "ro.build.version.sdk": "31",
            "ro.build.fingerprint": "google/redfin/redfin:12/SP1A.210812.015/7671067:user/release-keys",
        }
        return props.get(prop, "")

    mock_adb.getprop.side_effect = mock_getprop

    device.refresh_info()

    assert device.state == DeviceState.ONLINE
    assert device.model == "Pixel 5"
    assert device.manufacturer == "Google"
    assert device.android_version == "12"
    assert device.sdk_version == 31
    assert (
        device.build_fingerprint
        == "google/redfin/redfin:12/SP1A.210812.015/7671067:user/release-keys"
    )
    mock_adb.get_state.assert_called_once_with("12345")


def test_android_device_refresh_info_offline(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    mock_adb.get_state.return_value = "offline"

    device.refresh_info()

    assert device.state == DeviceState.OFFLINE
    assert device.model is None
    assert device.sdk_version is None
    # Ensure getprop was not called
    mock_adb.getprop.assert_not_called()


def test_android_device_refresh_info_unknown_state(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    mock_adb.get_state.return_value = "blabla"
    device.refresh_info()
    assert device.state == DeviceState.UNKNOWN
    assert device.model is None


def test_android_device_refresh_info_nondigit_sdk(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    mock_adb.get_state.return_value = "device"

    def mock_getprop(serial: str, prop: str) -> str:
        if prop == "ro.build.version.sdk":
            return "not_a_number"
        return "value"

    mock_adb.getprop.side_effect = mock_getprop
    device.refresh_info()
    assert device.state == DeviceState.ONLINE
    assert device.sdk_version is None


def test_android_device_refresh_info_adb_error(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    mock_adb.get_state.side_effect = AdbCommandError("offline")
    device.refresh_info()
    assert device.state == DeviceState.UNKNOWN
    assert device.model is None


def test_android_device_is_online(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)

    mock_adb.get_state.return_value = "device"
    assert device.is_online()
    mock_adb.get_state.assert_called_with("12345")

    mock_adb.get_state.return_value = "offline"
    assert not device.is_online()

    mock_adb.get_state.side_effect = AdbCommandError("error")
    assert not device.is_online()


def test_android_device_shell(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    mock_adb.shell.return_value = "output"

    # Test without timeout
    result = device.shell("ls -l")
    assert result == "output"
    mock_adb.shell.assert_called_with("12345", "ls -l", timeout=None)

    # Test with timeout
    result_with_timeout = device.shell("ls -l", timeout=5.0)
    assert result_with_timeout == "output"
    mock_adb.shell.assert_called_with("12345", "ls -l", timeout=5.0)


def test_android_device_pidof(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    mock_adb.pidof.return_value = 4242

    assert device.pidof("com.example.app") == 4242
    mock_adb.pidof.assert_called_once_with("12345", "com.example.app")


def test_android_device_kill_process(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    device.kill_process(4242, signal=9)
    mock_adb.kill_process.assert_called_once_with("12345", 4242, 9)


def test_android_device_force_stop(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    device.force_stop("com.example.app")
    mock_adb.force_stop.assert_called_once_with("12345", "com.example.app")


def test_android_device_launch_app(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    device.launch_app("com.example.app")
    mock_adb.start_app.assert_called_once_with("12345", "com.example.app")


def test_android_device_reboot(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    device.reboot()
    mock_adb.reboot.assert_called_once_with("12345")


def test_android_device_screenshot(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    device.screenshot("/path/to/shot.png")
    mock_adb.screenshot.assert_called_once_with("12345", "/path/to/shot.png")


def test_android_device_logcat(mock_adb: MagicMock) -> None:
    device = AndroidDevice("12345", mock_adb)
    mock_adb.logcat.return_value = "logs"

    assert device.logcat(lines=100) == "logs"
    mock_adb.logcat.assert_called_once_with("12345", 100)
