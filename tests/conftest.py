from __future__ import annotations

import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

sys.path.append(os.path.dirname(__file__))
fake_win32 = importlib.import_module("_fake_win32").fake_win32  # type: ignore[attr-defined]

sys.modules["win32print"] = fake_win32  # type: ignore[assignment]
