"""
Smart Framing subsystem.

Local visual intelligence for converting source video
into a target aspect ratio without destroying composition.

Architecture:

Level 1 — Geometry
    Aspect ratio, crop boundaries, safe geometric transforms.

Level 2 — Visual Awareness
    People, faces, heads, text/logo regions, safe zones.

Level 3 — Tracking
    Dynamic crop movement following subjects over time.
    Not implemented yet.
"""

from .models import (
    BoundingBox,
    Detection,
    FrameAnalysis,
    CropDecision,
    SmartFramingConfig,
)

__all__ = [
    "BoundingBox",
    "Detection",
    "FrameAnalysis",
    "CropDecision",
    "SmartFramingConfig",
]