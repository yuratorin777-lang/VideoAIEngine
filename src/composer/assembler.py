import json
import os
import random
import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
import moviepy.audio.fx as afx
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    VideoFileClip,
    concatenate_videoclips,
)

from src.composer.branding import apply_brand_logo
from src.composer.subtitle_layout import layout_subtitle_text
from src.composer.subtitle_style_selector import select_subtitle_style
from src.composer.subtitle_styles import (
    calculate_font_size,
    calculate_margin_bottom,
    get_subtitle_style,
)
from src.graphics.overlay_generator import OverlayGenerator

# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ============================================================
# TEMP DIRECTORIES
# ============================================================

DOWNLOAD_DIR = BASE_DIR / "temp_downloads"
NORMALIZED_DIR = BASE_DIR / "temp_normalized"


# ============================================================
# SUBTITLE SYNC
# ============================================================

SUBTITLE_EARLY_OFFSET = 0.20


# ============================================================
# OUTPUT QUALITY
# ============================================================

VIDEO_CODEC = "libx264"
VIDEO_PRESET = "slow"
VIDEO_CRF = "17"
VIDEO_PIXEL_FORMAT = "yuv420p"

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"

OUTPUT_FPS = 30


# ============================================================
# TARGET DURATION
# ============================================================

DEFAULT_TARGET_DURATION = 20.0


# ============================================================
# PATH RESOLVER
# ============================================================


def resolve_path(relative_or_absolute_path: str) -> Path:
    path = Path(relative_or_absolute_path)

    if not path.is_absolute():
        return BASE_DIR / path

    return path


# ============================================================
# FFmpeg RESOLVER
# ============================================================


def get_ffmpeg_path() -> str:
    """Возвращает путь к FFmpeg от imageio_ffmpeg или системный."""
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# ============================================================
# COVER & FRAME EXTRACTION PROCESSING
# ============================================================


