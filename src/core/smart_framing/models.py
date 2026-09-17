from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class DetectionType(str, Enum):
    PERSON = "person"
    FACE = "face"
    HEAD = "head"
    TEXT = "text"
    LOGO = "logo"


class CropStrategy(str, Enum):
    CENTER_CROP = "CENTER_CROP"
    SMART_PERSON_CROP = "SMART_PERSON_CROP"
    SMART_FACE_CROP = "SMART_FACE_CROP"
    SMART_TEXT_CROP = "SMART_TEXT_CROP"
    SMART_COMPOSITION_CROP = "SMART_COMPOSITION_CROP"
    FIT = "FIT"


@dataclass
class BoundingBox:
    """
    Bounding box in source-frame pixel coordinates.
    """

    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    def clamp(self, frame_width: int, frame_height: int) -> "BoundingBox":
        x = max(0, min(self.x, frame_width))
        y = max(0, min(self.y, frame_height))

        x2 = max(x, min(self.x2, frame_width))
        y2 = max(y, min(self.y2, frame_height))

        return BoundingBox(
            x=x,
            y=y,
            width=x2 - x,
            height=y2 - y,
        )


@dataclass
class Detection:
    """
    A visual object detected on a sampled frame.
    """

    detection_type: DetectionType
    bbox: BoundingBox

    confidence: float = 0.0

    label: Optional[str] = None

    # Optional source frame information.
    frame_index: Optional[int] = None
    timestamp: Optional[float] = None


@dataclass
class FrameAnalysis:
    """
    Visual analysis result for one sampled frame.
    """

    frame_index: int
    timestamp: float

    frame_width: int
    frame_height: int

    detections: List[Detection] = field(default_factory=list)

    @property
    def persons(self) -> List[Detection]:
        return [
            d
            for d in self.detections
            if d.detection_type == DetectionType.PERSON
        ]

    @property
    def faces(self) -> List[Detection]:
        return [
            d
            for d in self.detections
            if d.detection_type == DetectionType.FACE
        ]

    @property
    def heads(self) -> List[Detection]:
        return [
            d
            for d in self.detections
            if d.detection_type == DetectionType.HEAD
        ]

    @property
    def text_regions(self) -> List[Detection]:
        return [
            d
            for d in self.detections
            if d.detection_type == DetectionType.TEXT
        ]

    @property
    def logos(self) -> List[Detection]:
        return [
            d
            for d in self.detections
            if d.detection_type == DetectionType.LOGO
        ]


@dataclass
class CropDecision:
    """
    Final crop decision produced by Smart Framing.

    Coordinates are in source-frame pixels.
    """

    x: int
    y: int
    width: int
    height: int

    source_width: int
    source_height: int

    target_width: int
    target_height: int

    strategy: CropStrategy

    score: float = 0.0

    reason: str = ""

    detected_people: int = 0
    detected_faces: int = 0
    detected_heads: int = 0
    detected_text_regions: int = 0
    detected_logos: int = 0

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "source_width": self.source_width,
            "source_height": self.source_height,
            "target_width": self.target_width,
            "target_height": self.target_height,
            "strategy": self.strategy.value,
            "score": self.score,
            "reason": self.reason,
            "detected_people": self.detected_people,
            "detected_faces": self.detected_faces,
            "detected_heads": self.detected_heads,
            "detected_text_regions": self.detected_text_regions,
            "detected_logos": self.detected_logos,
        }


@dataclass
class SmartFramingConfig:
    """
    Configuration for local Smart Framing.
    """

    sample_count: int = 7

    person_confidence: float = 0.35

    # Additional safety margins around important objects.
    face_margin_ratio: float = 0.12
    head_margin_ratio: float = 0.15
    person_margin_ratio: float = 0.08
    text_margin_ratio: float = 0.08

    # How strongly different visual elements affect crop scoring.
    face_weight: float = 5.0
    head_weight: float = 5.0
    person_weight: float = 3.0
    text_weight: float = 4.0
    logo_weight: float = 4.0

    # Minimum confidence required for semantic decisions.
    minimum_decision_score: float = 0.5

    # If the intelligent crop would destroy too much content,
    # allow the caller to fall back to FIT.
    allow_fit_fallback: bool = True