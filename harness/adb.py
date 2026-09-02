"""ADB interaction layer."""

import logging
import os
import shlex
import subprocess
from typing import Any, List, Optional, Union

from harness.exceptions import AdbCommandError

logger = logging.getLogger(__name__)


class AdbWrapper:
    """Wrapper for executing adb commands."""

    def __init__(self, adb_path: str = "adb", default_timeout: float = 30.0) -> None:
        self.adb_path = adb_path
        self.default_timeout = default_timeout

    def _run(
        self,
        args: List[str],
        timeout: Optional[float] = None,
        text: bool = True,
        capture_output: bool = True,
        **kwargs: Any,
    ) -> "subprocess.CompletedProcess[Any]":
        """Executes an adb command safely using subprocess."""
        cmd_timeout = timeout if timeout is not None else self.default_timeout
        try:
            result = subprocess.run(
                args,
                timeout=cmd_timeout,
                check=False,
                text=text,
                capture_output=capture_output,
                **kwargs,
            )
        except FileNotFoundError as e:
            raise AdbCommandError(
                f"ADB executable not found at '{self.adb_path}': {e}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise AdbCommandError(
                f"Command timed out after {cmd_timeout}s: {args}"
            ) from e

        if result.returncode != 0:
            stderr = (
                result.stderr
                if text
                else (
                    result.stderr.decode("utf-8", errors="replace")
                    if result.stderr
                    else ""
                )
            )

            if stderr:
                stderr_lower = stderr.lower()
                if "device offline" in stderr_lower:
                    raise AdbCommandError(
                        f"Device offline. Command: {args}, Stderr: {stderr}"
                    )
                if "unauthorized" in stderr_lower:
                    raise AdbCommandError(
                        f"Device unauthorized. Command: {args}, Stderr: {stderr}"
                    )

            raise AdbCommandError(
                f"ADB command failed with exit code {result.returncode}. "
                f"Command: {args}, Stderr: {stderr}"
            )

        return result

    def _build_cmd(self, serial: Optional[str], *args: str) -> List[str]:
        cmd = [self.adb_path]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(args)
        return cmd

    def start_server(self) -> None:
        self._run([self.adb_path, "start-server"])

    def kill_server(self) -> None:
        self._run([self.adb_path, "kill-server"])

    def devices(self) -> str:
        result = self._run([self.adb_path, "devices"])
        out: str = result.stdout
        return out.strip()

    def get_state(self, serial: str) -> str:
        result = self._run(self._build_cmd(serial, "get-state"))
        out: str = result.stdout
        return out.strip()

    def shell(
        self,
        serial: str,
        command: Union[str, List[str]],
        timeout: Optional[float] = None,
    ) -> str:
        args = self._build_cmd(serial, "shell")
        if isinstance(command, str):
            args.extend(shlex.split(command))
        else:
            args.extend(command)

        result = self._run(args, timeout=timeout)
        out: str = result.stdout
        return out.strip()

    def getprop(self, serial: str, property_name: str) -> str:
        return self.shell(serial, ["getprop", property_name])

    def pidof(self, serial: str, package_name: str) -> Optional[int]:
        try:
            out = self.shell(serial, ["pidof", package_name])
            if out:
                pids = out.split()
                if pids:
                    return int(pids[0])
            return None
        except AdbCommandError:
            return None

    def kill_process(self, serial: str, pid: int, signal: int = 15) -> None:
        self.shell(serial, ["kill", f"-{signal}", str(pid)])

    def force_stop(self, serial: str, package_name: str) -> None:
        self.shell(serial, ["am", "force-stop", package_name])

    def start_app(self, serial: str, package_name: str) -> None:
        self.shell(
            serial,
            [
                "monkey",
                "-p",
                package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
        )

    def reboot(self, serial: str) -> None:
        self._run(self._build_cmd(serial, "reboot"))

    def wait_for_device(self, serial: str, timeout: Optional[float] = None) -> None:
        self._run(self._build_cmd(serial, "wait-for-device"), timeout=timeout)

    def screenshot(self, serial: str, output_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        args = self._build_cmd(serial, "exec-out", "screencap", "-p")
        with open(output_path, "wb") as f:
            self._run(args, text=False, capture_output=False, stdout=f)

    def logcat(self, serial: str, lines: Optional[int] = None) -> str:
        args = self._build_cmd(serial, "logcat", "-d")
        if lines is not None:
            args.extend(["-t", str(lines)])
        result = self._run(args)
        out: str = result.stdout
        return out.strip()
