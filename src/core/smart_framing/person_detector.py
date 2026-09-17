from __future__ import annotations

from pathlib import Path
from typing import List

import cv2

try:
    import mediapipe as mp
except ModuleNotFoundError:
    mp = None
    print("[PersonDetector] WARNING: mediapipe is not installed.")

from .models import BoundingBox, Detection, DetectionType


class PersonDetector:
    """
    Local person/body detector using MediaPipe Pose Landmarker.

    Produces a bounding box around the visible body based on
    detected pose landmarks.
    """

    def __init__(
        self,
        model_path: str = "04_LIBRARY/models/pose_landmarker_lite.task",
        min_detection_confidence: float = 0.5,
    ) -> None:
        self.model_path = Path(model_path)
        self.min_detection_confidence = min_detection_confidence
        self._landmarker = None
        self._failed_to_load = False

    def _load_model(self):
        if self._landmarker is not None or self._failed_to_load:
            return self._landmarker

        if mp is None:
            self._failed_to_load = True
            return None

        if not self.model_path.exists():
            print(f"[PersonDetector] WARNING: Pose model not found: {self.model_path}")
            self._failed_to_load = True
            return None

        try:
            BaseOptions = mp.tasks.BaseOptions
            PoseLandmarker = mp.tasks.vision.PoseLandmarker
            PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = PoseLandmarkerOptions(
                base_options=BaseOptions(
                    model_asset_path=str(self.model_path.resolve())
                ),
                running_mode=VisionRunningMode.IMAGE,
                min_pose_detection_confidence=self.min_detection_confidence,
                min_pose_presence_confidence=self.min_detection_confidence,
            )

            self._landmarker = PoseLandmarker.create_from_options(options)
        except Exception as e:
            print(f"[PersonDetector] WARNING: Failed to initialize MediaPipe PoseLandmarker ({e}). Skipping person detection.")
            self._failed_to_load = True
            self._landmarker = None

        return self._landmarker

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

        landmarker = self._load_model()
        if landmarker is None:
            return []

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=rgb,
            )

            result = landmarker.detect(mp_image)
        except Exception as e:
            print(f"[PersonDetector] WARNING: Error during pose detection ({e}).")
            return []

        detections: List[Detection] = []

        if not result.pose_landmarks:
            return detections

        for pose_landmarks in result.pose_landmarks:

            visible_points = []

            for landmark in pose_landmarks:
                visibility = getattr(landmark, "visibility", 1.0)

                if visibility >= self.min_detection_confidence:
                    x = int(landmark.x * width)
                    y = int(landmark.y * height)

                    if 0 <= x < width and 0 <= y < height:
                        visible_points.append((x, y))

            if len(visible_points) < 3:
                continue

            xs = [p[0] for p in visible_points]
            ys = [p[1] for p in visible_points]

            x1 = max(0, min(xs))
            y1 = max(0, min(ys))
            x2 = min(width, max(xs))
            y2 = min(height, max(ys))

            box_width = x2 - x1
            box_height = y2 - y1

            if box_width <= 0 or box_height <= 0:
                continue

            detections.append(
                Detection(
                    detection_type=DetectionType.PERSON,
                    bbox=BoundingBox(
                        x=x1,
                        y=y1,
                        width=box_width,
                        height=box_height,
                    ),
                    confidence=1.0,
                    label="person",
                    frame_index=frame_index,
                    timestamp=timestamp,
                )
            )

        return detections