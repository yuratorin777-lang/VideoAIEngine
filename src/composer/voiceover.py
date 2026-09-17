import asyncio
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import edge_tts


BASE_DIR = Path(__file__).resolve().parent.parent.parent

DEFAULT_VOICE = "ru-RU-DmitryNeural"

# ============================================================
# ПРОИЗНОШЕНИЕ БРЕНДОВЫХ НАЗВАНИЙ
# ============================================================

import re

TTS_PRONUNCIATION_MAP = {
    "Dance Kids": "Дэнс Кидс",
    "dance kids": "дэнс кидс",
    "Baby Dance": "Бэби Дэнс",
    "Baby dance": "Бэби Дэнс",
    "baby dance": "бэби дэнс",
    "Dance": "Дэнс",
    "dance": "дэнс",
}

def normalize_tts_pronunciation(text: str) -> str:
    """
    Безопасно меняет английские термины на фонетическую кириллицу для TTS.
    """
    sorted_keys = sorted(TTS_PRONUNCIATION_MAP.keys(), key=len, reverse=True)
    
    for key in sorted_keys:
        value = TTS_PRONUNCIATION_MAP[key]
        pattern = r'\b' + re.escape(key) + r'\b'
        text = re.sub(pattern, value, text)
        
    return text

# ============================================================
# НАСТРОЙКИ СУБТИТРОВ
# ============================================================

MAX_CHARS = 32
MAX_DURATION = 1.80
PAUSE_BREAK = 0.28


# ============================================================
# VOICE DIRECTION / PROSODY
# ============================================================

@dataclass(frozen=True)
class ProsodyProfile:
    rate: str
    pitch: str
    volume: str
    pause_after: float


@dataclass(frozen=True)
class VoiceDirection:
    style: str
    role: str
    prosody: ProsodyProfile


# Базовые профили.
#
# Значения специально умеренные.
# Мы не делаем голос карикатурно "эмоциональным".
# Цель — убрать монотонность и дать речи живую динамику.

PROSODY_PROFILES = {
    "energetic": {
        "hook": ProsodyProfile(
            rate="+7%",
            pitch="+2Hz",
            volume="+0%",
            pause_after=0.16,
        ),
        "body": ProsodyProfile(
            rate="+2%",
            pitch="+0Hz",
            volume="+0%",
            pause_after=0.11,
        ),
        "cta": ProsodyProfile(
            rate="+5%",
            pitch="+2Hz",
            volume="+0%",
            pause_after=0.18,
        ),
    },

    "friendly": {
        "hook": ProsodyProfile(
            rate="+3%",
            pitch="+1Hz",
            volume="+0%",
            pause_after=0.15,
        ),
        "body": ProsodyProfile(
            rate="+0%",
            pitch="+0Hz",
            volume="+0%",
            pause_after=0.12,
        ),
        "cta": ProsodyProfile(
            rate="+3%",
            pitch="+1Hz",
            volume="+0%",
            pause_after=0.16,
        ),
    },

    "warm": {
        "hook": ProsodyProfile(
            rate="+0%",
            pitch="+1Hz",
            volume="+0%",
            pause_after=0.16,
        ),
        "body": ProsodyProfile(
            rate="-2%",
            pitch="+0Hz",
            volume="+0%",
            pause_after=0.14,
        ),
        "cta": ProsodyProfile(
            rate="+1%",
            pitch="+1Hz",
            volume="+0%",
            pause_after=0.18,
        ),
    },

    "informational": {
        "hook": ProsodyProfile(
            rate="+1%",
            pitch="+0Hz",
            volume="+0%",
            pause_after=0.14,
        ),
        "body": ProsodyProfile(
            rate="-2%",
            pitch="-1Hz",
            volume="+0%",
            pause_after=0.12,
        ),
        "cta": ProsodyProfile(
            rate="+1%",
            pitch="+1Hz",
            volume="+0%",
            pause_after=0.16,
        ),
    },

    "calm": {
        "hook": ProsodyProfile(
            rate="-2%",
            pitch="+0Hz",
            volume="+0%",
            pause_after=0.18,
        ),
        "body": ProsodyProfile(
            rate="-4%",
            pitch="-1Hz",
            volume="+0%",
            pause_after=0.16,
        ),
        "cta": ProsodyProfile(
            rate="-1%",
            pitch="+0Hz",
            volume="+0%",
            pause_after=0.20,
        ),
    },

    "promo": {
        "hook": ProsodyProfile(
            rate="+8%",
            pitch="+2Hz",
            volume="+0%",
            pause_after=0.14,
        ),
        "body": ProsodyProfile(
            rate="+3%",
            pitch="+0Hz",
            volume="+0%",
            pause_after=0.10,
        ),
        "cta": ProsodyProfile(
            rate="+6%",
            pitch="+2Hz",
            volume="+0%",
            pause_after=0.17,
        ),
    },
}


