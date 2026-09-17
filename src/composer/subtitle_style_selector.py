from __future__ import annotations

from typing import Any

from src.composer.subtitle_styles import (
    DEFAULT_STYLE,
    SUBTITLE_STYLES,
)


def _normalize(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, list):
        return " ".join(
            str(item).lower()
            for item in value
        )

    return str(value).lower().strip()


def select_subtitle_style(
    profile: dict | None = None,
    explicit_style: str | None = None,
) -> str:
    """
    Выбирает subtitle preset.

    Приоритет:

    1. Явно заданный стиль.
    2. Content Profile.
    3. DEFAULT_STYLE.
    """

    # =========================================================
    # 1. Явный preset
    # =========================================================

    if explicit_style:

        explicit_style = explicit_style.lower().strip()

        if explicit_style != "auto":

            if explicit_style in SUBTITLE_STYLES:
                return explicit_style

            print(
                f"⚠️ Неизвестный subtitle_style "
                f"'{explicit_style}'. Переходим к AUTO."
            )

    # =========================================================
    # 2. Анализ Content Profile
    # =========================================================

    profile = profile or {}

    audience = _normalize(
        profile.get("audience")
    )

    topic = _normalize(
        profile.get("topic")
    )

    tone = _normalize(
        profile.get("tone")
    )

    intent = _normalize(
        profile.get("intent")
    )

    content_type = _normalize(
        profile.get("content_type")
    )

    tags = _normalize(
        profile.get("tags")
    )

    context = " ".join(
        [
            audience,
            topic,
            tone,
            intent,
            content_type,
            tags,
        ]
    )

    # =========================================================
    # 3. Kids
    # =========================================================

    kids_keywords = [
        "kids",
        "child",
        "children",
        "дет",
        "ребен",
        "дошколь",
        "малыш",
        "школьник",
        "детский",
    ]

    if any(
        keyword in context
        for keyword in kids_keywords
    ):
        return "kids"

    # =========================================================
    # 4. Promo
    # =========================================================

    promo_keywords = [
        "promo",
        "promotion",
        "sale",
        "offer",
        "cta",
        "реклам",
        "продаж",
        "акци",
        "скидк",
        "запиш",
        "купить",
        "предложение",
    ]

    if any(
        keyword in context
        for keyword in promo_keywords
    ):
        return "promo"

    # =========================================================
    # 5. Expert
    # =========================================================

    expert_keywords = [
        "expert",
        "education",
        "educational",
        "tutorial",
        "how-to",
        "analysis",
        "эксперт",
        "обуч",
        "урок",
        "совет",
        "разбор",
        "объяс",
    ]

    if any(
        keyword in context
        for keyword in expert_keywords
    ):
        return "expert"

    # =========================================================
    # 6. Business
    # =========================================================

    business_keywords = [
        "business",
        "b2b",
        "corporate",
        "company",
        "businesslike",
        "бизнес",
        "корпорат",
        "компан",
        "предприним",
    ]

    if any(
        keyword in context
        for keyword in business_keywords
    ):
        return "business"

    # =========================================================
    # 7. Dance
    # =========================================================

    dance_keywords = [
        "dance",
        "dancing",
        "choreography",
        "танц",
        "хореограф",
        "студия",
        "трениров",
        "балет",
    ]

    if any(
        keyword in context
        for keyword in dance_keywords
    ):
        return "dance"

    # =========================================================
    # 8. Fallback
    # =========================================================

    return DEFAULT_STYLE