"""Shared win32print test doubles.

This module centralizes the fake win32print implementations used in the
unit tests so they can reuse the same behavior and sys.modules
registration.
"""

from __future__ import annotations

import sys


class BaseWin32:
    """Basic fake implementation that mimics the win32print API used in tests."""

    def __init__(self) -> None:
        self.written: list[bytes] = []

    def GetDefaultPrinter(self):
        return "dummy"

    def OpenPrinter(self, name):
        return object()

    def StartDocPrinter(self, h, level, info):
        pass

    def StartPagePrinter(self, h):
        pass

    def WritePrinter(self, h, data):
        self.written.append(data)

    def EndPagePrinter(self, h):
        pass

    def EndDocPrinter(self, h):
        pass

    def ClosePrinter(self, h):
        pass


class FakeWin32(BaseWin32):
    """Default fake used across the test-suite."""


fake_win32 = FakeWin32()

# Register the fake in sys.modules so imports of win32print use it.
sys.modules["win32print"] = fake_win32  # type: ignore[assignment]

__all__ = ["BaseWin32", "FakeWin32", "fake_win32"]