def extract_frame_from_video(
    video_path: str | Path,
    output_frame_path: str | Path,
    time_offset: float = 0.5,
) -> Path:
    """Вырезает кадр из видео для использования в качестве фона обложки."""
    video = resolve_path(str(video_path))
    output_frame = resolve_path(str(output_frame_path))
    ffmpeg_bin = get_ffmpeg_path()

    cmd = [
        ffmpeg_bin,
        "-y",
        "-ss",
        str(time_offset),
        "-i",
        str(video),
        "-vframes",
        "1",
        "-q:v",
        "2",
        str(output_frame),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[FrameExtract] Ошибка при вырезании кадра: {e}")

    return output_frame


import random
from pathlib import Path

def generate_cover_image(
    video_path: str | Path,
    cover_title: str,
    brand_name: str = "dance_kids",
    is_landscape: bool = False,
    output_png_path: str | Path | None = None,
    raw_source_video: str | Path | None = None,
) -> Path | None:
    """Генерирует обложку для видео с использованием HTML/CSS-шаблонов Playwright."""

    try:
        # Если путь не передан, сохраняем по умолчанию в output/covers/
        if output_png_path is None:
            video_stem = Path(video_path).stem
            output_dir = BASE_DIR / "output" / "covers"
            output_dir.mkdir(parents=True, exist_ok=True)  # Автоматически создает папку, если ее нет
            out_path = output_dir / f"cover_{video_stem}.png"
        else:
            out_path = resolve_path(str(output_png_path))
            out_path.parent.mkdir(parents=True, exist_ok=True)

        temp_frame = out_path.parent / f"temp_bg_{out_path.stem}.jpg"

        # Если передан чистый исходник — берем из него, иначе пробуем из переданного файла
        target_video_for_frame = raw_source_video or video_path
        frame_extracted = False

        if target_video_for_frame and Path(target_video_for_frame).exists():
            try:
                # Вырезаем случайный кадр (от 2.0 до 5.0 сек)
                random_offset = round(random.uniform(2.0, 5.0), 2)
                extract_frame_from_video(target_video_for_frame, temp_frame, time_offset=random_offset)
                if temp_frame.exists() and temp_frame.stat().st_size > 0:
                    frame_extracted = True
                    print(f"[Cover] Вырезан чистый кадр из видео (метка {random_offset}s)")
            except Exception as e:
                print(f"[Cover] Ошибка вырезки кадра из видео: {e}")

        # ФОЛЛБЭК: Если кадр не вырезался или видео повреждено — берем из папки backgrounds
        bg_path = temp_frame
        if not frame_extracted:
            print("[Cover] Кадр из видео не получен. Переходим к фоллбэку из папки backgrounds...")
            bg_dir = BASE_DIR / f"04_LIBRARY/brands/{brand_name}/backgrounds"
            if bg_dir.exists():
                bg_files = (
                    list(bg_dir.glob("*.png"))
                    + list(bg_dir.glob("*.jpg"))
                    + list(bg_dir.glob("*.jpeg"))
                )
                if bg_files:
                    bg_path = random.choice(bg_files)
                    print(f"[Cover] Выбран фоновый рисунок из библиотеки: {bg_path.name}")

        # 2. Выбор логотипа бренда
        brand_dir = BASE_DIR / f"04_LIBRARY/brands/{brand_name}"
        logo_files = [
            f for f in brand_dir.glob("logo*.*")
            if f.suffix.lower() in [".png", ".jpg", ".jpeg", ".svg"]
        ]
        logo_path = random.choice(logo_files) if logo_files else ""

        # 3. Выбор шаблона обложки
        if is_landscape:
            cover_templates = ["cover_landscape_classic.html"]
        else:
            cover_templates = [
                "cover_classic.html",
                "cover_badge.html",
                "cover_bold.html",
            ]

        selected_template = random.choice(cover_templates)
        print(f"[Cover] Шаблон обложки: {selected_template}")

        # 4. Рендер через Playwright
        generator = OverlayGenerator()
        context = {
            "background_path": bg_path,
            "logo_path": logo_path,
            "title": cover_title,
        }

        generator.generate_image(
            template_name=selected_template,
            context=context,
            output_path=str(out_path),
            is_landscape=is_landscape,  # <-- ПЕРЕДАЕМ ФЛАГ ЗДЕСЬ
        )

        if temp_frame.exists():
            temp_frame.unlink()

        return out_path

    except Exception as e:
        print(f"[Cover Generator] Ошибка генерации обложки, пропускаем: {e}")
        return None


def apply_cover_overlay(
    input_video_path: str | Path,
    cover_image_path: str | Path,
    output_video_path: str | Path,
    duration: float = 1.5,
) -> Path:
    input_video = resolve_path(str(input_video_path))
    cover_image = resolve_path(str(cover_image_path))
    output_video = resolve_path(str(output_video_path))

    if not cover_image.exists():
        print(f"[CoverOverlay] Предупреждение: Файл обложки {cover_image} не найден. Пропуск.")
        return input_video

    ffmpeg_bin = get_ffmpeg_path()
    
    # Создаем временный файл в сторонней папке или с уникальным именем
    temp_output = output_video.parent / f"temp_final_{output_video.name}"

    # Надежный фильтр:
    # 1. Берем обложку [1:v] и закольцовываем
    # 2. Масштабируем обложку [1:v] под точные W x H основного видео [0:v]
    # 3. Накладываем обложку на видео на первые N секунд
    filter_complex = (
        f"[1:v]loop=loop=-1:size=1:start=0[cover_loop];"
        f"[cover_loop][0:v]scale2ref=w=iw:h=ih[cover_scaled][main];"
        f"[main][cover_scaled]overlay=0:0:enable='between(t,0,{duration})':shortest=1[v]"
    )

    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(input_video),
        "-i", str(cover_image),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",  # Сохраняем аудио из исходного видео
        "-c:v", VIDEO_CODEC,
        "-preset", VIDEO_PRESET,
        "-crf", str(VIDEO_CRF),
        "-pix_fmt", VIDEO_PIXEL_FORMAT,
        "-c:a", "copy",
        str(temp_output),
    ]

    print(f"[CoverOverlay] Автоматическое наложение обложки на первые {duration} сек...")
    
    # Запускаем БЕЗ DEVNULL, чтобы в случае ошибки увидеть лог
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[CoverOverlay] ❌ Ошибка FFmpeg при наложении обложки:\n{result.stderr}")
        print("[CoverOverlay] Возвращаем исходное видео без обложки.")
        return input_video

    # Если всё прошло успешно, подменяем целевой файл
    if temp_output.exists() and temp_output.stat().st_size > 1000000: # проверяем что файл больше 1МБ
        if output_video.exists() and output_video != input_video:
            output_video.unlink()
        shutil.move(str(temp_output), str(output_video))
        print(f"[CoverOverlay] ✓ Обложка успешно наложена, размер: {output_video.stat().st_size / (1024*1024):.2f} MB")
    else:
        print("[CoverOverlay] ⚠️ Итоговый файл получился слишком маленьким или не создался. Откат к исходнику.")
        if temp_output.exists():
            temp_output.unlink()
        return input_video

    return output_video


# ============================================================
# TIME HELPERS
# ============================================================

def srt_time_to_seconds(value: str) -> float:
    """
    SRT:
        HH:MM:SS,mmm
    ->
        секунды
    """

    value = value.strip()

    match = re.match(
        r"(\d+):(\d{2}):(\d{2}),(\d{3})",
        value,
    )

    if not match:
        raise ValueError(
            f"Некорректное SRT-время: {value}"
        )

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    milliseconds = int(match.group(4))

    return (
        hours * 3600
        + minutes * 60
        + seconds
        + milliseconds / 1000.0
    )


