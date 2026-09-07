"""Abstract base class for all skill executors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class SkillExecutor(ABC, Generic[InputT, OutputT]):
    """Abstract base for a skill executor.

    Each skill module provides:
    - A Pydantic Input model  (the request schema)
    - A Pydantic Output model (the response schema)
    - An execute() method that implements the skill logic

    Subclass this with the appropriate type parameters to get type-safe
    execute() calls registered in the skill router.
    """

    @property
    @abstractmethod
    def slug(self) -> str:
        """Canonical skill name, e.g. 'store_memory'."""
        raise NotImplementedError

    @abstractmethod
    async def execute(self, input_data: InputT) -> OutputT:
        """Run the skill with the given input and return the output."""
        raise NotImplementedError
