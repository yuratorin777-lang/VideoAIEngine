from __future__ import annotations

from typing import List

import cv2
import easyocr

from .models import (
    BoundingBox,
    Detection,
    DetectionType,
)


class TextDetector:
    """
    Detects text regions using EasyOCR.

    OCR text itself is not currently used for crop decisions.
    We primarily need bounding boxes of visible text.
    """

    def __init__(
        self,
        languages: list[str] | None = None,
        confidence: float = 0.35,
    ) -> None:

        self.languages = languages or ["en", "ru"]
        self.confidence = confidence

        self.reader = easyocr.Reader(
            self.languages,
            gpu=False,
            verbose=False,
        )

    def detect(
        self,
        frame,
        frame_index: int = 0,
        timestamp: float = 0.0,
    ) -> List[Detection]:

        height, width = frame.shape[:2]

        results = self.reader.readtext(
            frame,
            detail=1,
            paragraph=False,
        )

        detections: List[Detection] = []

        for result in results:

            if len(result) != 3:
                continue

            polygon, text, confidence = result

            confidence = float(confidence)

            if confidence < self.confidence:
                continue

            xs = [
                int(point[0])
                for point in polygon
            ]

            ys = [
                int(point[1])
                for point in polygon
            ]

            if not xs or not ys:
                continue

            x1 = max(0, min(xs))
            y1 = max(0, min(ys))
            x2 = min(width, max(xs))
            y2 = min(height, max(ys))

            bbox = BoundingBox(
                x=x1,
                y=y1,
                width=max(1, x2 - x1),
                height=max(1, y2 - y1),
            )

            detections.append(
                Detection(
                    detection_type=DetectionType.TEXT,
                    bbox=bbox,
                    confidence=confidence,
                    label=str(text),
                    frame_index=frame_index,
                    timestamp=timestamp,
                )
            )

        return detections