from __future__ import annotations

import sys
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parent / "backend" / "src"
backend_src_str = str(BACKEND_SRC)
if backend_src_str not in sys.path:
    sys.path.insert(0, backend_src_str)