def seconds_to_ass_time(seconds: float) -> str:
    """
    Секунды -> ASS:
        H:MM:SS.cc
    """

    seconds = max(
        0.0,
        float(seconds),
    )

    total_centiseconds = int(
        round(seconds * 100)
    )

    hours = (
        total_centiseconds // 360000
    )

    remainder = (
        total_centiseconds % 360000
    )

    minutes = (
        remainder // 6000
    )

    remainder = (
        remainder % 6000
    )

    secs = (
        remainder // 100
    )

    centiseconds = (
        remainder % 100
    )

    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{centiseconds:02d}"
    )


# ============================================================
# SRT -> ASS
# ============================================================

def srt_to_ass(
    srt_path: Path,
    ass_path: Path,
    video_width: int,
    video_height: int,
    style_name: str = "dance",
):
    """
    Конвертирует SRT -> ASS.

    Выполняются:

    1. выбор Subtitle Style;
    2. расчёт размера шрифта;
    3. расчёт позиции;
    4. Subtitle Layout Engine;
    5. нормализация тайминга;
    6. генерация ASS.

    Синхронизация сохраняется:
        SUBTITLE_EARLY_OFFSET = 0.20
    """

    # --------------------------------------------------------
    # ЧТЕНИЕ SRT
    # --------------------------------------------------------

    content = ""

    for enc in [
        "utf-8-sig",
        "utf-8",
        "utf-16",
        "cp1251",
    ]:

        try:

            with open(
                srt_path,
                "r",
                encoding=enc,
            ) as f:

                content = f.read()

            if content.strip():
                break

        except UnicodeDecodeError:
            continue

    if not content.strip():

        raise ValueError(
            f"Не удалось прочитать SRT файл "
            f"{srt_path} ни в одной кодировке."
        )

    # --------------------------------------------------------
    # STYLE ENGINE
    # --------------------------------------------------------

    style = get_subtitle_style(
        style_name
    )

    font_size = calculate_font_size(
        video_height,
        style,
    )

    margin_bottom = calculate_margin_bottom(
        video_height,
        style,
    )

    print()
    print("🎨 Subtitle Style Engine")

    print(
        f"   Style: "
        f"{style.name}"
    )

    print(
        f"   Video: "
        f"{video_width}x{video_height}"
    )

    print(
        f"   Font: "
        f"{style.font_name}"
    )

    print(
        f"   Font size: "
        f"{font_size}px"
    )

    print(
        f"   Margin bottom: "
        f"{margin_bottom}px"
    )

    print(
        f"   Max chars: "
        f"{style.max_chars}"
    )

    print(
        f"   Max lines: "
        f"{style.max_lines}"
    )

    print(
        f"   Border style: "
        f"{style.border_style}"
    )

    print(
        f"   Sync offset: "
        f"-{SUBTITLE_EARLY_OFFSET:.2f}s"
    )

    print()

    # --------------------------------------------------------
    # ASS HEADER
    # --------------------------------------------------------

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "Collisions: Normal\n"
        "PlayDepth: 0\n"
        f"PlayResX: {video_width}\n"
        f"PlayResY: {video_height}\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, "
        "PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding\n"
        f"Style: Default,"
        f"{style.font_name},"
        f"{font_size},"
        f"{style.primary_colour},"
        f"&H00000000,"
        f"{style.outline_colour},"
        f"{style.back_colour},"
        f"{style.bold},"
        f"0,0,0,"
        f"100,100,0,0,"
        f"{style.border_style},"
        f"{style.outline},"
        f"{style.shadow},"
        f"2,20,20,"
        f"{margin_bottom},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, "
        "MarginL, MarginR, MarginV, Effect, Text\n"
    )

    # --------------------------------------------------------
    # PARSE SRT BLOCKS
    # --------------------------------------------------------

    blocks = re.split(
        r"\r?\n\s*\r?\n",
        content.strip(),
    )

    parsed_cues = []

    # --------------------------------------------------------
    # FIRST PASS
    # --------------------------------------------------------

    for block in blocks:

        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if len(lines) < 3:
            continue

        # ----------------------------------------------------
        # TIMESTAMPS
        # ----------------------------------------------------

        times = lines[1]

        if "-->" not in times:
            continue

        start_raw, end_raw = times.split(
            "-->",
            1,
        )

        start_raw = start_raw.strip()
        end_raw = end_raw.strip()

        try:

            start_seconds = srt_time_to_seconds(
                start_raw
            )

            end_seconds = srt_time_to_seconds(
                end_raw
            )

        except ValueError:
            continue

        # ----------------------------------------------------
        # TEXT
        # ----------------------------------------------------

        text = " ".join(
            lines[2:]
        )

        # ----------------------------------------------------
        # SUBTITLE LAYOUT ENGINE
        # ----------------------------------------------------

        formatted_text = layout_subtitle_text(
            text,
            style,
        )

        if not formatted_text:
            continue

        parsed_cues.append(
            {
                "start": start_seconds,
                "end": end_seconds,
                "text": formatted_text,
            }
        )

    # --------------------------------------------------------
    # SYNC NORMALIZATION
    # --------------------------------------------------------

    normalized_cues = []

    if parsed_cues:

        print(
            "⏱️ Нормализация таймлайна "
            "субтитров..."
        )

        for index, cue in enumerate(
            parsed_cues
        ):

            original_start = cue["start"]
            original_end = cue["end"]

            # ----------------------------------------------
            # СДВИГ НАЗАД
            # ----------------------------------------------

            start = (
                original_start
                - SUBTITLE_EARLY_OFFSET
            )

            end = (
                original_end
                - SUBTITLE_EARLY_OFFSET
            )

            # ----------------------------------------------
            # FIRST CUE
            # ----------------------------------------------

            if index == 0:

                start = max(
                    0.0,
                    start,
                )

            # ----------------------------------------------
            # НЕ ДОПУСКАЕМ ПЕРЕКРЫТИЯ
            # ----------------------------------------------

            if normalized_cues:

                previous_end = (
                    normalized_cues[-1]["end"]
                )

                start = max(
                    start,
                    previous_end,
                )

            # ----------------------------------------------
            # ЗАЩИТА ОТ СХЛОПЫВАНИЯ
            # ----------------------------------------------

            minimum_duration = 0.12

            end = max(
                end,
                start + minimum_duration,
            )

            normalized_cues.append(
                {
                    "start": start,
                    "end": end,
                    "text": cue["text"],
                }
            )

    # --------------------------------------------------------
    # CREATE ASS DIALOGUES
    # --------------------------------------------------------

    dialogues = []

    for index, cue in enumerate(
        normalized_cues,
        start=1,
    ):

        start = seconds_to_ass_time(
            cue["start"]
        )

        end = seconds_to_ass_time(
            cue["end"]
        )

        dialogues.append(
            f"Dialogue: 0,"
            f"{start},"
            f"{end},"
            f"Default,,0,0,0,,"
            f"{cue['text']}"
        )

        debug_text = cue["text"].replace(
            "\\N",
            " / ",
        )

        print(
            f"   {index:02d}. "
            f"{cue['start']:.3f} → "
            f"{cue['end']:.3f}  "
            f"{debug_text}"
        )

    # --------------------------------------------------------
    # WRITE ASS
    # --------------------------------------------------------

    ass_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        ass_path,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            header
            + "\n".join(dialogues)
        )


