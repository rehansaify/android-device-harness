"""Data models for the Android device harness."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class DeviceState(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    RECOVERY = "recovery"
    BOOTLOADER = "bootloader"
    UNKNOWN = "unknown"


@dataclass
class DeviceInfo:
    """Information about an Android device."""

    serial: str
    state: DeviceState
    model: Optional[str] = None
    product: Optional[str] = None
    is_emulator: bool = False
    os_version: Optional[str] = None
    api_level: Optional[int] = None


@dataclass
class HealthStatus:
    """Legacy health status (kept for compatibility)."""

    is_healthy: bool
    checks_passed: int
    checks_failed: int
    issues: List[str] = field(default_factory=list)


@dataclass
class HealthResult:
    """The result of a single health check."""

    check_name: str
    is_healthy: bool
    duration_ms: int
    message: str
    details: Optional[str] = None


@dataclass
class HealthReport:
    """Comprehensive report of a device's health."""

    serial: str
    results: List[HealthResult]
    total_duration_ms: int

    @property
    def is_healthy(self) -> bool:
        return all(r.is_healthy for r in self.results)

    @property
    def failed_checks(self) -> List[HealthResult]:
        return [r for r in self.results if not r.is_healthy]

    def has_failure(self, name: str) -> bool:
        return any(not r.is_healthy for r in self.results if r.check_name == name)


@dataclass
class TestResult:
    """The result of a test execution."""

    test_name: str
    passed: bool
    duration_ms: int
    error_message: Optional[str] = None
    logs: Optional[str] = None


@dataclass
class RecoveryStepResult:
    """The result of a single recovery step attempt."""

    step_name: str
    success: bool
    duration_ms: int
    message: str
    details: Optional[str] = None


@dataclass
class RecoveryReport:
    """Comprehensive report of a recovery process."""

    serial: str
    successful: bool
    steps: List[RecoveryStepResult]
    final_health: HealthReport
    total_duration_ms: int
