from dataclasses import dataclass


@dataclass(frozen=True)
class FormatProfile:
    name: str
    width: int
    height: int
    fps: int


FORMAT_PROFILES = {
    "reels": FormatProfile(
        name="reels",
        width=1080,
        height=1920,
        fps=30,
    ),

    "story": FormatProfile(
        name="story",
        width=1080,
        height=1920,
        fps=30,
    ),

    "post": FormatProfile(
        name="post",
        width=1080,
        height=1350,
        fps=30,
    ),

    "landscape": FormatProfile(
        name="landscape",
        width=1920,
        height=1080,
        fps=30,
    ),
}


def get_format_profile(format_name: str) -> FormatProfile:
    """
    Возвращает профиль целевого формата.

    Пример:
        get_format_profile("reels")
    """

    normalized = (format_name or "").strip().lower()

    if normalized not in FORMAT_PROFILES:
        available = ", ".join(FORMAT_PROFILES.keys())
        raise ValueError(
            f"Неизвестный формат '{format_name}'. "
            f"Доступные форматы: {available}"
        )

    return FORMAT_PROFILES[normalized]