# ============================================================
# BURN SUBTITLES
# ============================================================

def burn_subtitles_ffmpeg(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    style_name: str = "dance",
) -> bool:
    """
    Конвертирует SRT в ASS
    и вжигает субтитры через FFmpeg/libass.

    Синхронизация НЕ изменяется.
    """

    ffmpeg_exe = (
        imageio_ffmpeg.get_ffmpeg_exe()
    )

    abs_srt = srt_path.resolve()
    abs_video = video_path.resolve()
    abs_output = output_path.resolve()

    # ========================================================
    # CHECK INPUT FILES
    # ========================================================

    if not abs_srt.exists():

        print(
            f"❌ Файл субтитров не найден: "
            f"{abs_srt}"
        )

        return False

    if not abs_video.exists():

        print(
            f"❌ Исходное видео не найдено: "
            f"{abs_video}"
        )

        return False

    work_dir = abs_output.parent

    work_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_ass = (
        work_dir
        / "_temp_sub.ass"
    )

    temp_out = (
        work_dir
        / "_temp_rendered.mp4"
    )

    video_clip = None

    try:

        # ====================================================
        # GET VIDEO DIMENSIONS
        # ====================================================

        print(
            "📐 Определение размера видео..."
        )

        video_clip = VideoFileClip(
            str(abs_video)
        )

        video_width = int(
            video_clip.w
        )

        video_height = int(
            video_clip.h
        )

        video_clip.close()
        video_clip = None

        print(
            f"   Размер: "
            f"{video_width}x{video_height}"
        )

        # ====================================================
        # SRT -> ASS
        # ====================================================

        print(
            "🔄 Чистка и конвертация "
            "SRT → ASS..."
        )

        srt_to_ass(
            abs_srt,
            temp_ass,
            video_width,
            video_height,
            style_name,
        )

        if not temp_ass.exists():

            print(
                "❌ ASS-файл "
                "не был создан."
            )

            return False

        print(
            f"📜 ASS создан: "
            f"{temp_ass}"
        )

        # ====================================================
        # WINDOWS PATH
        # ====================================================

        ass_filter_path = (
            temp_ass
            .resolve()
            .as_posix()
        )

        if (
            len(ass_filter_path) >= 2
            and ass_filter_path[1] == ":"
        ):

            ass_filter_path = (
                ass_filter_path[:1]
                + r"\:"
                + ass_filter_path[2:]
            )

        ass_filter_path = (
            ass_filter_path.replace(
                "'",
                r"\'",
            )
        )

        filter_arg = (
            f"ass=filename="
            f"'{ass_filter_path}'"
        )

        print(
            f"🔧 FFmpeg subtitle filter: "
            f"{filter_arg}"
        )

        # ====================================================
        # FFMPEG COMMAND
        # ====================================================

        command = [
            ffmpeg_exe,
            "-y",

            "-i",
            str(abs_video),

            "-vf",
            filter_arg,

            "-c:v",
            VIDEO_CODEC,

            "-preset",
            VIDEO_PRESET,

            "-crf",
            VIDEO_CRF,

            "-pix_fmt",
            VIDEO_PIXEL_FORMAT,

            "-c:a",
            "copy",

            "-movflags",
            "+faststart",

            str(temp_out),
        ]

        print(
            "🎬 Вжигание субтитров "
            "с качественным encode..."
        )

        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # ====================================================
        # FFMPEG ERROR
        # ====================================================

        if result.returncode != 0:

            print(
                "❌ Ошибка FFmpeg "
                "при вжигании субтитров:"
            )

            print(
                result.stderr
            )

            return False

        # ====================================================
        # CHECK OUTPUT
        # ====================================================

        if not temp_out.exists():

            print(
                "❌ FFmpeg завершился "
                "без создания "
                "выходного файла."
            )

            return False

        # ====================================================
        # REPLACE FINAL FILE
        # ====================================================

        if abs_output.exists():

            try:

                abs_output.unlink()

            except PermissionError:

                print(
                    "❌ Невозможно заменить "
                    "выходной файл."
                )

                print(
                    "Закрой видеофайл, "
                    "если он открыт "
                    "в проигрывателе."
                )

                return False

        shutil.move(
            str(temp_out),
            str(abs_output),
        )

        print(
            f"✅ Субтитры успешно "
            f"вжжены: "
            f"{abs_output.name}"
        )

        return True

    except Exception as e:

        print(
            f"❌ Исключение "
            f"при обработке "
            f"субтитров: {e}"
        )

        return False

    finally:

        if video_clip is not None:

            try:
                video_clip.close()
            except Exception:
                pass

        if temp_ass.exists():

            try:
                temp_ass.unlink()
            except Exception:
                pass

        if temp_out.exists():

            try:
                temp_out.unlink()
            except Exception:
                pass


