# SPDX-License-Identifier: Apache-2.0
"""Shell command executor with workspace boundary enforcement."""

import asyncio
import ctypes
import os
from pathlib import Path
import signal
import subprocess
from typing import Any
from ctypes import wintypes

from .base import BaseExecutor, ExecResult
from shared.protocol import ErrorCode


class ShellExecutor(BaseExecutor):
    def __init__(self, workspace: str, timeout: int = 120):
        self._workspace = Path(workspace).resolve()
        self._timeout = timeout

    async def execute(self, params: dict[str, Any]) -> ExecResult:
        command = params.get("command", "")
        cwd = params.get("cwd", ".")

        work_dir = (self._workspace / cwd).resolve()
        try:
            work_dir.relative_to(self._workspace)
        except ValueError:
            return ExecResult(
                success=False,
                error=f"cwd escapes workspace: {cwd}",
                error_code=ErrorCode.workspace_violation.value,
            )

        work_dir.mkdir(parents=True, exist_ok=True)

        if os.name == "nt":
            return await asyncio.to_thread(self._execute_windows, command, work_dir)

        try:
            popen_kwargs = {}
            popen_kwargs["start_new_session"] = True

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(work_dir),
                **popen_kwargs)
            communicate_task = asyncio.create_task(proc.communicate())
            done, _ = await asyncio.wait({communicate_task}, timeout=self._timeout)
            if not done:
                await self._terminate_process_tree(proc)
                try:
                    await asyncio.wait_for(communicate_task, timeout=0.8)
                except asyncio.TimeoutError:
                    communicate_task.cancel()
                    try:
                        await communicate_task
                    except asyncio.CancelledError:
                        pass
                return ExecResult(
                    success=False, error=f"command timed out after {self._timeout}s",
                    error_code=ErrorCode.timeout.value)
            stdout, _ = communicate_task.result()
            output = stdout.decode("utf-8", errors="replace")
            return ExecResult(
                success=(proc.returncode == 0),
                output=f"Exit code: {proc.returncode}\n{output}")
        except Exception as e:
            return ExecResult(success=False, error=str(e))

    def _execute_windows(self, command: str, work_dir: Path) -> ExecResult:
        job = self._create_windows_job()
        proc = None
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=str(work_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            if job:
                self._assign_windows_job(job, proc)

            stdout, _ = proc.communicate(timeout=self._timeout)
            output = stdout.decode("utf-8", errors="replace")
            return ExecResult(
                success=(proc.returncode == 0),
                output=f"Exit code: {proc.returncode}\n{output}")
        except subprocess.TimeoutExpired:
            if job:
                self._terminate_windows_job(job)
            elif proc:
                proc.kill()
            if proc:
                try:
                    proc.communicate(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
            return ExecResult(
                success=False, error=f"command timed out after {self._timeout}s",
                error_code=ErrorCode.timeout.value)
        except Exception as e:
            return ExecResult(success=False, error=str(e))
        finally:
            if job:
                ctypes.windll.kernel32.CloseHandle(job)

    def _create_windows_job(self):
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_uint32),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", ctypes.c_uint32),
                ("SchedulingClass", ctypes.c_uint32),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        info = ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = 0x00002000
        ok = kernel32.SetInformationJobObject(
            job,
            9,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            kernel32.CloseHandle(job)
            return None
        return job

    def _assign_windows_job(self, job, proc: subprocess.Popen) -> None:
        kernel32 = ctypes.windll.kernel32
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        handle = int(proc._handle)
        kernel32.AssignProcessToJobObject(job, handle)

    def _terminate_windows_job(self, job) -> None:
        kernel32 = ctypes.windll.kernel32
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, ctypes.c_uint]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject(job, 1)

    async def _terminate_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(proc.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
            try:
                await asyncio.wait_for(killer.communicate(), timeout=0.2)
            except asyncio.TimeoutError:
                killer.kill()
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        try:
            await asyncio.wait_for(proc.wait(), timeout=0.2)
        except asyncio.TimeoutError:
            pass
