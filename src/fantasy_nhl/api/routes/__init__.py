"""The HTTP API: every view of the CLI tools as JSON, their prompts as
query parameters. A view with figures also serves them as PNG at
<view>/figures/<n>.png."""
from fastapi import APIRouter

from . import league, planning, review, standings
from .base import LOCAL_HOSTS

router = APIRouter(prefix="/api")
for _module in (league, standings, planning, review):
    router.include_router(_module.router)

__all__ = ["LOCAL_HOSTS", "router"]