# ============================================================
# TEMP FILE CLEANUP
# ============================================================

def cleanup_temp_files(
    used_download_files: list[Path],
):
    """
    Удаляет временные файлы после
    УСПЕШНОГО полного рендера.

    Удаляются:

    1. все нормализованные клипы;
    2. только использованные исходники.
    """

    print()
    print("=" * 60)
    print(" CLEANUP TEMP FILES")
    print("=" * 60)

    # --------------------------------------------------------
    # NORMALIZED FILES
    # --------------------------------------------------------

    if NORMALIZED_DIR.exists():

        try:

            shutil.rmtree(
                NORMALIZED_DIR
            )

            print(
                f"🧹 Удалена папка: "
                f"{NORMALIZED_DIR}"
            )

        except Exception as e:

            print(
                f"⚠️ Не удалось удалить "
                f"{NORMALIZED_DIR}: {e}"
            )

    else:

        print(
            "ℹ️ temp_normalized уже отсутствует."
        )

    # --------------------------------------------------------
    # DOWNLOADED SOURCE FILES
    # --------------------------------------------------------

    for filepath in used_download_files:

        try:

            filepath = Path(filepath)

            if filepath.exists():

                filepath.unlink()

                print(
                    f"🧹 Удалён исходник: "
                    f"{filepath.name}"
                )

        except Exception as e:

            print(
                f"⚠️ Не удалось удалить "
                f"{filepath}: {e}"
            )

    print()

    print(
        "✓ Очистка временных файлов завершена."
    )


# ============================================================
# GET TARGET DURATION
# ============================================================

def get_target_duration(
    plan: dict,
) -> float:

    output_config = plan.get(
        "output",
        {},
    )

    target_duration = output_config.get(
        "duration_seconds",
        DEFAULT_TARGET_DURATION,
    )

    try:

        target_duration = float(
            target_duration
        )

    except (
        TypeError,
        ValueError,
    ):

        target_duration = (
            DEFAULT_TARGET_DURATION
        )

    return max(
        0.1,
        target_duration,
    )


# ============================================================
# VALIDATE MONTAGE DURATION
# ============================================================

