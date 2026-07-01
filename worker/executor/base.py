# SPDX-License-Identifier: Apache-2.0
"""Base executor interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ExecResult:
    success: bool
    output: str = ""
    error: str = ""
    error_code: Optional[str] = None


class BaseExecutor(ABC):
    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ExecResult:
        ...
