from __future__ import annotations

import sys
from pathlib import Path

import cv2


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_INPUT_DIR = PROJECT_ROOT / "test_media"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "test_media" / "output"


# ============================================================
# IMPORT PROJECT MODULES
# ============================================================

sys.path.insert(0, str(PROJECT_ROOT))

from src.core.smart_framing.detector import LocalObjectDetector
from src.core.smart_framing.analyzer import SmartFramingAnalyzer
from src.core.smart_framing.crop_engine import SmartCropEngine


# ============================================================
# HELPERS
# ============================================================

def find_input_video() -> Path:
    """
    Find the first video inside test_media.

    Supported:
        mp4
        mov
        avi
        mkv
        webm
    """

    if not DEFAULT_INPUT_DIR.exists():
        raise FileNotFoundError(
            f"Test directory does not exist:\n"
            f"{DEFAULT_INPUT_DIR}\n\n"
            f"Create it and put a test video inside."
        )

    extensions = {
        ".mp4",
        ".mov",
        ".avi",
        ".mkv",
        ".webm",
    }

    videos = sorted(
        path
        for path in DEFAULT_INPUT_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in extensions
    )

    if not videos:
        raise FileNotFoundError(
            f"No test video found in:\n"
            f"{DEFAULT_INPUT_DIR}\n\n"
            f"Put a video there, for example:\n"
            f"test_media\\problem.mp4"
        )

    return videos[0]


