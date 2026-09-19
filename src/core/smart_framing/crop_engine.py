# src/core/smart_framing/crop_engine.py

from __future__ import annotations

from .models import CropDecision


class SmartCropEngine:
    """
    Converts a CropDecision into an FFmpeg crop/scale/pad filter.

    The engine does not decide WHERE to crop.
    That decision has already been made by SmartFramingAnalyzer.
    """

    def build_filter(
        self,
        decision: CropDecision,
    ) -> str:
        crop_x = int(round(decision.x))
        crop_y = int(round(decision.y))
        crop_w = int(round(decision.width))
        crop_h = int(round(decision.height))

        target_w = int(decision.target_width)
        target_h = int(decision.target_height)

        crop = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"

        # Используем flags=lanczos для сохранения максимальной четкости при рескейле
        scale = (
            f"scale={target_w}:{target_h}:"
            f"force_original_aspect_ratio=decrease:"
            f"flags=lanczos"
        )

        pad = (
            f"pad={target_w}:{target_h}:"
            f"(ow-iw)/2:(oh-ih)/2"
        )

        return f"{crop},{scale},{pad}"