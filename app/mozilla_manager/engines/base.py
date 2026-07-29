from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import LaunchResult, Profile


class EngineLauncher(ABC):
    name: str

    @abstractmethod
    def launch(self, profile: Profile, *, headless: bool = False, open_check: bool | None = None) -> LaunchResult:
        raise NotImplementedError

    @abstractmethod
    def stop(self, profile_id: str) -> None:
        raise NotImplementedError
