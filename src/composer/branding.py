import json
from pathlib import Path
from moviepy import ImageClip, CompositeVideoClip, VideoFileClip

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BRANDS_DIR = BASE_DIR / "04_LIBRARY" / "brands"


def apply_brand_logo(
    video_clip: VideoFileClip,
    project_id: str = "dance_kids",
    preset_name: str | None = None,
) -> CompositeVideoClip:
    """
    Накладывает логотип из бренда с использованием выбранного пресета.
    """
    brand_path = BRANDS_DIR / project_id
    config_file = brand_path / "brand_config.json"

    if not config_file.exists():
        print(f"[Branding] Профиль бренда '{project_id}' не найден ({config_file}). Пропуск.")
        return video_clip

    with open(config_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    presets = config.get("presets", {})

    target_preset = preset_name or config.get("default_preset")
    logo_cfg = presets.get(target_preset)

    if not logo_cfg:
        print(f"[Branding] Пресет '{target_preset}' не найден в бренде '{project_id}'. Пропуск.")
        return video_clip

    logo_file_path = brand_path / logo_cfg.get("file", "logo2.png")

    if not logo_file_path.exists():
        print(f"[Branding] Файл логотипа {logo_file_path} не найден. Пропуск.")
        return video_clip

    mode = logo_cfg.get("mode", "end")
    display_dur = float(logo_cfg.get("display_duration", 3.0))
    fade_dur = float(logo_cfg.get("fade_duration", 0.5))
    logo_width = int(logo_cfg.get("logo_width", 250))
    raw_pos = logo_cfg.get("position", "center")

    position = tuple(raw_pos) if isinstance(raw_pos, list) else raw_pos

    if mode == "start":
        start_time = 0.0
        duration = min(display_dur, video_clip.duration)
    elif mode == "end":
        duration = min(display_dur, video_clip.duration)
        start_time = max(0.0, video_clip.duration - duration)
    elif mode == "full":
        start_time = 0.0
        duration = video_clip.duration
    else:
        start_time = 0.0
        duration = video_clip.duration

    # Создание клипа логотипа с поддержкой MoviePy v2
    logo_clip = ImageClip(str(logo_file_path))

    # Масштабирование
    if hasattr(logo_clip, "resized"):
        logo_clip = logo_clip.resized(width=logo_width)
    else:
        logo_clip = logo_clip.resize(width=logo_width)

    # Тайминги
    if hasattr(logo_clip, "with_start"):
        logo_clip = logo_clip.with_start(start_time).with_duration(duration)
    else:
        logo_clip = logo_clip.set_start(start_time).set_duration(duration)

    # Затухания (Fade In / Fade Out)
    if hasattr(logo_clip, "crossfadein"):
        logo_clip = logo_clip.crossfadein(fade_dur).crossfadeout(fade_dur)

    # Позиция
    if hasattr(logo_clip, "with_position"):
        logo_clip = logo_clip.with_position(position)
    else:
        logo_clip = logo_clip.set_position(position)

    print(f"[Branding] ✓ Наложен логотип '{logo_cfg['file']}' (Пресет: {target_preset}, Режим: {mode})")
    return CompositeVideoClip([video_clip, logo_clip])