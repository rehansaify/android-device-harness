"""Test result reporting."""

import json
import logging
import os
from dataclasses import asdict
from enum import Enum
from typing import Any, Dict, List, Optional

from harness.models import HealthReport, RecoveryReport, TestResult

logger = logging.getLogger(__name__)


def _custom_json_encoder(obj: Any) -> Any:
    """Handles JSON serialization for types not supported natively."""
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Type {type(obj)} is not JSON serializable")


class ConsoleReporter:
    """Produces human-readable console reports."""

    def generate_report(
        self,
        serial: str,
        results: List[TestResult],
        health_report: Optional[HealthReport] = None,
        recovery_report: Optional[RecoveryReport] = None,
    ) -> str:
        """Generates a structured terminal report."""
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        total = len(results)
        total_duration = sum(r.duration_ms for r in results)

        overall_status = "PASSED" if failed == 0 and total > 0 else "FAILED"
        if total == 0:
            overall_status = "NO TESTS"

        lines = [
            "Android Device Harness",
            "────────────────────────────────────",
            f"Device: {serial}",
            f"Status: {overall_status}",
            "",
        ]

        if results:
            lines.append("Tests")
            lines.append("────────────────────────────────────")
            for r in results:
                mark = "✓" if r.passed else "✗"
                dur = f"{r.duration_ms / 1000:.2f}s"
                lines.append(f"{mark} {r.test_name:<20} {dur:>6}")
                if r.error_message:
                    lines.append(f"  Error: {r.error_message}")
            lines.append("")

        if health_report:
            lines.append("Health")
            lines.append("────────────────────────────────────")
            health_status = "Healthy" if health_report.is_healthy else "Unhealthy"
            lines.append(
                f"State: {health_status} ({health_report.total_duration_ms / 1000:.2f}s)"
            )
            for hr in health_report.results:
                mark = "✓" if hr.is_healthy else "✗"
                lines.append(f"  {mark} {hr.check_name}")
            lines.append("")

        if recovery_report:
            lines.append("Recovery")
            lines.append("────────────────────────────────────")
            if recovery_report.successful:
                lines.append("✓ Device recovered after failure")
            else:
                lines.append("✗ Device recovery failed")
            for step in recovery_report.steps:
                mark = "✓" if step.success else "✗"
                lines.append(f"  {mark} {step.step_name}: {step.message}")
            lines.append("")

        lines.append("Summary")
        lines.append("────────────────────────────────────")
        lines.append(f"Passed:  {passed}")
        lines.append(f"Failed:  {failed}")
        lines.append("Skipped: 0")
        lines.append(f"Total:   {total}")
        lines.append(f"Duration: {total_duration / 1000:.2f}s")

        return "\n".join(lines)


class JsonReporter:
    """Produces JSON structured reports."""

    def generate_report(
        self,
        serial: str,
        results: List[TestResult],
        health_report: Optional[HealthReport] = None,
        recovery_report: Optional[RecoveryReport] = None,
    ) -> str:
        """Generates a JSON string report."""
        data: Dict[str, Any] = {
            "serial": serial,
            "summary": {
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "total": len(results),
                "duration_ms": sum(r.duration_ms for r in results),
            },
            "tests": [asdict(r) for r in results],
            "health": asdict(health_report) if health_report else None,
            "recovery": asdict(recovery_report) if recovery_report else None,
        }

        return json.dumps(data, indent=2, default=_custom_json_encoder)

    def write_report(
        self,
        output_path: str,
        serial: str,
        results: List[TestResult],
        health_report: Optional[HealthReport] = None,
        recovery_report: Optional[RecoveryReport] = None,
    ) -> None:
        """Writes the JSON report to a file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        report_json = self.generate_report(
            serial, results, health_report, recovery_report
        )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report_json)
