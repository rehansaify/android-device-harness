"""Test execution engine."""

import logging
import time
from typing import List, Optional, Protocol

from harness.device import AndroidDevice, DeviceManager
from harness.exceptions import HarnessError
from harness.health import DeviceHealthMonitor
from harness.models import TestResult
from harness.recovery import RecoveryEngine

logger = logging.getLogger(__name__)


class TestRunner(Protocol):
    """Protocol for a test execution strategy."""

    def run(self, device: AndroidDevice, test_path: str) -> TestResult:
        """Runs a specific test path on the device and returns the result."""
        ...


class InstrumentationTestRunner:
    """Runs Android instrumented tests via 'am instrument'."""

    def __init__(self, timeout: float = 300.0) -> None:
        self.timeout = timeout

    def run(self, device: AndroidDevice, test_path: str) -> TestResult:
        start = time.monotonic()
        try:
            out = device.shell(
                ["am", "instrument", "-w", test_path], timeout=self.timeout
            )
            duration = int((time.monotonic() - start) * 1000)

            passed = True
            error_message = None

            # Basic parsing of standard Android instrumentation output
            if (
                "FAILURES!!!" in out
                or "Exception" in out
                or "INSTRUMENTATION_FAILED" in out
            ):
                passed = False
                error_message = (
                    "Test failures or instrumentation error detected in logs"
                )

            return TestResult(
                test_name=test_path,
                passed=passed,
                duration_ms=duration,
                error_message=error_message,
                logs=out,
            )
        except HarnessError as e:
            duration = int((time.monotonic() - start) * 1000)
            return TestResult(
                test_name=test_path,
                passed=False,
                duration_ms=duration,
                error_message=f"Execution failed: {e}",
            )


class TestExecutor:
    """Executes tests on Android devices with health and recovery management."""

    def __init__(
        self,
        device_manager: DeviceManager,
        health_monitor: Optional[DeviceHealthMonitor] = None,
        recovery_engine: Optional[RecoveryEngine] = None,
        test_runner: Optional[TestRunner] = None,
    ) -> None:
        self.device_manager = device_manager
        self.health_monitor = health_monitor or DeviceHealthMonitor()
        self.recovery_engine = recovery_engine or RecoveryEngine(self.health_monitor)
        self.test_runner = test_runner or InstrumentationTestRunner()

    def run_tests(
        self, serial: Optional[str], test_paths: List[str]
    ) -> List[TestResult]:
        """Runs a suite of tests on a device, recovering it if necessary."""
        results: List[TestResult] = []

        try:
            device = self.device_manager.get_device(serial)
        except HarnessError as e:
            logger.error("Failed to acquire device: %s", e)
            for path in test_paths:
                results.append(
                    TestResult(
                        test_name=path,
                        passed=False,
                        duration_ms=0,
                        error_message=f"Device acquisition failed: {e}",
                    )
                )
            return results

        # Ensure device is healthy before running tests
        health = self.health_monitor.check_health(device)
        if not health.is_healthy:
            logger.warning(
                "Device %s is unhealthy. Attempting recovery...", device.serial
            )
            recovery = self.recovery_engine.recover(device, health)
            if not recovery.successful:
                logger.error("Failed to recover device %s.", device.serial)
                for path in test_paths:
                    results.append(
                        TestResult(
                            test_name=path,
                            passed=False,
                            duration_ms=0,
                            error_message="Device is unhealthy and recovery failed",
                        )
                    )
                return results
            logger.info("Successfully recovered device %s.", device.serial)

        # Execute tests
        for path in test_paths:
            logger.info("Running test %s on device %s", path, device.serial)
            result = self.test_runner.run(device, path)
            results.append(result)

        return results
