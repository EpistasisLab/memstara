"""Memstara package metadata and logging initialization."""

from __future__ import annotations

import os

# Set this before any dependency can import the model client.
os.environ.setdefault("LITELLM_LOG", "DEBUG")

try:
    from memstara._version import __version__
except ImportError:
    # Source checkouts report an unknown version until built or installed.
    __version__ = "0.0.0+unknown"
