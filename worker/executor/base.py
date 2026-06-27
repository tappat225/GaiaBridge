"""Base executor interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ExecResult:
    success: bool
    output: str = ""
    error: str = ""


class BaseExecutor(ABC):
    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ExecResult:
        ...
