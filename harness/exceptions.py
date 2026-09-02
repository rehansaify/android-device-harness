"""Custom exceptions for the Android device harness."""


class HarnessError(Exception):
    """Base exception for all harness errors."""

    pass


class AdbCommandError(HarnessError):
    """Raised when an ADB command fails."""

    pass


class DeviceNotFoundError(HarnessError):
    """Raised when a specified device is not found or no devices are connected."""

    pass


class MultipleDevicesError(HarnessError):
    """Raised when multiple usable devices are found but one was expected."""

    pass


class DeviceHealthError(HarnessError):
    """Raised when a device fails health checks."""

    pass


class RecoveryFailedError(HarnessError):
    """Raised when device recovery attempts fail."""

    pass