def probe_video(video_path: Path) -> tuple[int, int, float, int]:
    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise RuntimeError(
            f"Unable to open video:\n{video_path}"
        )

    width = int(
        capture.get(cv2.CAP_PROP_FRAME_WIDTH)
    )

    height = int(
        capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )

    fps = float(
        capture.get(cv2.CAP_PROP_FPS)
    )

    frame_count = int(
        capture.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    capture.release()

    if fps <= 0:
        fps = 25.0

    return width, height, fps, frame_count


def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


# ============================================================
# MAIN TEST
# ============================================================

def main() -> int:

    print_header("SMART FRAMING — ISOLATED TEST")

    # --------------------------------------------------------
    # 1. FIND VIDEO
    # --------------------------------------------------------

    try:
        video_path = find_input_video()
    except Exception as exc:
        print(f"\nERROR: {exc}")
        return 1

    print(f"\nInput video:")
    print(f"  {video_path}")

    # --------------------------------------------------------
    # 2. PROBE VIDEO
    # --------------------------------------------------------

    try:
        source_width, source_height, fps, frame_count = (
            probe_video(video_path)
        )
    except Exception as exc:
        print(f"\nERROR probing video: {exc}")
        return 1

    duration = (
        frame_count / fps
        if fps > 0
        else 0
    )

    print("\nSource:")
    print(f"  Resolution : {source_width} x {source_height}")
    print(f"  FPS        : {fps:.2f}")
    print(f"  Frames     : {frame_count}")
    print(f"  Duration   : {duration:.2f} sec")

    # --------------------------------------------------------
    # 3. TARGET FORMAT
    # --------------------------------------------------------
    #
    # For the first test we deliberately use 16:9.
    #
    # This is exactly the problematic case:
    #
    # horizontal source -> vertical/other composition
    #
    # The actual crop decision is calculated by SmartFraming.
    #

    target_width = 1920
    target_height = 1080

    print("\nTarget:")
    print(f"  Resolution : {target_width} x {target_height}")
    print(
        f"  Aspect     : "
        f"{target_width / target_height:.3f}"
    )

    # --------------------------------------------------------
    # 4. CREATE DETECTOR
    # --------------------------------------------------------

    print_header("STEP 1 — LOCAL DETECTION")

    try:
        detector = LocalObjectDetector(
    enable_person=True,
    enable_face=True,
    enable_text=True,
)
    except Exception as exc:
        print(f"\nERROR creating detector: {exc}")
        return 1

    print("Detector created.")

    print(
        "\nRunning multi-frame detection..."
    )
    print(
        "The video will NOT be modified."
    )

    # --------------------------------------------------------
    # 5. DETECT
    # --------------------------------------------------------

    try:
        analyses = detector.detect_video_samples(
            video_path=str(video_path),
            sample_count=7,
        )
    except Exception as exc:

        print()
        print("DETECTION FAILED")
        print("-" * 70)
        print(str(exc))
        print("-" * 70)

        if "ultralytics" in str(exc).lower():
            print()
            print(
                "Reason: ultralytics is not installed "
                "or cannot be imported."
            )
            print()
            print(
                "Current detector.py requires YOLO."
            )
            print(
                "OpenCV and NumPy are already available, "
                "but YOLO is not."
            )

        return 2

    print(
        f"\nFrames successfully analysed: "
        f"{len(analyses)}"
    )

    # --------------------------------------------------------
    # 6. PRINT DETECTIONS
    # --------------------------------------------------------

    total_people = 0

    for analysis in analyses:

        people = [
            detection
            for detection in analysis.detections
            if detection.detection_type.value == "person"
        ]

        total_people += len(people)

        print(
            f"\nFrame {analysis.frame_index}"
            f" @ {analysis.timestamp:.2f}s"
        )

        if not people:
            print("  People: 0")
            continue

        print(
            f"  People: {len(people)}"
        )

        for index, detection in enumerate(
            people,
            start=1,
        ):
            bbox = detection.bbox

            print(
                f"    Person {index}: "
                f"x={bbox.x}, "
                f"y={bbox.y}, "
                f"w={bbox.width}, "
                f"h={bbox.height}, "
                f"confidence={detection.confidence:.3f}"
            )

    print(
        f"\nTotal person detections across samples: "
        f"{total_people}"
    )

    # --------------------------------------------------------
    # 7. ANALYZE COMPOSITION
    # --------------------------------------------------------

    print_header("STEP 2 — SMART FRAMING ANALYSIS")

    analyzer = SmartFramingAnalyzer()

    try:
        decision = analyzer.analyze(
            analyses=analyses,
            target_width=target_width,
            target_height=target_height,
        )
    except Exception as exc:
        print(
            f"\nERROR during Smart Framing analysis: "
            f"{exc}"
        )
        return 3

    # --------------------------------------------------------
    # 8. PRINT DECISION
    # --------------------------------------------------------

    print("\nSMART FRAMING DECISION")
    print("-" * 70)

    print(
        f"Source       : "
        f"{decision.source_width} x "
        f"{decision.source_height}"
    )

    print(
        f"Target       : "
        f"{decision.target_width} x "
        f"{decision.target_height}"
    )

    print(
        f"Crop         : "
        f"x={decision.x}, "
        f"y={decision.y}, "
        f"w={decision.width}, "
        f"h={decision.height}"
    )

    print(
        f"Strategy     : "
        f"{decision.strategy}"
    )

    print(
        f"Score        : "
        f"{decision.score:.3f}"
    )

    print(
        f"People       : "
        f"{decision.detected_people}"
    )

    print(
        f"Faces        : "
        f"{decision.detected_faces}"
    )

    print(
        f"Heads        : "
        f"{decision.detected_heads}"
    )

    print(
        f"Text regions : "
        f"{decision.detected_text_regions}"
    )

    print(
        f"Logos        : "
        f"{decision.detected_logos}"
    )

    print(
        f"Reason       : "
        f"{decision.reason}"
    )

    # --------------------------------------------------------
    # 9. BUILD FFMPEG FILTER
    # --------------------------------------------------------

    print_header("STEP 3 — CROP ENGINE")

    crop_engine = SmartCropEngine()

    try:
        ffmpeg_filter = crop_engine.build_filter(
            decision
        )
    except Exception as exc:
        print(
            f"\nERROR building FFmpeg filter: "
            f"{exc}"
        )
        return 4

    print("\nGenerated FFmpeg filter:")
    print()
    print(ffmpeg_filter)

    # --------------------------------------------------------
    # 10. FINAL RESULT
    # --------------------------------------------------------

    print_header("TEST RESULT")

    print("Smart Framing analysis completed successfully.")
    print()
    print("IMPORTANT:")
    print(
        "This test did NOT render or modify the video."
    )
    print(
        "It only tested:"
    )
    print(
        "  1. video reading"
    )
    print(
        "  2. multi-frame detection"
    )
    print(
        "  3. Smart Framing analysis"
    )
    print(
        "  4. crop decision"
    )
    print(
        "  5. FFmpeg filter generation"
    )

    print()
    print(
        "Next step after successful detection:"
    )
    print(
        "render a preview using the generated crop "
        "decision and visually compare it with "
        "the current center crop."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())