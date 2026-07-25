import sys
import os

# Make the project root importable so `from app import app` works from api/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app  # noqa: E402

# Vercel's Python runtime looks for a WSGI-compatible `app` object in this file.