def validate_montage_duration(
    cuts: list,
    target_duration: float,
):
    """
    Проверяет сумму длительностей cuts.

    ВАЖНО:

    Assembler не должен молча
    компенсировать ошибочный montage_plan.

    Если план короче/длиннее цели,
    выводим явное предупреждение.
    """

    planned_duration = 0.0

    for cut in cuts:

        try:

            start = float(
                cut.get(
                    "start",
                    0.0,
                )
            )

            end = float(
                cut.get(
                    "end",
                    0.0,
                )
            )

            duration = max(
                0.0,
                end - start,
            )

            planned_duration += duration

        except (
            TypeError,
            ValueError,
        ):

            continue

    difference = (
        target_duration
        - planned_duration
    )

    print()
    print(
        "📏 Montage Duration Check"
    )

    print(
        f"   Плановая длительность: "
        f"{planned_duration:.3f}s"
    )

    print(
        f"   Целевая длительность: "
        f"{target_duration:.3f}s"
    )

    print(
        f"   Разница: "
        f"{difference:+.3f}s"
    )

    if abs(difference) <= 0.05:

        print(
            "   ✓ Длительность montage_plan "
            "соответствует цели."
        )

    elif difference > 0:

        print(
            "   ⚠️ Montage plan короче цели."
        )

        print(
            "   ⚠️ Недостающую длительность "
            "Assembler не будет заполнять "
            "повтором последнего кадра."
        )

    else:

        print(
            "   ⚠️ Montage plan длиннее цели."
        )

        print(
            "   ⚠️ Видеоряд будет ограничен "
            "целевой длительностью."
        )

    print()


# ============================================================
# ASSEMBLE REEL
# ============================================================

