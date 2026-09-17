from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitleStyle:
    """
    Визуальный пресет субтитров.

    Пресет описывает не содержание текста,
    а способ его визуальной подачи.
    """

    name: str

    # ---------------------------------------------------------
    # Размер
    # ---------------------------------------------------------

    font_size_ratio: float
    min_font_size: int
    max_font_size: int

    # ---------------------------------------------------------
    # Положение
    # ---------------------------------------------------------

    margin_bottom_ratio: float
    min_margin_bottom: int
    max_margin_bottom: int

    # ---------------------------------------------------------
    # ASS colors
    # ---------------------------------------------------------

    primary_colour: str
    outline_colour: str
    back_colour: str

    # ---------------------------------------------------------
    # Визуальные параметры
    # ---------------------------------------------------------

    outline: int
    shadow: int
    bold: int

    # 1 = обычный outline
    # 3 = opaque box
    border_style: int

    # ---------------------------------------------------------
    # Шрифт
    # ---------------------------------------------------------

    font_name: str

    # ---------------------------------------------------------
    # Layout
    # ---------------------------------------------------------

    max_chars: int
    max_lines: int


SUBTITLE_STYLES = {

    # =========================================================
    # KIDS
    # =========================================================

    "kids": SubtitleStyle(
        name="kids",

        font_size_ratio=0.042,
        min_font_size=62,
        max_font_size=86,

        margin_bottom_ratio=0.125,
        min_margin_bottom=170,
        max_margin_bottom=280,

        primary_colour="&H00FFFFFF",

        # Яркий фиолетовый outline.
        outline_colour="&H00FF66CC",

        # Полупрозрачный тёмный фон.
        back_colour="&H90000000",

        outline=5,
        shadow=2,
        bold=1,

        # Обычный outline, чтобы не превращать
        # каждый subtitle в огромную плашку.
        border_style=1,

        font_name="Arial",

        max_chars=34,
        max_lines=2,
    ),

    # =========================================================
    # DANCE
    # =========================================================

    "dance": SubtitleStyle(
        name="dance",

        font_size_ratio=0.040,
        min_font_size=60,
        max_font_size=82,

        margin_bottom_ratio=0.115,
        min_margin_bottom=155,
        max_margin_bottom=250,

        primary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H80000000",

        outline=4,
        shadow=2,
        bold=1,
        border_style=1,

        font_name="Arial",

        max_chars=36,
        max_lines=2,
    ),

    # =========================================================
    # EXPERT
    # =========================================================

    "expert": SubtitleStyle(
        name="expert",

        font_size_ratio=0.034,
        min_font_size=52,
        max_font_size=70,

        margin_bottom_ratio=0.100,
        min_margin_bottom=135,
        max_margin_bottom=220,

        primary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H70000000",

        outline=3,
        shadow=1,
        bold=1,
        border_style=1,

        font_name="Arial",

        max_chars=42,
        max_lines=2,
    ),

    # =========================================================
    # BUSINESS
    # =========================================================

    "business": SubtitleStyle(
        name="business",

        font_size_ratio=0.032,
        min_font_size=48,
        max_font_size=66,

        margin_bottom_ratio=0.095,
        min_margin_bottom=125,
        max_margin_bottom=205,

        primary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H60000000",

        outline=2,
        shadow=1,
        bold=0,
        border_style=1,

        font_name="Arial",

        max_chars=44,
        max_lines=2,
    ),

    # =========================================================
    # PROMO
    # =========================================================

    "promo": SubtitleStyle(
        name="promo",

        font_size_ratio=0.044,
        min_font_size=64,
        max_font_size=90,

        margin_bottom_ratio=0.130,
        min_margin_bottom=175,
        max_margin_bottom=290,

        primary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H90000000",

        outline=5,
        shadow=2,
        bold=1,
        border_style=3,

        font_name="Arial",

        max_chars=32,
        max_lines=2,
    ),
}


DEFAULT_STYLE = "dance"


def get_subtitle_style(
    style_name: str | None,
) -> SubtitleStyle:

    if not style_name:
        style_name = DEFAULT_STYLE

    style_name = style_name.lower().strip()

    if style_name == "auto":
        style_name = DEFAULT_STYLE

    if style_name not in SUBTITLE_STYLES:

        print(
            f"⚠️ Неизвестный стиль субтитров: "
            f"'{style_name}'. "
            f"Используется '{DEFAULT_STYLE}'."
        )

        return SUBTITLE_STYLES[DEFAULT_STYLE]

    return SUBTITLE_STYLES[style_name]


def calculate_font_size(
    video_height: int,
    style: SubtitleStyle,
) -> int:

    size = round(
        video_height * style.font_size_ratio
    )

    size = max(
        style.min_font_size,
        size,
    )

    size = min(
        style.max_font_size,
        size,
    )

    return size


def calculate_margin_bottom(
    video_height: int,
    style: SubtitleStyle,
) -> int:

    margin = round(
        video_height * style.margin_bottom_ratio
    )

    margin = max(
        style.min_margin_bottom,
        margin,
    )

    margin = min(
        style.max_margin_bottom,
        margin,
    )

    return margin