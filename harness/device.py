"""Device management and interaction."""

import logging
from typing import List, Optional, Union

from harness.adb import AdbWrapper
from harness.exceptions import (
    AdbCommandError,
    DeviceNotFoundError,
    MultipleDevicesError,
)
from harness.models import DeviceInfo, DeviceState

logger = logging.getLogger(__name__)


class AndroidDevice:
    """Represents a single Android device."""

    def __init__(self, serial: str, adb: AdbWrapper) -> None:
        self.serial = serial
        self.adb = adb

        # Metadata
        self.state: DeviceState = DeviceState.UNKNOWN
        self.model: Optional[str] = None
        self.manufacturer: Optional[str] = None
        self.android_version: Optional[str] = None
        self.sdk_version: Optional[int] = None
        self.build_fingerprint: Optional[str] = None

    def refresh_info(self) -> None:
        """Fetches device metadata via adb getprop and state."""
        try:
            state_str = self.adb.get_state(self.serial)
            if state_str == "device":
                self.state = DeviceState.ONLINE
            else:
                try:
                    self.state = DeviceState(state_str)
                except ValueError:
                    self.state = DeviceState.UNKNOWN
        except AdbCommandError:
            self.state = DeviceState.UNKNOWN

        if self.state == DeviceState.ONLINE:
            self.model = self.getprop("ro.product.model")
            self.manufacturer = self.getprop("ro.product.manufacturer")
            self.android_version = self.getprop("ro.build.version.release")

            sdk_str = self.getprop("ro.build.version.sdk")
            if sdk_str and sdk_str.isdigit():
                self.sdk_version = int(sdk_str)
            else:
                self.sdk_version = None

            self.build_fingerprint = self.getprop("ro.build.fingerprint")
        else:
            self.model = None
            self.manufacturer = None
            self.android_version = None
            self.sdk_version = None
            self.build_fingerprint = None

    def is_online(self) -> bool:
        """Returns True if the device is currently online and usable."""
        try:
            return self.adb.get_state(self.serial) == "device"
        except AdbCommandError:
            return False

    def getprop(self, property_name: str) -> str:
        return self.adb.getprop(self.serial, property_name)

    def shell(
        self, command: Union[str, List[str]], timeout: Optional[float] = None
    ) -> str:
        return self.adb.shell(self.serial, command, timeout=timeout)

    def pidof(self, package_name: str) -> Optional[int]:
        return self.adb.pidof(self.serial, package_name)

    def kill_process(self, pid: int, signal: int = 15) -> None:
        self.adb.kill_process(self.serial, pid, signal)

    def force_stop(self, package_name: str) -> None:
        self.adb.force_stop(self.serial, package_name)

    def launch_app(self, package_name: str) -> None:
        self.adb.start_app(self.serial, package_name)

    def reboot(self) -> None:
        self.adb.reboot(self.serial)

    def screenshot(self, output_path: str) -> None:
        self.adb.screenshot(self.serial, output_path)

    def logcat(self, lines: Optional[int] = None) -> str:
        return self.adb.logcat(self.serial, lines)


class DeviceManager:
    """Manages connected Android devices."""

    def __init__(self, adb: AdbWrapper) -> None:
        self.adb = adb

    def list_devices(self) -> List[DeviceInfo]:
        """Returns a list of all connected devices by parsing adb devices."""
        devices_out = self.adb.devices()
        lines = devices_out.splitlines()
        devices = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            serial = parts[0]
            state_str = parts[1].lower()
            if state_str == "device":
                state = DeviceState.ONLINE
            else:
                try:
                    state = DeviceState(state_str)
                except ValueError:
                    state = DeviceState.UNKNOWN

            model = None
            product = None

            # Identify transport/emulator
            is_emulator = (
                serial.startswith("emulator-")
                or serial.startswith("127.0.0.1:")
                or "emu" in serial
            )

            # Parse optional -l output if available
            for part in parts[2:]:
                if part.startswith("model:"):
                    model = part.split(":", 1)[1]
                elif part.startswith("product:"):
                    product = part.split(":", 1)[1]

            devices.append(
                DeviceInfo(
                    serial=serial,
                    state=state,
                    model=model,
                    product=product,
                    is_emulator=is_emulator,
                )
            )

        return devices

    def get_device(self, serial: Optional[str] = None) -> AndroidDevice:
        """
        Returns an AndroidDevice instance.
        If no serial is supplied, automatically selects the device if exactly one is usable.
        """
        devices = self.list_devices()

        if serial is not None:
            # Check if the requested serial actually exists in the adb list
            for info in devices:
                if info.serial == serial:
                    return AndroidDevice(serial, self.adb)
            raise DeviceNotFoundError(f"Device with serial '{serial}' not found.")

        # No serial supplied. Find usable devices (ONLINE)
        usable_devices = [d for d in devices if d.state == DeviceState.ONLINE]

        if len(usable_devices) == 0:
            raise DeviceNotFoundError("No usable online devices found.")
        elif len(usable_devices) > 1:
            raise MultipleDevicesError(
                f"Found {len(usable_devices)} usable devices. "
                "Please specify a serial number."
            )

        return AndroidDevice(usable_devices[0].serial, self.adb)