def assemble_reel(
    plan: dict,
):

    print(
        "🎬 Начинаем сборку видеоряда..."
    )

    # ========================================================
    # TARGET DURATION
    # ========================================================

    target_duration = get_target_duration(
        plan
    )

    print(
        f"🎯 Целевая длительность: "
        f"{target_duration:.3f} сек."
    )

    # ========================================================
    # VIDEO CUTS
    # ========================================================

    video_clips = []
    used_download_files = []

    cuts = plan.get(
        "cuts",
        [],
    )

    if not cuts:

        raise ValueError(
            "❌ В montage_plan отсутствуют cuts."
        )

    # ========================================================
    # PLAN DURATION VALIDATION
    # ========================================================

    validate_montage_duration(
        cuts,
        target_duration,
    )

    # ========================================================
    # LOAD NORMALIZED CLIPS
    # ========================================================

    for index, cut in enumerate(
        cuts,
        start=1,
    ):

        normalized_filename = (
            f"cut_{index:03d}.mp4"
        )

        filepath = (
            NORMALIZED_DIR
            / normalized_filename
        )

        if not filepath.exists():

            print(
                f"⚠️ Нормализованный файл "
                f"не найден: "
                f"{filepath}"
            )

            continue

        print(
            f"🎞️ Добавление "
            f"{normalized_filename}"
        )

        print(
            f"   Source: "
            f"{cut.get('filename')}"
        )

        print(
            f"   Segment: "
            f"[{cut.get('start')}s - "
            f"{cut.get('end')}s]"
        )

        clip = VideoFileClip(
            str(filepath)
        )

        clip = clip.without_audio()

        video_clips.append(
            clip
        )

        # ----------------------------------------------------
        # CLEANUP SOURCE TRACKING
        # ----------------------------------------------------

        original_filename = cut.get(
            "filename"
        )

        if original_filename:

            original_path = (
                DOWNLOAD_DIR
                / original_filename
            )

            if (
                original_path.exists()
                and original_path
                not in used_download_files
            ):

                used_download_files.append(
                    original_path
                )

    if not video_clips:

        raise ValueError(
            "❌ Нет доступных "
            "нормализованных клипов "
            "для сборки!"
        )

    # ========================================================
    # CONCAT VIDEO
    # ========================================================

    final_video = concatenate_videoclips(
        video_clips,
        method="chain",
    )

    actual_video_duration = (
        float(final_video.duration)
    )

    print(
        f"⏱️ Итоговая длина "
        f"видеоряда: "
        f"{actual_video_duration:.3f} сек."
    )

    # ========================================================
    # IMPORTANT:
    # DO NOT FREEZE LAST FRAME
    # ========================================================

    if actual_video_duration > target_duration:

        print(
            f"✂️ Видеоряд длиннее цели "
            f"на "
            f"{actual_video_duration - target_duration:.3f}s"
        )

        final_video = final_video.subclipped(
            0,
            target_duration,
        )

        actual_video_duration = (
            float(final_video.duration)
        )

        print(
            f"   → Обрезано до "
            f"{actual_video_duration:.3f}s"
        )

    elif (
        actual_video_duration
        < target_duration - 0.05
    ):

        print(
            f"⚠️ Видеоряд короче цели "
            f"на "
            f"{target_duration - actual_video_duration:.3f}s"
        )

        print(
            "⚠️ Последний кадр НЕ будет "
            "искусственно удерживаться."
        )

        print(
            "⚠️ Исправление длительности "
            "должно происходить "
            "на уровне montage_plan."
        )

    # ========================================================
    # AUDIO
    # ========================================================

    audio_tracks = []

    audio_config = plan.get(
        "audio",
        {},
    )

    # --------------------------------------------------------
    # VOICEOVER
    # --------------------------------------------------------

    voiceover_rel = (
        audio_config.get(
            "voiceover"
        )
    )

    if voiceover_rel:

        voice_path = resolve_path(
            voiceover_rel
        )

        if voice_path.exists():

            print(
                f"🎙️ Добавление озвучки: "
                f"{voice_path.name}"
            )

            voice_clip = AudioFileClip(
                str(voice_path)
            )

            voice_vol = (
                audio_config.get(
                    "voice_volume",
                    1.0,
                )
            )

            voice_clip = (
                voice_clip.with_effects(
                    [
                        afx.MultiplyVolume(
                            voice_vol
                        )
                    ]
                )
            )

            voice_clip = (
                voice_clip.with_start(1.5)
            )

            # Голос не должен создавать
            # длительность видео сам по себе.
            if (
                voice_clip.duration
                > target_duration
            ):

                voice_clip = (
                    voice_clip.subclipped(
                        0,
                        target_duration,
                    )
                )

            audio_tracks.append(
                voice_clip
            )

    # --------------------------------------------------------
    # BACKGROUND MUSIC
    # --------------------------------------------------------

    bg_music_rel = (
        audio_config.get(
            "background_music"
        )
    )

    if bg_music_rel:

        music_path = resolve_path(
            bg_music_rel
        )

        if music_path.exists():

            print(
                f"🎵 Добавление "
                f"фоновой музыки: "
                f"{music_path.name}"
            )

            music_clip = AudioFileClip(
                str(music_path)
            )

            if (
                music_clip.duration
                > target_duration
            ):

                music_clip = (
                    music_clip.subclipped(
                        0,
                        target_duration,
                    )
                )

            music_vol = (
                audio_config.get(
                    "music_volume",
                    0.15,
                )
            )

            music_clip = (
                music_clip.with_effects(
                    [
                        afx.MultiplyVolume(
                            music_vol
                        ),
                        afx.AudioFadeOut(
                            min(
                                1.5,
                                target_duration,
                            )
                        ),
                    ]
                )
            )

            music_clip = (
                music_clip.with_start(0)
            )

            audio_tracks.append(
                music_clip
            )

    # ========================================================
    # COMPOSITE AUDIO
    # ========================================================

    composite_audio = None

    if audio_tracks:

        composite_audio = (
            CompositeAudioClip(
                audio_tracks
            )
        )

        final_video = (
            final_video.with_audio(
                composite_audio
            )
        )

    # ========================================================
    # OUTPUT
    # ========================================================

    output_path = resolve_path(
        plan.get(
            "output_path",
            "07_OUTPUT/rendered_reel.mp4",
        )
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_raw_output = (
        output_path.parent
        / f"temp_{output_path.name}"
    )

    # ========================================================
    # BRANDING OVERLAY
    # ========================================================

    # Получаем параметры бренда из montage_plan (если указаны)
    project_id = plan.get("project_id", "dance_kids")
    preset_name = plan.get("brand_preset")

    # Применяем наложение логотипа
    #final_video = apply_brand_logo(
    #    final_video,
    #    project_id=project_id,
    #    preset_name=preset_name
    #)

    # ========================================================
    # BASE RENDER
    # ========================================================

    print()
    print(
        "🚀 Запуск базового "
        "рендеринга..."
    )

    final_video.write_videofile(
        str(temp_raw_output),

        codec=VIDEO_CODEC,
        audio_codec=AUDIO_CODEC,

        fps=OUTPUT_FPS,

        preset=VIDEO_PRESET,

        ffmpeg_params=[
            "-crf",
            VIDEO_CRF,

            "-pix_fmt",
            VIDEO_PIXEL_FORMAT,

            "-b:a",
            AUDIO_BITRATE,

            "-movflags",
            "+faststart",
        ],

        threads=0,
    )

    # ========================================================
    # CLOSE MOVIEPY OBJECTS
    # ========================================================

    for c in video_clips:

        try:
            c.close()
        except Exception:
            pass

    if audio_tracks:

        for track in audio_tracks:

            try:
                track.close()
            except Exception:
                pass

    if composite_audio:

        try:
            composite_audio.close()
        except Exception:
            pass

    try:
        final_video.close()
    except Exception:
        pass

    # ========================================================
    # SUBTITLE STYLE SELECTION
    # ========================================================

    requested_style = plan.get(
        "subtitle_style",
        "auto",
    )

    content_profile = plan.get(
        "content_profile",
        {},
    )

    subtitle_style = (
        select_subtitle_style(
            profile=content_profile,
            explicit_style=requested_style,
        )
    )

    print()
    print(
        "🧠 Subtitle Style Selector"
    )

    print(
        f"   Requested: "
        f"{requested_style}"
    )

    print(
        f"   Selected: "
        f"{subtitle_style}"
    )

    if content_profile:

        print(
            "   Content profile:"
        )

        for key, value in content_profile.items():

            print(
                f"      {key}: {value}"
            )

    print()

    # ========================================================
    # SUBTITLES
    # ========================================================

    raw_subtitles = plan.get("audio", {}).get("subtitles")

    # Если субтитры выключены (False/None), не пытаемся искать путь
    if not raw_subtitles:
        srt_rel = None
    elif isinstance(raw_subtitles, str):
        srt_rel = raw_subtitles
    else:
        srt_rel = "02_PROCESSING/temp_audio/subtitles.srt"

    srt_path = resolve_path(srt_rel) if srt_rel else None

    if srt_path and srt_path.exists():

        # === СДВИГ SRT НА 1.5 СЕК (Чистый Python) ===
        offset_srt_path = srt_path.parent / "temp_offset_subtitles.srt"
        try:
            import re
            from datetime import timedelta

            def shift_srt_time(match, offset_sec=1.5):
                # Формат SRT: HH:MM:SS,mmm
                h, m, s, ms = map(int, match.groups())
                td = timedelta(hours=h, minutes=m, seconds=s, milliseconds=ms) + timedelta(seconds=offset_sec)
                
                total_sec = int(td.total_seconds())
                ms_rem = int(td.microseconds / 1000)
                hours = total_sec // 3600
                minutes = (total_sec % 3600) // 60
                seconds = total_sec % 60
                return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms_rem:03d}"

            time_pattern = r"(\d{2}):(\d{2}):(\d{2}),(\d{3})"

            with open(srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()

            shifted_content = re.sub(
                time_pattern, 
                lambda m: shift_srt_time(m, 1.5), 
                srt_content
            )

            with open(offset_srt_path, "w", encoding="utf-8") as f:
                f.write(shifted_content)

            srt_to_use = offset_srt_path
            print("[Subtitles] ✓ SRT тайминги успешно сдвинуты на +1.5 сек")
        except Exception as e:
            print(f"[Subtitles] Ошибка при сдвиге SRT: {e}")
            srt_to_use = srt_path
        # ============================================

        success = burn_subtitles_ffmpeg(
            temp_raw_output,
            srt_to_use,
            output_path,
            style_name=subtitle_style,
        )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        if (
            success
            and temp_raw_output.exists()
        ):

            os.remove(
                temp_raw_output
            )

        # ----------------------------------------------------
        # FALLBACK
        # ----------------------------------------------------

        elif (
            not success
            and temp_raw_output.exists()
        ):

            print(
                "⚠️ Субтитры не "
                "наложены. "
                "Используется видео "
                "без субтитров."
            )

            shutil.move(
                str(temp_raw_output),
                str(output_path),
            )

    else:

        print(
            "ℹ️ Субтитры отсутствуют или отключены. "
            "Используется видео без субтитров."
        )

        if temp_raw_output.exists():

            shutil.move(
                str(temp_raw_output),
                str(output_path),
            )

    # ========================================================
    # VERIFY FINAL OUTPUT
    # ========================================================

    if not output_path.exists():

        raise RuntimeError(
            "❌ Финальный файл "
            "не создан. "
            "Очистка временных файлов "
            "НЕ выполняется."
        )

    if output_path.stat().st_size <= 0:

        raise RuntimeError(
            "❌ Финальный файл "
            "имеет нулевой размер. "
            "Очистка временных файлов "
            "НЕ выполняется."
        )

    # ========================================================
    # FINAL DURATION CHECK
    # ========================================================

    print()
    print(
        "🔎 Проверка финального видео..."
    )

    final_check_clip = None

    try:

        final_check_clip = VideoFileClip(
            str(output_path)
        )

        final_duration = float(
            final_check_clip.duration
        )

        print(
            f"   Финальная длительность: "
            f"{final_duration:.3f}s"
        )

        duration_difference = (
            final_duration
            - target_duration
        )

        print(
            f"   Отклонение от цели: "
            f"{duration_difference:+.3f}s"
        )

        if abs(duration_difference) <= 0.05:

            print(
                "   ✓ Длительность соответствует цели."
            )

        else:

            print(
                "   ⚠️ Финальная длительность "
                "отличается от target duration."
            )

    finally:

        if final_check_clip is not None:

            try:
                final_check_clip.close()
            except Exception:
                pass

    # ========================================================
    # CLEANUP
    # ========================================================

    cleanup_temp_files(
        used_download_files
    )

    # ========================================================
    # COMPLETE
    # ========================================================

    print()

    print(
        f"🎉 Сборка полностью "
        f"завершена! "
        f"Итоговый файл: "
        f"{output_path}"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    plan_file = (
        BASE_DIR
        / "06_COMPOSER"
        / "montage_plan.json"
    )

    if plan_file.exists():

        with open(
            plan_file,
            "r",
            encoding="utf-8",
        ) as f:

            plan_data = json.load(f)

        assemble_reel(
            plan_data
        )

    else:

        print(
            f"❌ Montage plan не найден: "
            f"{plan_file}"
        )