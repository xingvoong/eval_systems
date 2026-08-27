from abc import ABC, abstractmethod


class BaseSystemAdapter(ABC):
    """Implement this to plug any system into the eval framework."""

    @abstractmethod
    def call(self, input: str) -> str:
        """Send input to the system, return its output."""

    def validate_input(self, input: str) -> tuple[bool, str]:
        """Optional: return (is_valid, reason). Default: always valid."""
        return True, ""

    def scan_output(self, output: str) -> tuple[bool, str]:
        """Optional: return (is_safe, reason). Default: always safe."""
        return True, ""

    @property
    def name(self) -> str:
        return self.__class__.__name__
