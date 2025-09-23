from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

sys.path.append(os.path.dirname(__file__))
from _fake_win32 import fake_win32  # type: ignore

sys.modules["win32print"] = fake_win32  # type: ignore[assignment]
