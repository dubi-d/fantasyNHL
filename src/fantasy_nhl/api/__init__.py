"""The web backend (needs the ``web`` extra)."""
from .app import create_app, main

__all__ = ["create_app", "main"]
