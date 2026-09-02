"""Unit tests for the reporter module."""

import json
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

from harness.models import (
    HealthReport,
    HealthResult,
    RecoveryReport,
    RecoveryStepResult,
    TestResult,
)
from harness.reporter import ConsoleReporter, JsonReporter, _custom_json_encoder


@pytest.fixture
def test_results_mixed() -> list[TestResult]:
    return [
        TestResult(test_name="test_passed", passed=True, duration_ms=1000, logs="OK"),
        TestResult(
            test_name="test_failed",
            passed=False,
            duration_ms=2000,
            error_message="Exception thrown",
            logs="FAILURES!!!",
        ),
    ]


@pytest.fixture
def health_report() -> HealthReport:
    return HealthReport(
        serial="123",
        results=[
            HealthResult(
                check_name="dummy_check",
                is_healthy=True,
                duration_ms=50,
                message="All good",
            )
        ],
        total_duration_ms=50,
    )


@pytest.fixture
def recovery_report(health_report: HealthReport) -> RecoveryReport:
    return RecoveryReport(
        serial="123",
        successful=True,
        steps=[
            RecoveryStepResult(
                step_name="step1",
                success=True,
                duration_ms=100,
                message="Did the thing",
            )
        ],
        final_health=health_report,
        total_duration_ms=150,
    )


def test_console_reporter_mixed(
    test_results_mixed: list[TestResult],
    health_report: HealthReport,
    recovery_report: RecoveryReport,
) -> None:
    reporter = ConsoleReporter()
    report_text = reporter.generate_report(
        "123", test_results_mixed, health_report, recovery_report
    )

    assert "Device: 123" in report_text
    assert "Status: FAILED" in report_text
    assert "✓ test_passed" in report_text
    assert "✗ test_failed" in report_text
    assert "Error: Exception thrown" in report_text
    assert "State: Healthy (0.05s)" in report_text
    assert "✓ dummy_check" in report_text
    assert "✓ Device recovered after failure" in report_text
    assert "✓ step1: Did the thing" in report_text
    assert "Passed:  1" in report_text
    assert "Failed:  1" in report_text
    assert "Total:   2" in report_text
    assert "Duration: 3.00s" in report_text


def test_console_reporter_all_passed() -> None:
    results = [TestResult(test_name="t1", passed=True, duration_ms=1000)]
    reporter = ConsoleReporter()
    report_text = reporter.generate_report("123", results)

    assert "Status: PASSED" in report_text
    assert "✓ t1" in report_text
    assert "Passed:  1" in report_text


def test_console_reporter_empty() -> None:
    reporter = ConsoleReporter()
    report_text = reporter.generate_report("123", [])

    assert "Status: NO TESTS" in report_text
    assert "Total:   0" in report_text


def test_console_reporter_unhealthy_recovery_failed() -> None:
    hr = HealthReport("123", [HealthResult("chk", False, 10, "bad")], 10)
    rr = RecoveryReport("123", False, [], hr, 10)
    reporter = ConsoleReporter()
    report_text = reporter.generate_report("123", [], hr, rr)

    assert "State: Unhealthy" in report_text
    assert "✗ chk" in report_text
    assert "✗ Device recovery failed" in report_text


def test_json_reporter_mixed(
    test_results_mixed: list[TestResult],
    health_report: HealthReport,
    recovery_report: RecoveryReport,
) -> None:
    reporter = JsonReporter()
    json_str = reporter.generate_report(
        "123", test_results_mixed, health_report, recovery_report
    )

    data = json.loads(json_str)
    assert data["serial"] == "123"
    assert data["summary"]["passed"] == 1
    assert data["summary"]["failed"] == 1
    assert data["summary"]["total"] == 2
    assert data["summary"]["duration_ms"] == 3000

    assert len(data["tests"]) == 2
    assert data["tests"][0]["test_name"] == "test_passed"
    assert data["tests"][1]["error_message"] == "Exception thrown"

    assert data["health"]["serial"] == "123"
    assert data["health"]["results"][0]["check_name"] == "dummy_check"

    assert data["recovery"]["successful"] is True
    assert data["recovery"]["steps"][0]["step_name"] == "step1"


def test_json_reporter_write_report(tmp_path: Path) -> None:
    reporter = JsonReporter()
    output_file = tmp_path / "reports" / "output.json"

    reporter.write_report(str(output_file), "123", [])

    assert output_file.exists()
    content = output_file.read_text(encoding="utf-8")
    data = json.loads(content)
    assert data["serial"] == "123"
    assert data["summary"]["total"] == 0


def test_custom_json_encoder() -> None:
    class DummyEnum(Enum):
        A = "apple"

    assert _custom_json_encoder(DummyEnum.A) == "apple"

    with pytest.raises(TypeError):
        _custom_json_encoder(object())