DEFAULT_PROSODY_STYLE = "friendly"


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def ticks_to_seconds(ticks: int) -> float:
    return ticks / 10_000_000


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))

    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000

    minutes = milliseconds // 60_000
    milliseconds %= 60_000

    seconds_part = milliseconds // 1000
    milliseconds %= 1000

    return (
        f"{hours:02d}:"
        f"{minutes:02d}:"
        f"{seconds_part:02d},"
        f"{milliseconds:03d}"
    )


def normalize_word(word: str) -> str:
    return re.sub(r"\s+", " ", word).strip()


def normalize_style(style: str | None) -> str:
    if not style:
        return DEFAULT_PROSODY_STYLE

    style = style.strip().lower()

    aliases = {
        "энергичный": "energetic",
        "энергичная": "energetic",
        "энергичное": "energetic",

        "дружелюбный": "friendly",
        "дружелюбная": "friendly",

        "теплый": "warm",
        "тёплый": "warm",
        "теплая": "warm",
        "тёплая": "warm",

        "информационный": "informational",
        "информативный": "informational",

        "спокойный": "calm",
        "спокойная": "calm",

        "промо": "promo",
        "рекламный": "promo",
    }

    style = aliases.get(style, style)

    if style not in PROSODY_PROFILES:
        print(
            f"⚠️ Неизвестный voice_style '{style}'. "
            f"Используется '{DEFAULT_PROSODY_STYLE}'."
        )
        return DEFAULT_PROSODY_STYLE

    return style


# ============================================================
# РАЗБИВКА ТЕКСТА НА СМЫСЛОВЫЕ ФРАЗЫ
# ============================================================

def split_into_phrases(text: str) -> list[str]:
    """
    Разбивает сценарий на смысловые фразы.

    В первую очередь используем:
    - точку
    - !
    - ?
    - …
    - ;
    - двоеточие

    Если Gemini вернул длинный текст без нормальной пунктуации,
    дополнительно режем по длине.
    """

    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    raw_parts = re.split(
        r"(?<=[.!?;:…])\s+",
        text,
    )

    phrases = []

    for part in raw_parts:
        part = part.strip()

        if not part:
            continue

        # Если фраза очень длинная,
        # режем её по запятым.
        if len(part) > 95:
            comma_parts = re.split(
                r"(?<=,)\s+",
                part,
            )

            for comma_part in comma_parts:
                comma_part = comma_part.strip()

                if comma_part:
                    phrases.append(comma_part)
        else:
            phrases.append(part)

    return phrases


# ============================================================
# ОПРЕДЕЛЕНИЕ РОЛИ ФРАЗЫ
# ============================================================

CTA_PATTERNS = (
    "записывай",
    "запишитесь",
    "приходите",
    "попробуйте",
    "узнайте",
    "оставьте заявку",
    "начните",
    "подарите",
    "присоединяйтесь",
    "ждём",
    "ждем",
    "приглашаем",
    "выбирайте",
    "попробуйте",
)

HOOK_PATTERNS = (
    "хотите",
    "знаете ли",
    "а вы",
    "мечтаете",
    "вашему ребенку",
    "вашему ребёнку",
    "почему",
    "как помочь",
    "что если",
)


def detect_phrase_role(
    phrase: str,
    index: int,
    total: int,
) -> str:

    normalized = phrase.lower().strip()

    # Первый фрагмент почти всегда является hook,
    # если это не очень короткий текст.
    if index == 0 and total >= 2:
        return "hook"

    # Финальный фрагмент проверяем на CTA.
    if index == total - 1:
        for pattern in CTA_PATTERNS:
            if pattern in normalized:
                return "cta"

        # Если финальная фраза заканчивается
        # призывной пунктуацией — тоже CTA.
        if normalized.endswith(("!", "?!")):
            return "cta"

    # Любая фраза с явным CTA.
    for pattern in CTA_PATTERNS:
        if pattern in normalized:
            return "cta"

    # Явный hook.
    for pattern in HOOK_PATTERNS:
        if pattern in normalized:
            return "hook"

    return "body"


def build_voice_direction(
    text: str,
    voice_style: str | None,
) -> list[VoiceDirection]:

    style = normalize_style(voice_style)
    phrases = split_into_phrases(text)

    profiles = PROSODY_PROFILES[style]

    directions = []

    for index, phrase in enumerate(phrases):

        role = detect_phrase_role(
            phrase=phrase,
            index=index,
            total=len(phrases),
        )

        directions.append(
            VoiceDirection(
                style=style,
                role=role,
                prosody=profiles[role],
            )
        )

    return directions


