import os
import sys
from pathlib import Path

# Add backend and backend/src to Python path so app modules import cleanly
_current_dir = Path(__file__).resolve().parent
_backend_dir = _current_dir.parent
_src_dir = _backend_dir / "src"

for p in (_src_dir, _backend_dir):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

from app.main import app

# Export app for Vercel Serverless Function entry point
__all__ = ["app"]
