from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Isolate config loading during tests — point to a path that doesn't exist
# so tests always get an empty Config (PlaceholderQueryBackend behavior).
os.environ.setdefault("PY_CLAW_CONFIG_PATH", str(Path("/nonexistent-py-claw-config/config.json")))
