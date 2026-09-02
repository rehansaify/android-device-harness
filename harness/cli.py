"""Command-line interface for the Android Device Harness."""

import argparse
import importlib.metadata
import json
import logging
import sys
import traceback
from dataclasses import asdict
from typing import List, Optional

from harness.adb import AdbWrapper
from harness.device import DeviceManager
from harness.exceptions import HarnessError, MultipleDevicesError
from harness.executor import InstrumentationTestRunner, TestExecutor
from harness.health import DeviceHealthMonitor
from harness.recovery import RecoveryEngine
from harness.reporter import ConsoleReporter, JsonReporter, _custom_json_encoder

logger = logging.getLogger(__name__)


def get_version() -> str:
    try:
        return importlib.metadata.version("android-device-harness")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def resolve_device_serial(device_manager: DeviceManager, serial: Optional[str]) -> str:
    """Helper to get a serial safely, throws MultipleDevicesError if ambiguous."""
    if serial:
        return serial
    # get_device will throw clear exceptions if 0 or >1 devices
    device = device_manager.get_device(serial)
    return device.serial


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Android Device Harness",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"android-device-harness {get_version()}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Devices command
    devices_parser = subparsers.add_parser("devices", help="List connected devices")
    devices_parser.add_argument(
        "--output", choices=["console", "json"], default="console", help="Output format"
    )

    # Health command
    health_parser = subparsers.add_parser("health", help="Check device health")
    health_parser.add_argument("--serial", help="Target device serial")
    health_parser.add_argument(
        "--output", choices=["console", "json"], default="console", help="Output format"
    )
    health_parser.add_argument("--report", help="Path to write JSON report")

    # Recover command
    recover_parser = subparsers.add_parser("recover", help="Recover a device")
    recover_parser.add_argument("--serial", help="Target device serial")
    recover_parser.add_argument(
        "--output", choices=["console", "json"], default="console", help="Output format"
    )
    recover_parser.add_argument("--report", help="Path to write JSON report")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run tests on a device")
    run_parser.add_argument("test_paths", nargs="+", help="Paths to tests to run")
    run_parser.add_argument("--serial", help="Target device serial")
    run_parser.add_argument(
        "--timeout", type=float, default=300.0, help="Test execution timeout in seconds"
    )
    run_parser.add_argument(
        "--output", choices=["console", "json"], default="console", help="Output format"
    )
    run_parser.add_argument("--report", help="Path to write JSON report")
    run_parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )

    return parser


def cmd_devices(args: argparse.Namespace, device_manager: DeviceManager) -> int:
    try:
        devices = device_manager.list_devices()
    except HarnessError as e:
        print(f"Error listing devices: {e}", file=sys.stderr)
        return 3

    if args.output == "json":
        data = [asdict(d) for d in devices]
        print(json.dumps(data, indent=2, default=_custom_json_encoder))
        return 0

    print("Android Devices")
    print("────────────────────────────────────")
    if not devices:
        print("No devices connected.")
        return 0

    for d in devices:
        mark = "✓" if d.state.value == "online" else "✗"
        print(f"{mark} {d.serial}")
        if d.model:
            print(f"  Model: {d.model}")
        if d.os_version:
            print(f"  Android: {d.os_version}")
        if d.api_level:
            print(f"  API: {d.api_level}")
        print(f"  State: {d.state.value}")
        print()

    return 0


def cmd_health(
    args: argparse.Namespace,
    device_manager: DeviceManager,
    health_monitor: DeviceHealthMonitor,
) -> int:
    try:
        serial = resolve_device_serial(device_manager, args.serial)
        device = device_manager.get_device(serial)
        report = health_monitor.check_health(device)
    except MultipleDevicesError as e:
        print(f"Error: {e}. Please specify --serial.", file=sys.stderr)
        return 2
    except HarnessError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    if args.output == "json":
        json_rep = JsonReporter()
        print(json_rep.generate_report(serial, [], health_report=report))
    else:
        con_rep = ConsoleReporter()
        print(con_rep.generate_report(serial, [], health_report=report))

    if args.report:
        json_rep = JsonReporter()
        json_rep.write_report(args.report, serial, [], health_report=report)

    return 0 if report.is_healthy else 1


def cmd_recover(
    args: argparse.Namespace,
    device_manager: DeviceManager,
    health_monitor: DeviceHealthMonitor,
    recovery_engine: RecoveryEngine,
) -> int:
    try:
        serial = resolve_device_serial(device_manager, args.serial)
        device = device_manager.get_device(serial)
        initial_health = health_monitor.check_health(device)
        report = recovery_engine.recover(device, initial_health)
    except MultipleDevicesError as e:
        print(f"Error: {e}. Please specify --serial.", file=sys.stderr)
        return 2
    except HarnessError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    if args.output == "json":
        json_rep = JsonReporter()
        print(json_rep.generate_report(serial, [], recovery_report=report))
    else:
        con_rep = ConsoleReporter()
        print(con_rep.generate_report(serial, [], recovery_report=report))

    if args.report:
        json_rep = JsonReporter()
        json_rep.write_report(args.report, serial, [], recovery_report=report)

    return 0 if report.successful else 1


def cmd_run(args: argparse.Namespace, device_manager: DeviceManager) -> int:
    try:
        serial = resolve_device_serial(device_manager, args.serial)
    except MultipleDevicesError as e:
        print(f"Error: {e}. Please specify --serial.", file=sys.stderr)
        return 2
    except HarnessError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    test_runner = InstrumentationTestRunner(timeout=args.timeout)
    executor = TestExecutor(device_manager=device_manager, test_runner=test_runner)

    try:
        results = executor.run_tests(serial, args.test_paths)
    except HarnessError as e:
        print(f"Execution Error: {e}", file=sys.stderr)
        return 3

    all_passed = all(r.passed for r in results)

    if args.output == "json":
        json_rep = JsonReporter()
        print(json_rep.generate_report(serial, results))
    else:
        con_rep = ConsoleReporter()
        print(con_rep.generate_report(serial, results))

    if args.report:
        json_rep = JsonReporter()
        json_rep.write_report(args.report, serial, results)

    return 0 if all_passed else 1


def main(args: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit as e:
        if isinstance(e.code, int):
            return e.code
        return 2  # pragma: no cover

    if hasattr(parsed_args, "verbose") and parsed_args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    adb = AdbWrapper()
    device_manager = DeviceManager(adb)
    health_monitor = DeviceHealthMonitor()
    recovery_engine = RecoveryEngine(health_monitor)

    try:
        if parsed_args.command == "devices":
            return cmd_devices(parsed_args, device_manager)
        elif parsed_args.command == "health":
            return cmd_health(parsed_args, device_manager, health_monitor)
        elif parsed_args.command == "recover":
            return cmd_recover(
                parsed_args, device_manager, health_monitor, recovery_engine
            )
        elif parsed_args.command == "run":
            return cmd_run(parsed_args, device_manager)
        return 2  # pragma: no cover
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
