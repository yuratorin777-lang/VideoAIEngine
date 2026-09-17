from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import mediapipe as mp

from .models import BoundingBox, Detection, DetectionType


class FaceDetector:
    """
    Local face detector using MediaPipe Face Detector.
    """

    def __init__(
        self,
        model_path: str = "04_LIBRARY/models/blaze_face_short_range.tflite",
        min_detection_confidence: float = 0.5,
    ) -> None:
        self.model_path = Path(model_path)
        self.min_detection_confidence = min_detection_confidence

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Face model not found: {self.model_path}"
            )

        self._detector = None

    def _load_model(self):
        if self._detector is not None:
            return self._detector

        BaseOptions = mp.tasks.BaseOptions
        FaceDetector = mp.tasks.vision.FaceDetector
        FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        options = FaceDetectorOptions(
            base_options=BaseOptions(
                model_asset_path=str(self.model_path.resolve())
            ),
            running_mode=VisionRunningMode.IMAGE,
            min_detection_confidence=self.min_detection_confidence,
        )

        self._detector = FaceDetector.create_from_options(options)

        return self._detector

    def detect(
        self,
        frame,
        frame_index: int = 0,
        timestamp: float = 0.0,
    ) -> List[Detection]:

        if frame is None:
            return []

        height, width = frame.shape[:2]

        if width <= 0 or height <= 0:
            return []

        detector = self._load_model()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb,
        )

        result = detector.detect(mp_image)

        detections: List[Detection] = []

        for detection in result.detections:

            bbox = detection.bounding_box

            x = int(bbox.origin_x)
            y = int(bbox.origin_y)
            w = int(bbox.width)
            h = int(bbox.height)

            x = max(0, min(x, width))
            y = max(0, min(y, height))

            w = max(0, min(w, width - x))
            h = max(0, min(h, height - y))

            if w <= 0 or h <= 0:
                continue

            confidence = 0.0

            if detection.categories:
                confidence = float(
                    detection.categories[0].score
                )

            detections.append(
                Detection(
                    detection_type=DetectionType.FACE,
                    bbox=BoundingBox(
                        x=x,
                        y=y,
                        width=w,
                        height=h,
                    ),
                    confidence=confidence,
                    label="face",
                    frame_index=frame_index,
                    timestamp=timestamp,
                )
            )

        return detections