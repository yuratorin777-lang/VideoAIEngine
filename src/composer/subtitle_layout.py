from __future__ import annotations

import re

from src.composer.subtitle_styles import SubtitleStyle


# Слова, которые нежелательно оставлять в начале строки.
BAD_LINE_START = {
    "и",
    "а",
    "но",
    "или",
    "что",
    "как",
    "когда",
    "если",
    "чтобы",
    "потому",
    "для",
    "из",
    "с",
    "со",
    "к",
    "ко",
    "у",
    "о",
    "об",
    "от",
    "до",
    "на",
    "в",
    "во",
    "за",
    "по",
    "при",
    "без",
    "над",
    "под",
    "между",
}

# Слова, которые нежелательно оставлять в конце строки.
BAD_LINE_END = {
    "и",
    "а",
    "но",
    "или",
    "что",
    "как",
    "для",
    "из",
    "с",
    "со",
    "к",
    "ко",
    "у",
    "о",
    "об",
    "от",
    "до",
    "на",
    "в",
    "во",
    "за",
    "по",
    "при",
    "без",
    "над",
    "под",
    "между",
}


def normalize_text(text: str) -> str:
    """
    Нормализация текста субтитра.
    """

    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    # Убираем множественные пробелы.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _words(text: str) -> list[str]:
    return text.split()


def _line_score(line: str) -> float:
    """
    Оценивает качество отдельной строки.

    Чем выше score, тем лучше.
    """

    words = _words(line)

    if not words:
        return -1000

    first = words[0].lower().strip(".,!?;:-")
    last = words[-1].lower().strip(".,!?;:-")

    score = 0.0

    if first in BAD_LINE_START:
        score -= 25

    if last in BAD_LINE_END:
        score -= 20

    # Небольшой бонус за нормальную длину.
    if 12 <= len(line) <= 30:
        score += 5

    return score


def _find_best_break(
    words: list[str],
    max_chars: int,
) -> int | None:
    """
    Ищет лучшее место разрыва для двух строк.

    Возвращает количество слов в первой строке.
    """

    if len(words) <= 1:
        return None

    total_length = len(" ".join(words))

    target = total_length / 2

    best_index = None
    best_score = float("-inf")

    for index in range(1, len(words)):
        line1 = " ".join(words[:index])
        line2 = " ".join(words[index:])

        if len(line1) > max_chars:
            continue

        if len(line2) > max_chars:
            continue

        distance = abs(len(line1) - target)

        score = -distance

        score += _line_score(line1)
        score += _line_score(line2)

        # Слишком короткая первая/вторая строка — плохо.
        if len(line1) < 8:
            score -= 10

        if len(line2) < 8:
            score -= 10

        if score > best_score:
            best_score = score
            best_index = index

    return best_index


def layout_subtitle_text(
    text: str,
    style: SubtitleStyle,
) -> str:
    """
    Преобразует исходный текст субтитра
    в визуально аккуратную композицию.

    Результат использует \\N для ASS-переноса строки.
    """

    text = normalize_text(text)

    if not text:
        return ""

    words = _words(text)

    if not words:
        return ""

    max_chars = style.max_chars
    max_lines = style.max_lines

    # ---------------------------------------------------------
    # 1. Уже помещается в одну строку
    # ---------------------------------------------------------

    if len(text) <= max_chars:
        return text

    # ---------------------------------------------------------
    # 2. Две строки
    # ---------------------------------------------------------

    if max_lines >= 2:

        break_index = _find_best_break(
            words,
            max_chars,
        )

        if break_index is not None:

            line1 = " ".join(words[:break_index])
            line2 = " ".join(words[break_index:])

            return f"{line1}\\N{line2}"

    # ---------------------------------------------------------
    # 3. Fallback — принудительный перенос
    # ---------------------------------------------------------

    lines: list[str] = []
    current: list[str] = []

    for word in words:

        candidate = " ".join(current + [word])

        if current and len(candidate) > max_chars:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        lines.append(" ".join(current))

    # Ограничиваем количество строк.
    if len(lines) > max_lines:

        lines = lines[:max_lines]

        remaining_words = []

        for line in lines[-1].split():
            remaining_words.append(line)

        # В последней строке сохраняем остаток.
        # Это fallback, который используется только
        # если нормальная композиция невозможна.
        used_words = sum(len(line.split()) for line in lines[:-1])

        remaining = words[used_words:]

        lines[-1] = " ".join(remaining)

    return "\\N".join(lines[:max_lines])