# ============================================================
# FFMPEG
# ============================================================

def find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")

    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg не найден в PATH. "
            "Он необходим для сборки voiceover-фрагментов."
        )

    return ffmpeg


def find_ffprobe() -> str:
    ffprobe = shutil.which("ffprobe")

    if not ffprobe:
        raise RuntimeError(
            "FFprobe не найден в PATH. "
            "Он необходим для точного расчёта timeline voiceover."
        )

    return ffprobe


def get_audio_duration(path: Path) -> float:
    ffprobe = find_ffprobe()

    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    value = result.stdout.strip()

    if not value:
        raise RuntimeError(
            f"Не удалось определить длительность аудио: {path}"
        )

    return float(value)


def concat_audio_files(
    input_files: list[Path],
    output_path: Path,
) -> None:

    if not input_files:
        raise RuntimeError(
            "Нет аудиофайлов для объединения."
        )

    ffmpeg = find_ffmpeg()

    concat_file = output_path.parent / "voice_concat.txt"

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as file:

        for path in input_files:
            # FFmpeg concat demuxer требует экранирования
            # одинарных кавычек.
            escaped = str(path).replace("'", "'\\''")

            file.write(
                f"file '{escaped}'\n"
            )

    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(output_path),
            ],
            check=True,
        )

    finally:
        if concat_file.exists():
            concat_file.unlink()


# ============================================================
# ГЕНЕРАЦИЯ ОДНОЙ ФРАЗЫ
# ============================================================

async def generate_phrase_audio(
    phrase: str,
    voice: str,
    prosody: ProsodyProfile,
    output_path: Path,
) -> list[dict]:

    word_boundaries = []

    async def _fetch_chunks(comm: edge_tts.Communicate) -> list[dict]:
        boundaries = []
        with open(output_path, "wb") as file:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    boundaries.append(
                        {
                            "text": chunk["text"],
                            "offset": chunk["offset"],
                            "duration": chunk["duration"],
                        }
                    )
        return boundaries

    # 1-я попытка: с тонкими настройками prosody (pitch/rate/volume)
    communicate = edge_tts.Communicate(
        phrase,
        voice,
        rate=prosody.rate,
        volume=prosody.volume,
        pitch=prosody.pitch,
        boundary="WordBoundary",
    )

    try:
        word_boundaries = await _fetch_chunks(communicate)
    except Exception as e:
        print(f"[!] Ошибка edge-tts ({e}) при генерации фразы. Перезапускаем без pitch/rate...")
        
        # 2-я попытка (Fallback): чистый запрос без падающих параметров prosody
        fallback_communicate = edge_tts.Communicate(
            phrase,
            voice,
            boundary="WordBoundary",
        )
        word_boundaries = await _fetch_chunks(fallback_communicate)

    return word_boundaries


# ============================================================
# ФОРМИРОВАНИЕ ОБЩЕГО WORD TIMELINE
# ============================================================

def merge_phrase_word_boundaries(
    phrase_results: list[dict],
) -> list[dict]:

    merged = []

    timeline_offset = 0.0

    for result in phrase_results:

        boundaries = result["word_boundaries"]

        phrase_start = timeline_offset

        for item in boundaries:

            text = normalize_word(
                item["text"]
            )

            if not text:
                continue

            local_start = ticks_to_seconds(
                item["offset"]
            )

            local_duration = ticks_to_seconds(
                item["duration"]
            )

            merged.append(
                {
                    "text": text,
                    "offset": round(
                        (phrase_start + local_start)
                        * 10_000_000
                    ),
                    "duration": round(
                        local_duration
                        * 10_000_000
                    ),
                }
            )

        timeline_offset += result["duration"]

        timeline_offset += result["pause_after"]

    return merged


# ============================================================
# ФОРМИРОВАНИЕ СУБТИТРОВ
# ============================================================

