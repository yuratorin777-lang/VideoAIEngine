import json
import math
import re
import shutil
import subprocess
import gc
from pathlib import Path

from .format_profiles import get_format_profile
from ..core.smart_framing.detector import LocalObjectDetector
from ..core.smart_framing.analyzer import SmartFramingAnalyzer
from ..core.smart_framing.crop_engine import SmartCropEngine
from ..core.smart_framing.models import SmartFramingConfig


BASE_DIR = Path(__file__).resolve().parents[2]

MONTAGE_PLAN_PATH = BASE_DIR / "06_COMPOSER" / "montage_plan.json"
DOWNLOAD_DIR = BASE_DIR / "temp_downloads"
NORMALIZED_DIR = BASE_DIR / "temp_normalized"


class VideoNormalizer:
    """
    VideoAIEngine — Video Normalizer / Format Adapter.

    Основная логика:

    1. Читаем реальные параметры исходника через ffprobe.
    2. Учитываем rotation/display orientation.
    3. Если исходник уже практически совпадает с целевым AR:
       НЕ запускаем Smart Framing и НЕ режем кадр.
    4. Для вертикальных / несовпадающих источников:
       Smart Framing является основным механизмом композиции.
    5. Smart Framing проходит quality gate.
    6. Старый геометрический center crop используется
       только как fallback.
    7. Для вертикальных источников CropDetect остаётся
       дополнительным механизмом обнаружения embedded content.
    8. Цветовая нормализация выполняется отдельно.
    9. Исходные файлы не изменяются.

    ВАЖНО:
    Smart Framing анализируется только на видео без rotation 90/270,
    потому что detector работает в координатной системе исходных кадров.
    Для повёрнутых видео Smart Framing безопасно пропускается,
    а FFmpeg сам применяет autorotate перед геометрическим fallback.
    """

    # ---------------------------------------------------------
    # CROPDETECT
    # ---------------------------------------------------------

    CONTENT_AREA_THRESHOLD = 0.82

    MIN_DETECTED_WIDTH_RATIO = 0.55
    MIN_DETECTED_HEIGHT_RATIO = 0.55

    CROPDETECT_FRAMES = 120

    # ---------------------------------------------------------
    # SMART FRAMING
    # ---------------------------------------------------------

    SMART_ASPECT_TOLERANCE = 0.02

    # Smart Framing не должен создавать кадр,
    # который заметно меньше максимально возможного
    # target-AR crop.
    MIN_SMART_CROP_AREA_RATIO = 0.50

    PROTECT_MATCHED_ASPECT = True

    # Только информационный порог.
    # НИЗКОЕ разрешение само по себе НЕ является причиной
    # отказа от Smart Framing.
    LOW_RES_SOURCE_WIDTH = 960

    # ---------------------------------------------------------
    # COLOR NORMALIZATION
    # ---------------------------------------------------------

    COLOR_ANALYSIS_FPS = 2
    COLOR_ANALYSIS_MAX_SECONDS = 8.0

    COLOR_MIN_BRIGHTNESS = -0.08
    COLOR_MAX_BRIGHTNESS = 0.08

    COLOR_MIN_SATURATION = 0.88
    COLOR_MAX_SATURATION = 1.12

    def __init__(
        self,
        plan_path: Path = MONTAGE_PLAN_PATH,
        download_dir: Path = DOWNLOAD_DIR,
        output_dir: Path = NORMALIZED_DIR,
    ):
        self.plan_path = Path(plan_path)
        self.download_dir = Path(download_dir)
        self.output_dir = Path(output_dir)

        self.smart_framing_config = SmartFramingConfig(
            sample_count=7,
            person_confidence=0.5,
            # Компактные отступы, чтобы рамка не раздувалась за пределы кадра
            face_margin_ratio=0.35,
            head_margin_ratio=0.40,
            person_margin_ratio=0.2,
            text_margin_ratio=0.08,
            # Приоритет отдаем голове и верхней части туловища
            face_weight=4.0,
            head_weight=3.5,
            person_weight=1,
            text_weight=2.0,
            logo_weight=1.0,
            minimum_decision_score=0.4,
            allow_fit_fallback=True,
        )

        self.smart_detector = LocalObjectDetector(
            enable_person=True,
            enable_face=True,
            enable_text=True,
        )

        self.smart_analyzer = SmartFramingAnalyzer(
            config=self.smart_framing_config
        )

        self.smart_crop_engine = SmartCropEngine()

    # =========================================================
    # PLAN
    # =========================================================

    def load_plan(self) -> dict:
        if not self.plan_path.exists():
            raise FileNotFoundError(
                f"Montage plan не найден: {self.plan_path}"
            )

        with self.plan_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def get_output_format(self, plan: dict) -> str:
        output = plan.get("output", {})

        if isinstance(output, dict):
            format_name = output.get("format")

            if format_name:
                return format_name

        return "reels"

    def prepare_output_dir(self):
        if self.output_dir.exists():
            shutil.rmtree(self.output_dir)

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # =========================================================
    # FFPROBE
    # =========================================================

    def probe_video(self, source_path: Path) -> dict:
        """
        Получает:

        - raw width / height
        - fps
        - duration
        - rotation
        - display width / height
        - display aspect ratio

        Rotation нужен для безопасной обработки видео,
        снятых телефоном с display matrix / rotate metadata.
        """

        command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            (
                "stream="
                "width,"
                "height,"
                "r_frame_rate,"
                "duration"
                ":stream_tags=rotate"
                ":stream_side_data=rotation"
            ),
            "-of",
            "json",
            str(source_path),
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "FFprobe ошибка при анализе "
                f"{source_path.name}:\n{result.stderr}"
            )

        try:
            data = json.loads(result.stdout)

            stream = data["streams"][0]

            raw_width = int(stream["width"])
            raw_height = int(stream["height"])

            duration_raw = stream.get("duration")

            duration = (
                float(duration_raw)
                if duration_raw is not None
                else None
            )

            fps_raw = stream.get(
                "r_frame_rate",
                "0/1",
            )

            numerator, denominator = fps_raw.split("/")

            numerator = float(numerator)
            denominator = float(denominator)

            fps = (
                numerator / denominator
                if denominator
                else 0.0
            )

            # -----------------------------------------------------
            # Rotation
            # -----------------------------------------------------

            rotation = 0.0

            tags = stream.get("tags", {})

            if isinstance(tags, dict):
                rotate_tag = tags.get("rotate")

                if rotate_tag is not None:
                    try:
                        rotation = float(rotate_tag)
                    except (TypeError, ValueError):
                        rotation = 0.0

            side_data_list = stream.get(
                "side_data_list",
                [],
            )

            if isinstance(side_data_list, list):
                for side_data in side_data_list:
                    if not isinstance(side_data, dict):
                        continue

                    if "rotation" in side_data:
                        try:
                            rotation = float(
                                side_data["rotation"]
                            )
                            break
                        except (
                            TypeError,
                            ValueError,
                        ):
                            pass

        except (
            KeyError,
            IndexError,
            ValueError,
            ZeroDivisionError,
            TypeError,
        ) as e:
            raise RuntimeError(
                f"Не удалось разобрать ffprobe "
                f"для {source_path.name}: {e}"
            ) from e

        if raw_width <= 0 or raw_height <= 0:
            raise ValueError(
                f"Некорректные размеры видео "
                f"{source_path.name}: "
                f"{raw_width}x{raw_height}"
            )

        # Нормализуем rotation к 0 / 90 / 180 / 270.
        rotation = rotation % 360

        if math.isclose(rotation, 360.0, abs_tol=0.5):
            rotation = 0.0

        if math.isclose(rotation, 90.0, abs_tol=1.0):
            rotation = 90.0
        elif math.isclose(rotation, 180.0, abs_tol=1.0):
            rotation = 180.0
        elif math.isclose(rotation, 270.0, abs_tol=1.0):
            rotation = 270.0
        else:
            rotation = 0.0

        # При 90/270 display orientation меняет ширину/высоту.
        if rotation in (90.0, 270.0):
            display_width = raw_height
            display_height = raw_width
        else:
            display_width = raw_width
            display_height = raw_height

        display_aspect_ratio = (
            display_width / display_height
        )

        return {
            "width": display_width,
            "height": display_height,
            "raw_width": raw_width,
            "raw_height": raw_height,
            "fps": fps,
            "duration": duration,
            "rotation": rotation,
            "aspect_ratio": display_aspect_ratio,
        }

    # =========================================================
    # CROPDETECT
    # =========================================================

    def detect_content_crop(
        self,
        source_path: Path,
        start: float,
        duration: float,
        source_width: int,
        source_height: int,
    ) -> dict | None:
        """
        Ищет большие embedded black bars / поля.

        Это НЕ основной crop mechanism.
        Он используется только как дополнительная проверка
        вертикальных источников.

        Если найденная область слишком мала или почти совпадает
        с исходным кадром — результат игнорируется.
        """

        if duration <= 0:
            return None

        analysis_duration = min(
            max(duration, 1.0),
            5.0,
        )

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-ss",
            str(start),
            "-i",
            str(source_path),
            "-t",
            str(analysis_duration),
            "-vf",
            (
                "cropdetect="
                "limit=24:"
                "round=2:"
                f"reset={self.CROPDETECT_FRAMES}"
            ),
            "-an",
            "-f",
            "null",
            "-",
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            print(
                "       CropDetect: "
                "FFmpeg завершился с ошибкой → игнорируем"
            )
            return None

        log = result.stderr

        matches = re.findall(
            r"crop=(\d+):(\d+):(\d+):(\d+)",
            log,
        )

        if not matches:
            return None

        detected = []

        for width, height, x, y in matches:
            detected.append(
                {
                    "width": int(width),
                    "height": int(height),
                    "x": int(x),
                    "y": int(y),
                }
            )

        if not detected:
            return None

        crop = detected[-1]

        crop_width = crop["width"]
        crop_height = crop["height"]

        width_ratio = crop_width / source_width
        height_ratio = crop_height / source_height

        area_ratio = (
            crop_width * crop_height
        ) / (
            source_width * source_height
        )

        print(
            f"       CropDetect: "
            f"{crop_width}x{crop_height}"
            f"+{crop['x']}+{crop['y']} "
            f"area={area_ratio:.3f}"
        )

        if (
            width_ratio < self.MIN_DETECTED_WIDTH_RATIO
            or height_ratio < self.MIN_DETECTED_HEIGHT_RATIO
        ):
            print(
                "       CropDetect: "
                "область слишком мала → игнорируем"
            )
            return None

        if area_ratio >= self.CONTENT_AREA_THRESHOLD:
            print(
                "       CropDetect: "
                "существенных полей не обнаружено"
            )
            return None

        if crop["x"] < 0 or crop["y"] < 0:
            return None

        if (
            crop["x"] + crop_width > source_width
            or crop["y"] + crop_height > source_height
        ):
            return None

        print(
            "       CropDetect: "
            "обнаружена уменьшенная область контента"
        )

        return crop

    # =========================================================
    # GEOMETRIC FALLBACK
    # =========================================================

    def build_smart_crop_filter(
        self,
        source_width: int,
        source_height: int,
        target_width: int,
        target_height: int,
        detected_crop: dict | None = None,
    ) -> tuple[str, str]:
        """
        Геометрический fallback.

        Smart Framing вызывается отдельно.

        Этот метод НЕ пытается быть Smart Framing.
        Его задача — гарантированно получить target resolution,
        если CV decision отсутствует или отклонён quality gate.
        """

        source_aspect = (
            source_width / source_height
        )

        target_aspect = (
            target_width / target_height
        )

        aspect_difference = abs(
            source_aspect - target_aspect
        )

        # -----------------------------------------------------
        # Embedded content
        # -----------------------------------------------------

        if detected_crop is not None:
            crop_width = detected_crop["width"]
            crop_height = detected_crop["height"]
            crop_x = detected_crop["x"]
            crop_y = detected_crop["y"]

            content_aspect = (
                crop_width / crop_height
            )

            if (
                abs(
                    content_aspect - target_aspect
                )
                < self.SMART_ASPECT_TOLERANCE
            ):
                vf = (
                    f"crop={crop_width}:{crop_height}:"
                    f"{crop_x}:{crop_y},"
                    f"scale={target_width}:{target_height}:"
                    "flags=lanczos"
                )

                return (
                    vf,
                    "EMBEDDED_CONTENT_MATCHED_ASPECT",
                )

            vf = (
                f"crop={crop_width}:{crop_height}:"
                f"{crop_x}:{crop_y},"
                f"scale={target_width}:{target_height}:"
                "flags=lanczos:"
                "force_original_aspect_ratio=increase,"
                f"crop={target_width}:{target_height}:"
                "(in_w-out_w)/2:"
                "(in_h-out_h)/2"
            )

            return (
                vf,
                "EMBEDDED_CONTENT_CROP",
            )

        # -----------------------------------------------------
        # Matched aspect
        # -----------------------------------------------------

        if (
            self.PROTECT_MATCHED_ASPECT
            and aspect_difference
            < self.SMART_ASPECT_TOLERANCE
        ):
            vf = (
                f"scale={target_width}:{target_height}:"
                "flags=lanczos"
            )

            return (
                vf,
                "MATCHED_ASPECT_FULL_FRAME",
            )

        # -----------------------------------------------------
        # Vertical
        # -----------------------------------------------------

        if source_aspect < 1.0:
            vf = (
                f"scale={target_width}:{target_height}:"
                "flags=lanczos:"
                "force_original_aspect_ratio=increase,"
                f"crop={target_width}:{target_height}:"
                "(in_w-out_w)/2:"
                "(in_h-out_h)/2"  # Было /2. Смещение к верху кадра!
            )

            return (
                vf,
                "PORTRAIT_TOP_CROP_FALLBACK",
            )

        # -----------------------------------------------------
        # Horizontal
        # -----------------------------------------------------

        if source_aspect >= 1.0:
            vf = (
                f"scale={target_width}:{target_height}:"
                "flags=lanczos:"
                "force_original_aspect_ratio=increase,"
                f"crop={target_width}:{target_height}:"
                "(in_w-out_w)/2:"
                "(in_h-out_h)/2"  # Было /2. Смещение к верху кадра!
            )

            return (
                vf,
                "LANDSCAPE_TOP_CROP_FALLBACK",
            )

        # -----------------------------------------------------
        # Absolute fallback
        # -----------------------------------------------------

        vf = (
            f"scale={target_width}:{target_height}:"
            "flags=lanczos:"
            "force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height}:"
            "(in_w-out_w)/2:"
            "(in_h-out_h)/2"  # Было /2
        )

        return (
            vf,
            "FALLBACK_CENTER_CROP",
        )

    # =========================================================
    # SMART FRAMING QUALITY GATE
    # =========================================================

    def validate_smart_decision(
        self,
        decision,
        source_width: int,
        source_height: int,
        target_width: int,
        target_height: int,
    ) -> tuple[bool, str]:
        """
        Проверяет, не испортил ли Smart Framing кадр.

        Критически важно:

        Smart Framing может выбирать композицию,
        но не имеет права незаметно уменьшать usable source area.

        Проверяем:

        - размеры;
        - координаты;
        - target aspect;
        - соответствие source dimensions;
        - crop area относительно максимально возможного
          target-AR crop.
        """

        if decision is None:
            return False, "decision=None"

        try:
            x = int(decision.x)
            y = int(decision.y)
            width = int(decision.width)
            height = int(decision.height)

            decision_source_width = int(
                decision.source_width
            )
            decision_source_height = int(
                decision.source_height
            )

        except (
            AttributeError,
            TypeError,
            ValueError,
        ):
            return False, "некорректная структура CropDecision"

        if width <= 0 or height <= 0:
            return False, (
                f"некорректный crop {width}x{height}"
            )

        if x < 0 or y < 0:
            return False, (
                f"отрицательные координаты {x},{y}"
            )

        if (
            x + width > source_width
            or y + height > source_height
        ):
            return False, (
                "crop выходит за границы исходного кадра"
            )

        if (
            decision_source_width != source_width
            or decision_source_height != source_height
        ):
            return False, (
                "размеры CropDecision не совпадают "
                "с display-размерами исходника"
            )

        crop_aspect = width / height

        target_aspect = (
            target_width / target_height
        )

        aspect_error = abs(
            crop_aspect - target_aspect
        )

        # Допускаем небольшую погрешность округления.
        if aspect_error > 0.03:
            return False, (
                f"неверный aspect ratio: "
                f"crop={crop_aspect:.4f}, "
                f"target={target_aspect:.4f}"
            )

        # -----------------------------------------------------
        # Максимально возможный crop target AR.
        #
        # Это не означает, что Smart Framing обязан брать
        # весь этот прямоугольник.
        #
        # Но если decision внезапно отдаёт сильно меньшую
        # область — это почти наверняка плохое решение.
        # -----------------------------------------------------

        source_aspect = (
            source_width / source_height
        )

        if source_aspect >= target_aspect:
            max_crop_width = source_width
            max_crop_height = int(
                round(
                    source_width / target_aspect
                )
            )
        else:
            max_crop_height = source_height
            max_crop_width = int(
                round(
                    source_height * target_aspect
                )
            )

        max_crop_width = min(
            max_crop_width,
            source_width,
        )

        max_crop_height = min(
            max_crop_height,
            source_height,
        )

        max_area = (
            max_crop_width
            * max_crop_height
        )

        decision_area = width * height

        if max_area <= 0:
            return False, "невозможно вычислить максимальную площадь"

        area_ratio = (
            decision_area / max_area
        )

        if (
            area_ratio
            < self.MIN_SMART_CROP_AREA_RATIO
        ):
            return False, (
                f"Smart Crop слишком мал: "
                f"{width}x{height}, "
                f"max={max_crop_width}x{max_crop_height}, "
                f"area_ratio={area_ratio:.3f}"
            )

        return True, (
            f"quality OK, "
            f"area_ratio={area_ratio:.3f}"
        )

    # =========================================================
    # SMART FRAMING
    # =========================================================

    def analyze_smart_framing(
        self,
        source_path: Path,
        start: float,
        duration: float,
        target_width: int,
        target_height: int,
        source_width: int,
        source_height: int,
    ):
        """
        Запускает локальный Smart Framing.

        Важно:
        - matching aspect сюда не должен доходить;
        - rotation 90/270 сюда не должен доходить;
        - низкое разрешение НЕ является автоматическим отказом.
        """

        if duration <= 0:
            return None

        source_aspect = (
            source_width / source_height
        )

        target_aspect = (
            target_width / target_height
        )

        # -----------------------------------------------------
        # Matched aspect — Smart Framing не нужен.
        # -----------------------------------------------------

        if (
            abs(source_aspect - target_aspect)
            < self.SMART_ASPECT_TOLERANCE
        ):
            print(
                "       Smart Framing: "
                "пропущен — исходник уже в целевом aspect ratio"
            )
            return None

        # -----------------------------------------------------
        # Detector
        # -----------------------------------------------------

        print(
            "       Smart Framing: "
            "локальный CV-анализ..."
        )

        analyses = (
            self.smart_detector.detect_video_samples(
                video_path=str(source_path),
                sample_count=(
                    self.smart_framing_config.sample_count
                ),
                start_time=start,
                duration=duration,
            )
        )

        if not analyses:
            print(
                "       Smart Framing: "
                "детекции отсутствуют → fallback"
            )
            return None

        people_count = sum(
            len(frame.persons)
            for frame in analyses
        )

        face_count = sum(
            len(frame.faces)
            for frame in analyses
        )

        head_count = sum(
            len(frame.heads)
            for frame in analyses
        )

        text_count = sum(
            len(frame.text_regions)
            for frame in analyses
        )

        logo_count = sum(
            len(frame.logos)
            for frame in analyses
        )

        print(
            "       Smart Framing detections: "
            f"frames={len(analyses)}, "
            f"people={people_count}, "
            f"faces={face_count}, "
            f"heads={head_count}, "
            f"text={text_count}, "
            f"logos={logo_count}"
        )

        # -----------------------------------------------------
        # Analyzer
        # -----------------------------------------------------

        decision = self.smart_analyzer.analyze(
            analyses=analyses,
            target_width=target_width,
            target_height=target_height,
        )

        if decision is None:
            print(
                "       Smart Framing: "
                "decision отсутствует → fallback"
            )
            return None

        print(
            "       Smart Framing decision: "
            f"{decision.strategy.value}, "
            f"crop={decision.width}x{decision.height}"
            f"+{decision.x}+{decision.y}, "
            f"score={decision.score:.3f}"
        )

        # -----------------------------------------------------
        # Existing analyzer score
        # -----------------------------------------------------

        if (
            decision.score
            < self.smart_framing_config.minimum_decision_score
        ):
            print(
                "       Smart Framing: "
                f"score={decision.score:.3f} "
                "ниже порога → fallback"
            )
            return None

        # -----------------------------------------------------
        # Quality gate
        # -----------------------------------------------------

        valid, reason = (
            self.validate_smart_decision(
                decision=decision,
                source_width=source_width,
                source_height=source_height,
                target_width=target_width,
                target_height=target_height,
            )
        )

        if not valid:
            print(
                "       Smart Framing: "
                f"QUALITY GATE REJECT → {reason}"
            )
            return None

        print(
            "       Smart Framing: "
            f"QUALITY GATE PASS → {reason}"
        )

        # Информационное предупреждение, но НЕ rejection.
        if source_width < self.LOW_RES_SOURCE_WIDTH:
            print(
                "       Smart Framing: "
                f"low-res source ({source_width}px width), "
                "но decision разрешён"
            )

        gc.collect()

        return decision

    # =========================================================
    # COLOR ANALYSIS
    # =========================================================

    def analyze_color(
        self,
        source_path: Path,
        start: float,
        duration: float,
    ) -> dict | None:
        """
        Измеряет YAVG и SATAVG через FFmpeg signalstats.
        """

        if duration <= 0:
            return None

        analysis_duration = min(
            max(duration, 1.0),
            self.COLOR_ANALYSIS_MAX_SECONDS,
        )

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-ss",
            str(start),
            "-i",
            str(source_path),
            "-t",
            str(analysis_duration),
            "-vf",
            (
                f"fps={self.COLOR_ANALYSIS_FPS},"
                "signalstats,"
                "metadata=print"
            ),
            "-an",
            "-f",
            "null",
            "-",
        ]

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            print(
                "       Color Analysis: "
                "FFmpeg signalstats ошибка → пропускаем"
            )
            return None

        log = result.stderr

        y_values = [
            float(value)
            for value in re.findall(
                r"lavfi\.signalstats\.YAVG="
                r"([-+]?\d+(?:\.\d+)?)",
                log,
            )
        ]

        sat_values = [
            float(value)
            for value in re.findall(
                r"lavfi\.signalstats\.SATAVG="
                r"([-+]?\d+(?:\.\d+)?)",
                log,
            )
        ]

        if not y_values or not sat_values:
            print(
                "       Color Analysis: "
                "YAVG/SATAVG не получены → пропускаем"
            )
            return None

        return {
            "yavg": self.median(y_values),
            "satavg": self.median(sat_values),
        }

    # =========================================================
    # MEDIAN
    # =========================================================

    @staticmethod
    def median(values: list[float]) -> float:
        if not values:
            raise ValueError(
                "Невозможно вычислить медиану пустого списка."
            )

        ordered = sorted(values)

        middle = len(ordered) // 2

        if len(ordered) % 2:
            return ordered[middle]

        return (
            ordered[middle - 1]
            + ordered[middle]
        ) / 2.0

    # =========================================================
    # COLOR FILTER
    # =========================================================

    def build_color_normalization_filter(
        self,
        color_stats: dict | None,
    ) -> tuple[str, dict]:
        if not color_stats:
            return "", {
                "enabled": False,
                "brightness": 0.0,
                "saturation": 1.0,
            }

        target_yavg = color_stats["target_yavg"]
        target_satavg = color_stats["target_satavg"]

        source_yavg = color_stats["yavg"]
        source_satavg = color_stats["satavg"]

        brightness = (
            target_yavg - source_yavg
        ) / 255.0

        brightness = max(
            self.COLOR_MIN_BRIGHTNESS,
            min(
                self.COLOR_MAX_BRIGHTNESS,
                brightness,
            ),
        )

        if source_satavg > 0:
            saturation = (
                target_satavg / source_satavg
            )
        else:
            saturation = 1.0

        saturation = max(
            self.COLOR_MIN_SATURATION,
            min(
                self.COLOR_MAX_SATURATION,
                saturation,
            ),
        )

        if (
            abs(brightness) < 0.005
            and abs(saturation - 1.0) < 0.02
        ):
            brightness = 0.0
            saturation = 1.0
            filter_expression = ""
        else:
            filter_expression = (
                "eq="
                f"brightness={brightness:.5f}:"
                f"saturation={saturation:.5f}"
            )

        return filter_expression, {
            "enabled": bool(filter_expression),
            "brightness": brightness,
            "saturation": saturation,
            "source_yavg": source_yavg,
            "source_satavg": source_satavg,
            "target_yavg": target_yavg,
            "target_satavg": target_satavg,
        }

    # =========================================================
    # NORMALIZE CUT
    # =========================================================

    def normalize_cut(
        self,
        filename: str,
        start: float,
        end: float,
        index: int,
        profile,
        color_stats: dict | None = None,
        keep_source_audio: bool = False,  # <--- Добавлен параметр с дефолтом False
    ) -> Path:
        source_path = self.download_dir / filename

        # Если файл не найден напрямую, пробуем найти файл с таким же именем на диске
        if not source_path.exists():
            matches = list(self.download_dir.glob(f"*{filename}*"))
            if matches:
                source_path = matches[0]
            else:
                raise FileNotFoundError(
                    f"Исходный файл не найден: {source_path}"
                )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = (
            self.output_dir
            / f"cut_{index:03d}.mp4"
        )

        duration = end - start

        if duration <= 0:
            raise ValueError(
                f"Некорректный диапазон "
                f"{start} → {end} "
                f"для {filename}"
            )

        # -----------------------------------------------------
        # Probe
        # -----------------------------------------------------

        probe = self.probe_video(
            source_path
        )

        source_width = probe["width"]
        source_height = probe["height"]
        source_fps = probe["fps"]
        source_duration = probe["duration"]
        source_aspect = probe["aspect_ratio"]
        rotation = probe["rotation"]

        target_width = profile.width
        target_height = profile.height

        target_aspect = (
            target_width / target_height
        )

        print()
        print(
            f"   [{index}] {filename} "
            f"[{start:.3f}s - {end:.3f}s]"
        )

        print(
            f"       Source: "
            f"{source_width}x{source_height} "
            f"AR={source_aspect:.3f} "
            f"FPS={source_fps:.3f}"
        )

        if rotation:
            print(
                f"       Rotation metadata: "
                f"{rotation:.0f}°"
            )

        if source_duration is not None:
            print(
                f"       Source duration: "
                f"{source_duration:.3f}s"
            )

        print(
            f"       Target: "
            f"{target_width}x{target_height} "
            f"AR={target_aspect:.3f}"
        )

        # -----------------------------------------------------
        # 1. Embedded content / CropDetect
        # -----------------------------------------------------

        detected_crop = None

        if source_aspect < 1.0:
            print(
                "       CropDetect: "
                "анализ вертикального исходника..."
            )

            detected_crop = (
                self.detect_content_crop(
                    source_path=source_path,
                    start=start,
                    duration=duration,
                    source_width=source_width,
                    source_height=source_height,
                )
            )

        # -----------------------------------------------------
        # 2. Matched aspect — PROTECTED
        # -----------------------------------------------------

        aspect_difference = abs(
            source_aspect - target_aspect
        )

        if (
            self.PROTECT_MATCHED_ASPECT
            and aspect_difference
            < self.SMART_ASPECT_TOLERANCE
            and detected_crop is None
        ):
            vf = (
                f"scale={target_width}:{target_height}:"
                "flags=lanczos"
            )

            strategy = (
                "MATCHED_ASPECT_FULL_FRAME"
            )

            print(
                "       Smart Framing: "
                "SKIP — matched aspect"
            )

        else:
            # -------------------------------------------------
            # 3. Smart Framing
            # -------------------------------------------------

            smart_decision = None

            if rotation in (90.0, 270.0):
                print(
                    "       Smart Framing: "
                    "SKIP — rotated source, "
                    "safe geometry fallback"
                )
            else:
                smart_decision = (
                    self.analyze_smart_framing(
                        source_path=source_path,
                        start=start,
                        duration=duration,
                        target_width=target_width,
                        target_height=target_height,
                        source_width=source_width,
                        source_height=source_height,
                    )
                )

            # -------------------------------------------------
            # 4. Smart decision accepted
            # -------------------------------------------------

            if smart_decision is not None:
                vf = (
                    self.smart_crop_engine
                    .build_filter(
                        smart_decision
                    )
                )

                strategy = (
                    smart_decision
                    .strategy
                    .value
                )

                print(
                    "       Smart Framing: "
                    "APPLIED"
                )

            # -------------------------------------------------
            # 5. Fallback
            # -------------------------------------------------

            else:
                vf, strategy = (
                    self.build_smart_crop_filter(
                        source_width=source_width,
                        source_height=source_height,
                        target_width=target_width,
                        target_height=target_height,
                        detected_crop=detected_crop,
                    )
                )

                print(
                    "       Smart Framing: "
                    "FALLBACK → "
                    f"{strategy}"
                )

        # -----------------------------------------------------
        # Color Normalization
        # -----------------------------------------------------

        color_filter, color_info = (
            self.build_color_normalization_filter(
                color_stats
            )
        )

        if color_filter:
            vf = (
                f"{vf},{color_filter}"
            )

            print(
                "       Color Normalization: "
                f"brightness="
                f"{color_info['brightness']:+.4f}, "
                f"saturation="
                f"{color_info['saturation']:.3f}"
            )
        else:
            print(
                "       Color Normalization: "
                "коррекция не требуется"
            )

        print(
            f"       Smart Crop strategy: "
            f"{strategy}"
        )

        print(
            f"       → {profile.name}: "
            f"{profile.width}x{profile.height}"
        )

        # -----------------------------------------------------
        # FFmpeg
        # -----------------------------------------------------

        # Собираем инпуты и временные сдвиги
        command = [
            "ffmpeg",
            "-y",
            "-i", str(source_path),
            "-ss", str(start),
        ]

        # Добавляем генератор тишины, если оригинальный звук выключен
        if not keep_source_audio:
            command.extend([
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            ])

        # Параметры видео и ограничение длительности
        command.extend([
            "-t", str(duration),
            "-vf", vf,
            "-r", str(profile.fps),
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "17",
            "-pix_fmt", "yuv420p",
        ])

        # Обработка аудиопотока и явный маппинг
        if keep_source_audio:
            command.extend([
                "-map", "0:v:0",   # Видео из первого файла (source_path)
                "-map", "0:a:0?",  # Аудио из первого файла (если есть)
                "-c:a", "aac",
                "-b:a", "192k",
            ])
        else:
            command.extend([
                "-map", "0:v:0",   # Видео из первого файла (source_path)
                "-map", "1:a:0",   # Аудио из второго файла (anullsrc)
                "-c:a", "aac",
                "-shortest",
            ])

        command.append(str(output_path))

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "FFmpeg ошибка при нормализации "
                f"{filename}:\n"
                f"{result.stderr}"
            )

        if not output_path.exists():
            raise RuntimeError(
                "FFmpeg завершился без создания файла: "
                f"{output_path}"
            )

        # -----------------------------------------------------
        # Проверка результата
        # -----------------------------------------------------

        output_probe = self.probe_video(
            output_path
        )

        if (
            output_probe["width"]
            != target_width
            or output_probe["height"]
            != target_height
        ):
            raise RuntimeError(
                "Нормализованный файл имеет "
                "неверный размер: "
                f"{output_probe['width']}x"
                f"{output_probe['height']}, "
                f"ожидалось "
                f"{target_width}x"
                f"{target_height}"
            )

        print(
            f"       ✓ Создан: "
            f"{output_path.name}"
        )

        print(
            f"       ✓ Проверка: "
            f"{output_probe['width']}x"
            f"{output_probe['height']} "
            f"@ {output_probe['fps']:.3f} FPS"
        )

        return output_path

    # =========================================================
    # NORMALIZE PLAN
    # =========================================================

    def normalize_plan(self) -> list[Path]:
        plan = self.load_plan()

        format_name = (
            self.get_output_format(plan)
        )

        profile = get_format_profile(
            format_name
        )

        cuts = plan.get(
            "cuts",
            [],
        )

        if not cuts:
            raise ValueError(
                "В montage_plan.json "
                "отсутствует массив cuts."
            )

        print()
        print("=" * 60)
        print(
            " VIDEO AI ENGINE — "
            "SMART FORMAT ADAPTER v3"
        )
        print("=" * 60)

        print(
            f"[Formatter] Формат: "
            f"{profile.name}"
        )

        print(
            f"[Formatter] Размер: "
            f"{profile.width}x{profile.height}"
        )

        print(
            f"[Formatter] FPS: "
            f"{profile.fps}"
        )

        print(
            f"[Formatter] Фрагментов: "
            f"{len(cuts)}"
        )

        # -----------------------------------------------------
        # Temporary output directory
        # -----------------------------------------------------

        self.prepare_output_dir()

        # -----------------------------------------------------
        # PASS 1 — Color Analysis
        # -----------------------------------------------------

        print()
        print(
            "[Formatter] PASS 1 — "
            "Color Analysis"
        )

        color_results = []

        for index, cut in enumerate(
            cuts,
            start=1,
        ):
            file_id = cut.get("file_id")
            raw_filename = (
                cut.get("source")
                or cut.get("filename")
                or cut.get("file")
                or "video.mp4"
            )

            # 1. Попытка найти файл по file_id
            source_path = None
            if file_id:
                ext = Path(raw_filename).suffix or ".mp4"
                candidate = self.download_dir / f"{file_id}{ext}"
                if candidate.exists():
                    source_path = candidate

            # 2. Фолбэк: поиск по обычному имени файла
            if not source_path or not source_path.exists():
                source_path = self.download_dir / raw_filename

            if not source_path.exists():
                raise FileNotFoundError(
                    f"Cut #{index}: исходник не найден "
                    f"(искали {file_id or raw_filename} в {self.download_dir})"
                )

            filename = source_path.name

            start = float(cut.get("start", 0.0))
            end = float(cut.get("end", 0.0))
            duration = end - start

            print(
                f"   [{index}] "
                f"{filename}"
            )

            stats = self.analyze_color(
                source_path=source_path,
                start=start,
                duration=duration,
            )

            if stats:
                print(
                    f"       YAVG="
                    f"{stats['yavg']:.2f}, "
                    f"SATAVG="
                    f"{stats['satavg']:.2f}"
                )
            else:
                print(
                    "       Color Analysis: "
                    "нет данных"
                )

            color_results.append(
                {
                    "filename": filename,
                    "start": start,
                    "end": end,
                    "stats": stats,
                }
            )

        # -----------------------------------------------------
        # Общий color baseline
        # -----------------------------------------------------

        valid_color_stats = [
            item["stats"]
            for item in color_results
            if item["stats"] is not None
        ]

        if valid_color_stats:
            target_yavg = self.median(
                [
                    item["yavg"]
                    for item in valid_color_stats
                ]
            )

            target_satavg = self.median(
                [
                    item["satavg"]
                    for item in valid_color_stats
                ]
            )

            print()
            print(
                "[Formatter] Color baseline: "
                f"YAVG={target_yavg:.2f}, "
                f"SATAVG={target_satavg:.2f}"
            )

            for item in color_results:
                if item["stats"] is not None:
                    item["stats"][
                        "target_yavg"
                    ] = target_yavg

                    item["stats"][
                        "target_satavg"
                    ] = target_satavg

        # -----------------------------------------------------
        # PASS 2 — Normalize
        # -----------------------------------------------------

        print()
        print(
            "[Formatter] PASS 2 — "
            "Smart Normalization"
        )

        normalized_paths = []

        for index, item in enumerate(
            color_results,
            start=1,
        ):
            output_path = self.normalize_cut(
                filename=item["filename"],
                start=item["start"],
                end=item["end"],
                index=index,
                profile=profile,
                color_stats=item["stats"],
            )

            normalized_paths.append(
                output_path
            )

            gc.collect()

        print()
        print("=" * 60)
        print(
            "[Formatter] ✓ Нормализация завершена"
        )
        print(
            f"[Formatter] Создано файлов: "
            f"{len(normalized_paths)}"
        )
        print("=" * 60)

        return normalized_paths


# =============================================================
# MAIN
# =============================================================

def main():
    normalizer = VideoNormalizer()

    normalizer.normalize_plan()


if __name__ == "__main__":
    main()