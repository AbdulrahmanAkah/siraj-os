"""SIRAJ desktop dashboard package."""

from .models import DashboardSnapshot, EpisodeRecord, EpisodeStage
from .repository import build_dashboard_snapshot, discover_episode_records

__all__ = [
    "DashboardSnapshot",
    "EpisodeRecord",
    "EpisodeStage",
    "build_dashboard_snapshot",
    "discover_episode_records",
]