def build_grouped_srt(
    word_boundaries: list[dict],
) -> str:

    if not word_boundaries:
        return ""

    words = []

    for item in word_boundaries:

        text = normalize_word(
            item["text"]
        )

        if not text:
            continue

        start = ticks_to_seconds(
            item["offset"]
        )

        duration = ticks_to_seconds(
            item["duration"]
        )

        end = start + duration

        words.append(
            {
                "text": text,
                "start": start,
                "end": end,
            }
        )

    if not words:
        return ""

    # ========================================================
    # ДИАГНОСТИКА WORD TIMELINE
    # ========================================================

    print()
    print("🕐 WordBoundary Timeline")

    print(
        f"   First word: "
        f"{words[0]['start']:.3f}s"
    )

    print(
        f"   Last word: "
        f"{words[-1]['end']:.3f}s"
    )

    print(
        f"   Total speech timeline: "
        f"{words[-1]['end'] - words[0]['start']:.3f}s"
    )

    print()
    print("   Последние WordBoundary:")

    for word in words[-5:]:

        print(
            f"      "
            f"{word['start']:.3f} → "
            f"{word['end']:.3f}  "
            f"{word['text']}"
        )

    # ========================================================
    # ГРУППИРОВКА СЛОВ
    # ========================================================

    groups = []
    current = []

    for word in words:

        if not current:
            current.append(word)
            continue

        current_text = " ".join(
            item["text"]
            for item in current
        )

        candidate_text = (
            current_text
            + " "
            + word["text"]
        )

        current_start = current[0]["start"]

        word_start = word["start"]

        candidate_duration = (
            word_start
            - current_start
        )

        pause = (
            word["start"]
            - current[-1]["end"]
        )

        should_break = False

        # ----------------------------------------------------
        # 1. Слишком длинный текст
        # ----------------------------------------------------

        if len(candidate_text) > MAX_CHARS:
            should_break = True

        # ----------------------------------------------------
        # 2. Слишком длинный subtitle cue
        # ----------------------------------------------------

        if candidate_duration > MAX_DURATION:
            should_break = True

        # ----------------------------------------------------
        # 3. Пауза в речи
        # ----------------------------------------------------

        if pause > PAUSE_BREAK:
            should_break = True

        if should_break:

            groups.append(current)

            current = [word]

        else:

            current.append(word)

    if current:
        groups.append(current)

    # ========================================================
    # СОЗДАЁМ SRT
    # ========================================================

    srt_blocks = []

    for index, group in enumerate(groups):

        start = group[0]["start"]

        if index + 1 < len(groups):

            end = groups[index + 1][0]["start"]

        else:

            end = group[-1]["end"]

        if end <= start:
            end = group[-1]["end"]

        text = " ".join(
            item["text"]
            for item in group
        )

        srt_blocks.append(
            f"{index + 1}\n"
            f"{format_srt_time(start)} --> "
            f"{format_srt_time(end)}\n"
            f"{text}"
        )

    srt_text = (
        "\n\n".join(srt_blocks)
        + "\n"
    )

    # ========================================================
    # ДИАГНОСТИКА SRT TIMELINE
    # ========================================================

    print()
    print("📜 SRT Timeline")

    for index, group in enumerate(groups):

        start = group[0]["start"]

        if index + 1 < len(groups):

            end = groups[index + 1][0]["start"]

        else:

            end = group[-1]["end"]

        text = " ".join(
            item["text"]
            for item in group
        )

        print(
            f"   {index + 1:02d}. "
            f"{start:.3f} → "
            f"{end:.3f}  "
            f"{text}"
        )

    return srt_text


# ============================================================
# ГЕНЕРАЦИЯ VOICEOVER
# ============================================================

