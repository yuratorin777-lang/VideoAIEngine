from __future__ import annotations

from typing import List

import cv2

from .models import FrameAnalysis
from .person_detector import PersonDetector
from .face_detector import FaceDetector
from .text_detector import TextDetector


class LocalObjectDetector:
    """
    Unified local visual detector.

    Detection backends:
        Person -> MediaPipe Pose
        Face   -> MediaPipe Face Detection
        Text   -> EasyOCR

    This class only orchestrates detectors.

    It does NOT:
        - decide crop;
        - modify video;
        - run FFmpeg;
        - communicate with Gemini.
    """

    def __init__(
        self,
        enable_person: bool = True,
        enable_face: bool = True,
        enable_text: bool = True,
    ) -> None:

        self.person_detector = (
            PersonDetector()
            if enable_person
            else None
        )

        self.face_detector = (
            FaceDetector()
            if enable_face
            else None
        )

        self.text_detector = (
            TextDetector()
            if enable_text
            else None
        )

    def detect_frame(
        self,
        frame,
        frame_index: int = 0,
        timestamp: float = 0.0,
    ) -> FrameAnalysis:

        if frame is None:
            raise ValueError("Frame cannot be None.")

        frame_height, frame_width = frame.shape[:2]

        detections = []

        if self.person_detector is not None:
            detections.extend(
                self.person_detector.detect(
                    frame=frame,
                    frame_index=frame_index,
                    timestamp=timestamp,
                )
            )

        if self.face_detector is not None:
            detections.extend(
                self.face_detector.detect(
                    frame=frame,
                    frame_index=frame_index,
                    timestamp=timestamp,
                )
            )

        if self.text_detector is not None:
            detections.extend(
                self.text_detector.detect(
                    frame=frame,
                    frame_index=frame_index,
                    timestamp=timestamp,
                )
            )

        return FrameAnalysis(
            frame_index=frame_index,
            timestamp=timestamp,
            frame_width=frame_width,
            frame_height=frame_height,
            detections=detections,
        )

    def detect_video_samples(
        self,
        video_path: str,
        sample_count: int = 7,
        start_time: float = 0.0,
        duration: float | None = None,
    ) -> List[FrameAnalysis]:
        """
        Анализирует sample_count кадров конкретного временного
        диапазона видео.

        Если duration не задан — анализируется весь файл.

        Важно:
        frame_index остаётся индексом кадра исходного видео,
        timestamp считается относительно исходного видео.
        """

        capture = cv2.VideoCapture(video_path)

        if not capture.isOpened():
            raise RuntimeError(
                f"Unable to open video: {video_path}"
            )

        total_frames = int(
            capture.get(cv2.CAP_PROP_FRAME_COUNT)
        )

        fps = float(
            capture.get(cv2.CAP_PROP_FPS)
        )

        if fps <= 0:
            fps = 25.0

        if total_frames <= 0:
            capture.release()
            raise RuntimeError(
                f"Unable to determine frame count: {video_path}"
            )

        start_time = max(0.0, float(start_time))

        start_frame = int(
            round(start_time * fps)
        )

        if start_frame >= total_frames:
            capture.release()
            return []

        if duration is None:
            end_frame = total_frames - 1
        else:
            duration = max(0.0, float(duration))

            end_time = start_time + duration

            end_frame = int(
                round(end_time * fps)
            )

            end_frame = min(
                end_frame,
                total_frames - 1,
            )

        if end_frame < start_frame:
            capture.release()
            return []

        available_frames = (
            end_frame - start_frame + 1
        )

        sample_count = max(
            1,
            min(sample_count, available_frames),
        )

        if sample_count == 1:

            frame_indices = [
                start_frame
                + available_frames // 2
            ]

        else:

            step = (
                (available_frames - 1)
                / (sample_count - 1)
            )

            frame_indices = [
                start_frame
                + int(round(index * step))
                for index in range(sample_count)
            ]

        analyses: List[FrameAnalysis] = []

        for frame_index in frame_indices:

            capture.set(
                cv2.CAP_PROP_POS_FRAMES,
                frame_index,
            )

            success, frame = capture.read()

            if not success or frame is None:
                continue

            timestamp = frame_index / fps

            analysis = self.detect_frame(
                frame=frame,
                frame_index=frame_index,
                timestamp=timestamp,
            )

            analyses.append(analysis)

        capture.release()

        return analyses