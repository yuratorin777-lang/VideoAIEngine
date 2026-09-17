from __future__ import annotations

from .models import CropDecision


class SmartCropEngine:
    """
    Converts a CropDecision into an FFmpeg crop/scale filter.

    The engine does not decide WHERE to crop.
    That decision has already been made by SmartFramingAnalyzer.
    """

    def build_filter(
        self,
        decision: CropDecision,
    ) -> str:
        crop = (
            f"crop="
            f"{decision.width}:"
            f"{decision.height}:"
            f"{decision.x}:"
            f"{decision.y}"
        )

        scale = (
            f"scale="
            f"{decision.target_width}:"
            f"{decision.target_height}:"
            f"force_original_aspect_ratio=decrease"
        )

        pad = (
            f"pad="
            f"{decision.target_width}:"
            f"{decision.target_height}:"
            f"(ow-iw)/2:"
            f"(oh-ih)/2"
        )

        return f"{crop},{scale},{pad}"