async def generate_voiceover_async(
    text: str,
    output_mp3_path: Path,
    output_srt_path: Path,
    voice: str = DEFAULT_VOICE,
    voice_style: str = DEFAULT_PROSODY_STYLE,
):

    output_mp3_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_srt_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Генерация озвучки голосом '{voice}'..."
    )

    style = normalize_style(
        voice_style
    )

    print(
        f"🎙 Voice style: {style}"
    )

    # ========================================================
    # VOICE DIRECTION
    # ========================================================

    directions = build_voice_direction(
        text=text,
        voice_style=style,
    )

    phrases = split_into_phrases(text)

    if not phrases:
        raise RuntimeError(
            "Не удалось выделить фразы из текста."
        )

    print()
    print("🎭 Voice Direction")

    for index, (phrase, direction) in enumerate(
        zip(phrases, directions),
        start=1,
    ):

        print(
            f"   {index:02d}. "
            f"[{direction.role}] "
            f"rate={direction.prosody.rate}, "
            f"pitch={direction.prosody.pitch}, "
            f"text={phrase}"
        )

    # ========================================================
    # ВРЕМЕННАЯ ПАПКА
    # ========================================================

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="video_ai_voice_",
            dir=str(output_mp3_path.parent),
        )
    )

    phrase_files = []

    phrase_results = []

    try:

        # ====================================================
        # ГЕНЕРИРУЕМ ФРАЗЫ ОТДЕЛЬНО
        # ====================================================

        for index, (phrase, direction) in enumerate(
            zip(phrases, directions),
            start=1,
        ):

            phrase_path = (
                temp_dir
                / f"phrase_{index:03d}.mp3"
            )

            word_boundaries = (
                await generate_phrase_audio(
                    phrase=phrase,
                    voice=voice,
                    prosody=direction.prosody,
                    output_path=phrase_path,
                )
            )

            if not phrase_path.exists():
                raise RuntimeError(
                    f"Не создан аудиофайл фразы #{index}."
                )

            duration = get_audio_duration(
                phrase_path
            )

            phrase_files.append(
                phrase_path
            )

            phrase_results.append(
                {
                    "phrase": phrase,
                    "word_boundaries": word_boundaries,
                    "duration": duration,
                    "pause_after": direction.prosody.pause_after,
                }
            )

            print(
                f"   🔊 Фраза #{index}: "
                f"{duration:.3f}s"
            )

        # ====================================================
        # ОБЩИЙ AUDIO
        # ====================================================

        print()
        print("🎚 Сборка voiceover-фрагментов...")

        concat_audio_files(
            input_files=phrase_files,
            output_path=output_mp3_path,
        )

        # ====================================================
        # ОБЩИЙ WORD TIMELINE
        # ====================================================

        word_boundaries = (
            merge_phrase_word_boundaries(
                phrase_results
            )
        )

        # ====================================================
        # SRT
        # ====================================================

        srt_text = build_grouped_srt(
            word_boundaries
        )

        with open(
            output_srt_path,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as file:

            file.write(
                srt_text
            )

        subtitle_count = 0

        if srt_text.strip():

            subtitle_count = len(
                srt_text.strip().split(
                    "\n\n"
                )
            )

        # ====================================================
        # ДИАГНОСТИКА
        # ====================================================

        print()
        print(
            f"Audio phrases: "
            f"{len(phrase_results)}"
        )

        print(
            f"WordBoundary: "
            f"{len(word_boundaries)}"
        )

        print(
            f"Subtitle cues: "
            f"{subtitle_count}"
        )

        print(
            f"SRT символов: "
            f"{len(srt_text)}"
        )

        total_duration = get_audio_duration(
            output_mp3_path
        )

        print(
            f"Voiceover duration: "
            f"{total_duration:.3f}s"
        )

        # ====================================================
        # ПРОВЕРКИ
        # ====================================================

        if not word_boundaries:

            raise RuntimeError(
                "WordBoundary не были получены."
            )

        if not srt_text.strip():

            raise RuntimeError(
                "SRT получился пустым."
            )

        if not output_mp3_path.exists():

            raise RuntimeError(
                "Файл voiceover.mp3 не был создан."
            )

        print()
        print(
            f"Озвучка сохранена: "
            f"{output_mp3_path}"
        )

        print(
            f"Субтитры сохранены: "
            f"{output_srt_path}"
        )

    finally:

        shutil.rmtree(
            temp_dir,
            ignore_errors=True,
        )


# ============================================================
# СИНХРОННАЯ ОБЁРТКА
# ============================================================

def create_voiceover(
    text: str,
    output_mp3_rel: str = (
        "02_PROCESSING/temp_audio/"
        "voiceover.mp3"
    ),
    output_srt_rel: str = (
        "02_PROCESSING/temp_audio/"
        "subtitles.srt"
    ),
    voice: str = DEFAULT_VOICE,
    voice_style: str = DEFAULT_PROSODY_STYLE,
):

    mp3_path = BASE_DIR / output_mp3_rel
    srt_path = BASE_DIR / output_srt_rel

    asyncio.run(
        generate_voiceover_async(
            text=text,
            output_mp3_path=mp3_path,
            output_srt_path=srt_path,
            voice=voice,
            voice_style=voice_style,
        )
    )

    return mp3_path, srt_path


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    sample_text = (
        "Хотите, чтобы ваш ребенок "
        "двигался уверенно и с удовольствием? "
        "Детские танцы помогают развить "
        "осанку, координацию и найти новых друзей. "
        "Подарите ребенку энергию движения "
        "и радость творчества!"
    )

    print()
    print("==============================================")
    print("TEST VOICEOVER")
    print("==============================================")
    print()

    print(
        f'Текст: "{sample_text}"'
    )

    print()

    mp3, srt = create_voiceover(
        text=sample_text,
        voice=DEFAULT_VOICE,
        voice_style="energetic",
    )

    print()
    print("==============================================")
    print("Тест завершён")
    print("==============================================")
    print()

    print(
        f"MP3: {mp3}"
    )

    print(
        f"SRT: {srt}"
    )