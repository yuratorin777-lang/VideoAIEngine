import os
import sys
import subprocess
import json
import re
import hashlib
from pathlib import Path
from src.composer.assembler import apply_cover_overlay, generate_cover_image
import requests


BASE_DIR = Path(__file__).resolve().parents[2]

DOWNLOADER_MODULE = "src.downloader.drive_downloader"
FORMATTER_MODULE = "src.formatter.video_normalizer"
ASSEMBLER_MODULE = "src.composer.assembler"

DEFAULT_VOICE = "ru-RU-SvetlanaNeural"
DEFAULT_VOICEOVER = "02_PROCESSING/temp_audio/voiceover.mp3"
DEFAULT_SUBTITLES = "02_PROCESSING/temp_audio/subtitles.srt"

DEFAULT_DURATION_SECONDS = 20
MAX_DURATION_OVERRUN_SECONDS = 1.5
VOICEOVER_TAIL_SECONDS = 0.20

MONTAGE_PLAN_PATH = (
    BASE_DIR / "06_COMPOSER" / "montage_plan.json"
)

VERCEL_PROXY_URL = os.getenv(
    "VERCEL_PROXY_URL",
    "https://video-ai-engine.vercel.app",
)


# ============================================================
# COMMAND RUNNER
# ============================================================

def run_command(command: list[str], title: str):
    print()
    print("=" * 70)
    print(f" {title}")
    print("=" * 70)
    print(
        f"[Pipeline] Запуск: {' '.join(command)}"
    )

    # Передаем env=os.environ.copy(), чтобы дочерний Python видел все пакеты и PYTHONPATH
    result = subprocess.run(
        command,
        cwd=BASE_DIR,
        env=os.environ.copy(),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{title} завершился с ошибкой. "
            f"Код возврата: {result.returncode}"
        )

    print(
        f"[Pipeline] ✓ {title} завершён"
    )


# ============================================================
# FORMAT DETECTION
# ============================================================

def detect_output_format(input_text: str) -> str:
    """
    Определяет технический формат ролика из ТЗ.
    """

    text = input_text.lower().strip()

    format_aliases = {
        "landscape": [
            "landscape",
            "горизонтальный",
            "горизонтальное",
            "горизонтальном",
            "16:9",
        ],
        "reels": [
            "reels",
            "рилс",
            "вертикальный",
            "вертикальное",
            "вертикальном",
            "9:16",
        ],
        "story": [
            "story",
            "stories",
            "сторис",
            "стори",
        ],
        "post": [
            "post",
            "пост",
            "лента",
            "4:5",
        ],
    }

    for format_name, aliases in format_aliases.items():
        for alias in aliases:
            if alias in text:
                return format_name

    return "reels"


# ============================================================
# DURATION DETECTION
# ============================================================

def detect_duration_seconds(input_text: str) -> int:
    """
    Пытается определить длительность ролика из ТЗ.

    Поддерживает:

        15 секунд
        20 сек
        30s
        30 s
        15-20 секунд

    Для диапазона берём верхнюю границу.

    Если длительность не указана:
        DEFAULT_DURATION_SECONDS
    """

    text = input_text.lower()

    range_patterns = [
        r"(\d{1,3})\s*[-–]\s*(\d{1,3})\s*(?:секунд(?:ы)?|сек\.?|s)\b",
    ]

    for pattern in range_patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            value = int(
                match.group(2)
            )

            if value > 0:
                return value

    patterns = [
        r"(\d{1,3})\s*(?:секунд(?:ы)?|сек\.?|s)\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            value = int(
                match.group(1)
            )

            if value > 0:
                return value

    return DEFAULT_DURATION_SECONDS


# ============================================================
# AUDIO MODE
# ============================================================

def detect_audio_mode(input_text: str) -> dict:
    """
    Определяет аудиорежим из ТЗ.

    Результат используется как часть
    Job / Content Contract.
    """

    text = input_text.lower().strip()

    # --------------------------------------------------------
    # ORIGINAL AUDIO
    # --------------------------------------------------------

    original_audio = False

    original_audio_keywords = [
        "оригинальный звук",
        "оригинальный ауди",
        "оставь звук",
        "оставить звук",
        "звук с видео",
        "живой звук",
        "original audio",
        "original sound",
    ]

    original_off_keywords = [
        "без оригинального звука",
        "без исходного звука",
        "убери оригинальный звук",
        "убрать оригинальный звук",
        "без звука с видео",
        "не использовать оригинальный звук",
        "не использовать исходный звук",
        "оригинальный звук не использовать",
        "исходный звук не использовать",
        "оригинальный звук исходных видео не использовать",
        "исходный звук исходных видео не использовать",
    ]

    if any(
        keyword in text
        for keyword in original_audio_keywords
    ):
        original_audio = True

    if any(
        keyword in text
        for keyword in original_off_keywords
    ):
        original_audio = False

    # --------------------------------------------------------
    # VOICEOVER & SUBTITLES
    # --------------------------------------------------------

    voiceover = False

    voiceover_on_keywords = [
        "с озвучкой",
        "с закадровой озвучкой",
        "закадровая озвучка",
        "нужна озвучка",
        "добавь озвучку",
        "голос за кадром",
        "голосовая озвучка",
        "voiceover",
        "voice over",
        "диктор",
        "дикторская озвучка",
        "голос озвучки",
        "tts",
        "neural",
        "ru-ru-",
        # --- ДОБАВЛЕННЫЕ КЛЮЧЕВЫЕ СЛОВА ---
        "озвучка вкл",
        "озвучка: вкл",
        "озвучка:вкл",
        "озвучка включена",
        "озвучку вкл",
        "voiceover on",
        "voiceover: on",
        "voiceover:on",
    ]

    voiceover_off_keywords = [
        "без озвучки",
        "без закадровой озвучкой",
        "без голоса",
        "озвучка не нужна",
        "без диктора",
        "voiceover off",
    ]

    # 1. Включаем, если найдено любое из ключевых слов озвучки или нейроголоса
    if any(keyword in text for keyword in voiceover_on_keywords):
        voiceover = True

    # 2. Стоп-слова имеют наивысший приоритет (если явно сказано "без озвучки")
    if any(keyword in text for keyword in voiceover_off_keywords):
        voiceover = False

    # 3. Авто-синхронизация субтитров с озвучкой
    subtitles = voiceover

    # --------------------------------------------------------
    # BACKGROUND MUSIC
    # --------------------------------------------------------

    background_music = True

    music_off_keywords = [
        "без музыки",
        "без фоновой музыки",
        "музыка не нужна",
        "убери музыку",
        "убрать музыку",
        "без музыкального сопровождения",
        "music off",
    ]

    music_on_keywords = [
        "с музыкой",
        "с фоновой музыкой",
        "добавь музыку",
        "музыкальное сопровождение",
        "background music",
    ]

    if any(
        keyword in text
        for keyword in music_off_keywords
    ):
        background_music = False

    elif any(
        keyword in text
        for keyword in music_on_keywords
    ):
        background_music = True

    # --------------------------------------------------------
    # SUBTITLES
    # --------------------------------------------------------

    subtitles = voiceover

    subtitles_on_keywords = [
        "с субтитрами",
        "добавь субтитры",
        "нужны субтитры",
        "с текстом на экране",
        "subtitles",
        "captions",
    ]

    subtitles_off_keywords = [
        "без субтитров",
        "без текста на экране",
        "субтитры не нужны",
        "убери субтитры",
        "subtitles off",
    ]

    if any(
        keyword in text
        for keyword in subtitles_on_keywords
    ):
        subtitles = True

    if any(
        keyword in text
        for keyword in subtitles_off_keywords
    ):
        subtitles = False

    return {
        "original_audio": original_audio,
        "background_music": background_music,
        "voiceover": voiceover,
        "subtitles": subtitles,
    }


# ============================================================
# VOICE DETECTION
# ============================================================

def detect_voice(input_text: str) -> str:
    """
    Определяет голос из ТЗ.
    """

    text = input_text.lower().strip()

    voice_aliases = {
        "ru-RU-SvetlanaNeural": [
            "светлана",
            "svetlana",
            "женский голос",
            "женский",
        ],
        "ru-RU-DmitryNeural": [
            "дмитрий",
            "dmitry",
            "мужской голос",
            "мужской",
        ],
    }

    for voice, aliases in voice_aliases.items():

        for alias in aliases:

            if alias in text:
                return voice

    return DEFAULT_VOICE


# ============================================================
# VOICE STYLE
# ============================================================

def detect_voice_style(input_text: str) -> str:
    """
    Определяет стилистическую характеристику голоса.

    Пока это параметр Content Contract.
    Реальное управление prosody TTS будет отдельным этапом.
    """

    text = input_text.lower()

    if any(
        word in text
        for word in [
            "энергич",
            "динамич",
            "активн",
            "весёл",
            "весел",
        ]
    ):
        return "energetic"

    if any(
        word in text
        for word in [
            "спокойн",
            "мягк",
            "добр",
            "тёпл",
            "тепл",
        ]
    ):
        return "warm"

    if any(
        word in text
        for word in [
            "эксперт",
            "профессиональн",
            "делов",
        ]
    ):
        return "professional"

    return "friendly"


# ============================================================
# MUSIC
# ============================================================

MUSIC_LIBRARY_RELATIVE = "04_LIBRARY/audio"

MUSIC_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".ogg",
    ".flac",
}


def get_music_library() -> list[Path]:
    """
    Возвращает список доступных музыкальных файлов
    из библиотеки 04_LIBRARY/audio.

    Конкретные имена треков не зашиваются в архитектуру.
    """

    library_path = BASE_DIR / MUSIC_LIBRARY_RELATIVE

    if not library_path.exists():
        raise RuntimeError(
            "Музыкальная библиотека не найдена:\n"
            f"{library_path}"
        )

    tracks = sorted(
        [
            path
            for path in library_path.iterdir()
            if path.is_file()
            and path.suffix.lower() in MUSIC_EXTENSIONS
        ],
        key=lambda path: path.name.lower(),
    )

    return tracks


def select_music_track(
    input_text: str,
) -> Path:
    """
    Автоматически выбирает музыкальный трек
    из библиотеки.

    Выбор детерминированный:
    одинаковое ТЗ + одинаковая библиотека
    дают одинаковый трек.

    Конкретные имена файлов в коде не используются.
    """

    tracks = get_music_library()

    if not tracks:
        raise RuntimeError(
            "В музыкальной библиотеке нет доступных треков:\n"
            f"{BASE_DIR / MUSIC_LIBRARY_RELATIVE}"
        )

    seed = hashlib.sha256(
        input_text.strip().encode("utf-8")
    ).hexdigest()

    index = int(seed, 16) % len(tracks)

    selected = tracks[index]

    print()
    print(
        f"[Music] Найдено треков в библиотеке: "
        f"{len(tracks)}"
    )
    print(
        f"[Music] Автоматически выбран трек: "
        f"{selected.name}"
    )

    return selected


def detect_music(
    input_text: str,
    audio_mode: dict,
) -> str | None:
    """
    Определяет музыкальный трек.

    Если фоновая музыка отключена:
        возвращает None.

    Если музыка включена:
        сканирует музыкальную библиотеку
        и автоматически выбирает доступный трек.
    """

    if not audio_mode["background_music"]:
        return None

    selected_track = select_music_track(
        input_text=input_text,
    )

    return str(
        selected_track.relative_to(BASE_DIR)
    )


# ============================================================
# JOB / CONTENT CONTRACT
# ============================================================

def build_job_contract(input_text: str) -> dict:
    """
    Формирует Job / Content Contract из ТЗ.
    """

    output_format = detect_output_format(
        input_text
    )

    duration_seconds = detect_duration_seconds(
        input_text
    )

    audio_mode = detect_audio_mode(
        input_text
    )

    voice = detect_voice(
        input_text
    )

    voice_style = detect_voice_style(
        input_text
    )

    music = detect_music(
        input_text,
        audio_mode,
    )

    contract = {
        "content_profile": {
            "audience": "parents",
            "topic": "children dance",
            "tone": voice_style,
            "intent": "engagement",
            "content_type": "dance",
            "tags": [
                "kids",
                "dance",
            ],
        },

        "output": {
            "format": output_format,
            "duration_seconds": duration_seconds,
        },

        "audio": {
            "original_audio": audio_mode[
                "original_audio"
            ],

            "background_music": audio_mode[
                "background_music"
            ],

            "voiceover": audio_mode[
                "voiceover"
            ],

            "voice": voice,

            "voice_style": voice_style,

            "subtitles": audio_mode[
                "subtitles"
            ],

            "music_volume": 0.15,

            "voice_volume": 1.0,

            "music_path": music,
        },

        "script": {
            "required": audio_mode[
                "voiceover"
            ],

            "text": None,
        },
    }

    return contract


# ============================================================
# CONTRACT → MONTAGE PLAN
# ============================================================

def apply_job_contract(
    plan_path: Path,
    contract: dict,
):
    """
    Применяет Job / Content Contract
    к уже созданному montage_plan.json.

    Retriever отвечает за cuts.

    Production Pipeline отвечает
    за production contract.
    """

    if not plan_path.exists():

        raise RuntimeError(
            f"Montage plan не найден: {plan_path}"
        )

    with plan_path.open(
        "r",
        encoding="utf-8",
    ) as f:

        plan = json.load(f)

    if not isinstance(
        plan,
        dict,
    ):

        raise RuntimeError(
            "montage_plan.json имеет "
            "некорректную структуру."
        )

    # --------------------------------------------------------
    # CONTENT PROFILE
    # --------------------------------------------------------

    content_profile = contract.get(
        "content_profile"
    )

    if isinstance(
        content_profile,
        dict,
    ):

        plan[
            "content_profile"
        ] = content_profile

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    output = plan.get(
        "output"
    )

    if not isinstance(
        output,
        dict,
    ):

        output = {}

    contract_output = contract.get(
        "output",
        {},
    )

    if isinstance(
        contract_output,
        dict,
    ):

        output.update(
            contract_output
        )

    plan["output"] = output

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = plan.get(
        "audio"
    )

    if not isinstance(
        audio,
        dict,
    ):

        audio = {}

    contract_audio = contract.get(
        "audio",
        {},
    )

    if isinstance(
        contract_audio,
        dict,
    ):

        audio[
            "original_audio"
        ] = contract_audio.get(
            "original_audio",
            False,
        )

        audio[
            "background_music_enabled"
        ] = contract_audio.get(
            "background_music",
            False,
        )

        audio[
            "voiceover_enabled"
        ] = contract_audio.get(
            "voiceover",
            False,
        )

        audio[
            "subtitles_enabled"
        ] = contract_audio.get(
            "subtitles",
            False,
        )

        audio[
            "voice"
        ] = contract_audio.get(
            "voice"
        )

        audio[
            "voice_style"
        ] = contract_audio.get(
            "voice_style"
        )

        audio[
            "music_volume"
        ] = contract_audio.get(
            "music_volume",
            0.15,
        )

        audio[
            "voice_volume"
        ] = contract_audio.get(
            "voice_volume",
            1.0,
        )

        music_path = contract_audio.get(
            "music_path"
        )

        audio[
            "background_music"
        ] = music_path

        if contract_audio.get(
            "voiceover"
        ):

            audio[
                "voiceover"
            ] = DEFAULT_VOICEOVER

        else:

            audio[
                "voiceover"
            ] = None

        if contract_audio.get(
            "subtitles"
        ):

            audio[
                "subtitles"
            ] = DEFAULT_SUBTITLES

        else:

            audio[
                "subtitles"
            ] = None

    plan["audio"] = audio

    # --------------------------------------------------------
    # SCRIPT
    # --------------------------------------------------------

    script = contract.get(
        "script"
    )

    if isinstance(
        script,
        dict,
    ):

        plan[
            "script"
        ] = script

    # --------------------------------------------------------
    # WRITE
    # --------------------------------------------------------

    with plan_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            plan,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        "[Pipeline] ✓ Job / Content Contract применён"
    )

    print(
        f"[Contract] format: "
        f"{plan.get('output', {}).get('format')}"
    )

    print(
        f"[Contract] duration: "
        f"{plan.get('output', {}).get('duration_seconds')}"
    )

    print(
        f"[Contract] voiceover: "
        f"{plan.get('audio', {}).get('voiceover_enabled')}"
    )

    print(
        f"[Contract] voice: "
        f"{plan.get('audio', {}).get('voice')}"
    )

    print(
        f"[Contract] subtitles: "
        f"{plan.get('audio', {}).get('subtitles_enabled')}"
    )

    print(
        f"[Contract] music: "
        f"{plan.get('audio', {}).get('background_music_enabled')}"
    )


# ============================================================
# EXPLICIT VOICEOVER TEXT
# ============================================================

def extract_explicit_voiceover_text(
    input_text: str,
) -> str | None:
    """
    Ищет явно заданный пользователем текст озвучки.

    Поддерживает:

        Текст озвучки: ...
        Текст для озвучки: ...
        Озвучка: ...
        Voiceover text: ...

    Если найден явный текст,
    Gemini Script Generator не запускается.
    """

    patterns = [
        r"(?is)текст\s+озвучки\s*:\s*(.+)",
        r"(?is)текст\s+для\s+озвучки\s*:\s*(.+)",
        r"(?is)озвучка\s*:\s*(.+)",
        r"(?is)voiceover\s+text\s*:\s*(.+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            input_text,
        )

        if match:

            value = match.group(1).strip()

            if value:

                return value

    return None


# ============================================================
# GEMINI RESPONSE CLEANER
# ============================================================

def clean_json_response(
    text: str,
) -> str:
    """
    Убирает markdown code fences,
    если Gemini вернул JSON внутри ```json ... ```.
    """

    value = text.strip()

    if value.startswith("```"):

        value = re.sub(
            r"^```(?:json)?\s*",
            "",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"\s*```$",
            "",
            value,
        )

    return value.strip()


# ============================================================
# SCRIPT GENERATOR — GEMINI
# ============================================================

SCRIPT_SYSTEM_INSTRUCTION = """
Ты — Script Generator внутри VideoAIEngine.

Твоя задача — написать короткий текст закадровой
озвучки для будущего короткого видеоролика.

Работай строго на основании переданного ТЗ
и Content Contract.

Не придумывай:
- адреса;
- цены;
- акции;
- названия;
- преимущества, которых нет в ТЗ;
- факты о компании;
- гарантии;
- конкретные результаты.

КРИТИЧЕСКОЕ ТРЕБОВАНИЕ ПО ДЛИТЕЛЬНОСТИ:

Текст должен физически укладываться в заданную
длительность ролика при естественной скорости
русской рекламной речи.

Нельзя писать длинный текст с расчётом на то,
что его потом будут ускорять или обрезать.

Количество символов должно соответствовать
переданному лимиту max_script_chars.

Целевой текст должен быть примерно на 75–90% 
от допустимого лимита. 

Не стремись заполнить лимит символов. 
Лучше сделать текст короче, чем получить voiceover, 
который не помещается в длительность ролика. 
 
Текст должен: 
- соответствовать аудитории; 

Текст должен:
- соответствовать аудитории;
- соответствовать цели ролика;
- соответствовать tone;
- звучать естественно при синтезе речи;
- быть коротким;
- содержать только действительно важные сообщения;
- при необходимости завершаться коротким CTA;
- не содержать заголовков;
- не содержать markdown;
- не содержать эмодзи;
- не содержать пояснений.

Не описывай монтаж.
Не выбирай кадры.
Не описывай визуал.
Не добавляй технические инструкции.

Верни ТОЛЬКО JSON:

{
  "script": "текст озвучки"
}
"""


def generate_script_with_gemini(
    input_text: str,
    contract: dict,
) -> str:

    duration_seconds = contract.get(
        "output",
        {},
    ).get(
        "duration_seconds",
        DEFAULT_DURATION_SECONDS,
    )

    content_profile = contract.get(
        "content_profile",
        {},
    )

    voice_style = contract.get(
        "audio",
        {},
    ).get(
        "voice_style",
        "friendly",
    )

    # Для русского TTS ориентируемся не на символы,
# а на безопасный объём текста для заданной длительности.
# ~2.0–2.2 слова/сек — нормальный рекламный темп с паузами.
    target_words = max(
       8,
       int(duration_seconds * 2.0),
    )

    max_words = max(
       10,
       int(duration_seconds * 2.2),
    )

    max_script_chars = max(
       80,
       int(max_words * 6.5),
    )

    target_min_chars = max(
       60,
       int(max_script_chars * 0.70),
    )

    target_max_chars = max_script_chars

    prompt = f"""
ТЗ пользователя:

{input_text}

Content Profile:

{json.dumps(
    content_profile,
    ensure_ascii=False,
    indent=2,
)}

Production parameters:

Длительность готового ролика:
{duration_seconds} секунд

Стиль голоса:
{voice_style}

ОГРАНИЧЕНИЕ ТЕКСТА ОЗВУЧКИ:

ЦЕЛЕВОЙ ОБЪЁМ:
примерно {target_words} слов.

МАКСИМАЛЬНЫЙ ОБЪЁМ:
не более {max_words} слов.

Дополнительно:
текст не должен превышать {target_max_chars} символов.

Для ролика длительностью {duration_seconds} секунд
приоритет имеет фактическое время произнесения,
а не заполнение лимита символов.

Для ролика длительностью {duration_seconds} секунд
текст должен быть рассчитан на естественное
произнесение с паузами.

НЕ ПЫТАЙСЯ заполнить весь доступный лимит.
Главное — смысл, естественность и соответствие ТЗ.

Если ТЗ содержит много требований,
выбери только самые важные для рекламного ролика.

Для короткого ролика используй короткие предложения.
Не повторяй одну мысль разными словами.
Не добавляй вступительные фразы без смысловой ценности.

ВАЖНО:
Итоговый script НЕ ДОЛЖЕН превышать
{target_max_chars} символов.

Напиши текст закадровой озвучки.

Не описывай монтаж.
Не выбирай кадры.
Не описывай визуал.
Не добавляй технические инструкции.

Верни только JSON указанного формата.
"""

    proxy_url = VERCEL_PROXY_URL.rstrip("/")

    endpoint = (
        f"{proxy_url}/api/gemini"
    )

    payload = {
        "action": "generateContent",

        "prompt": prompt,

        "systemInstruction":
            SCRIPT_SYSTEM_INSTRUCTION,

        "responseMimeType":
            "application/json",

        "temperature": 0.4,
    }

    print()
    print("=" * 70)
    print(" SCRIPT GENERATOR")
    print("=" * 70)

    print(
        "[Pipeline] Отправка ТЗ в Script Generator..."
    )

    try:

        response = requests.post(
            endpoint,
            json=payload,
            timeout=120,
        )

    except requests.RequestException as e:

        raise RuntimeError(
            "Ошибка соединения с Vercel/Gemini "
            f"при генерации script: {e}"
        ) from e

    if response.status_code != 200:

        body = response.text[:2000]

        raise RuntimeError(
            "Script Generator вернул HTTP "
            f"{response.status_code}.\n"
            f"{body}"
        )

    try:

        data = response.json()

    except ValueError as e:

        raise RuntimeError(
            "Script Generator вернул "
            "некорректный JSON response."
        ) from e

    if not isinstance(
        data,
        dict,
    ):

        raise RuntimeError(
            "Ответ Script Generator "
            "имеет некорректную структуру."
        )

    # --------------------------------------------------------
    # EXTRACT GENERATED TEXT
    # --------------------------------------------------------

    generated_text = None

    if isinstance(
        data.get("text"),
        str,
    ):

        generated_text = data[
            "text"
        ]

    elif isinstance(
        data.get("result"),
        str,
    ):

        generated_text = data[
            "result"
        ]

    elif isinstance(
        data.get("content"),
        str,
    ):

        generated_text = data[
            "content"
        ]

    elif isinstance(
        data.get("data"),
        str,
    ):

        generated_text = data[
            "data"
        ]

    elif isinstance(
        data.get("data"),
        dict,
    ):

        nested = data[
            "data"
        ]

        for key in [
            "text",
            "result",
            "content",
        ]:

            if isinstance(
                nested.get(key),
                str,
            ):

                generated_text = nested[
                    key
                ]

                break

    if not generated_text:

        raise RuntimeError(
            "Script Generator не вернул "
            "текст генерации."
        )

    # --------------------------------------------------------
    # PARSE JSON
    # --------------------------------------------------------

    cleaned = clean_json_response(
        generated_text
    )

    try:

        script_data = json.loads(
            cleaned
        )

    except json.JSONDecodeError as e:

        raise RuntimeError(
            "Script Generator вернул "
            "текст вместо ожидаемого JSON.\n"
            f"Ответ:\n{generated_text}"
        ) from e

    if not isinstance(
        script_data,
        dict,
    ):

        raise RuntimeError(
            "JSON Script Generator "
            "имеет некорректную структуру."
        )

    script = script_data.get(
        "script"
    )

    if not isinstance(
        script,
        str,
    ):

        raise RuntimeError(
            "В ответе Script Generator "
            "отсутствует поле 'script'."
        )

    script = script.strip()

    if not script:

        raise RuntimeError(
            "Script Generator вернул "
            "пустой script."
        )

    print()
    print(
        "[Script Generator] ✓ Текст получен:"
    )

    print(
        f"[Script Generator] {script}"
    )

    print(
        f"[Script Generator] Символов: "
        f"{len(script)}"
    )

    return script


# ============================================================
# SCRIPT GENERATOR
# ============================================================

def generate_voiceover_script(
    input_text: str,
    contract: dict,
) -> str | None:
    """
    Главная точка генерации voiceover script.

    Приоритет:

    1. Явный текст пользователя.
    2. Gemini Script Generator.
    3. None, если voiceover выключен.
    """

    audio = contract.get(
        "audio",
        {},
    )

    voiceover_enabled = bool(
        audio.get(
            "voiceover"
        )
    )

    if not voiceover_enabled:

        print()
        print(
            "[Pipeline] Voiceover выключен."
        )

        return None

    # --------------------------------------------------------
    # EXPLICIT USER SCRIPT
    # --------------------------------------------------------

    explicit_text = (
        extract_explicit_voiceover_text(
            input_text
        )
    )

    if explicit_text:

        print()
        print(
            "[Pipeline] Найден явный текст "
            "озвучки в ТЗ."
        )

        print(
            f"[Pipeline] Script: "
            f"{explicit_text}"
        )

        return explicit_text

    # --------------------------------------------------------
    # GEMINI SCRIPT GENERATOR
    # --------------------------------------------------------

    script = generate_script_with_gemini(
        input_text=input_text,
        contract=contract,
    )

    return script


# ============================================================
# SAVE SCRIPT TO CONTRACT / PLAN
# ============================================================

def apply_script_to_contract(
    contract: dict,
    script: str | None,
):
    """
    Сохраняет результат Script Generator
    в Job / Content Contract.
    """

    if "script" not in contract:
        contract["script"] = {}

    contract["script"][
        "required"
    ] = bool(
        script
    )

    contract["script"][
        "text"
    ] = script


def apply_script_to_plan(
    plan_path: Path,
    script: str | None,
):
    """
    Сохраняет generated script
    непосредственно в montage_plan.json.

    Это нужно для traceability job.
    """

    if not plan_path.exists():

        raise RuntimeError(
            f"Montage plan не найден: {plan_path}"
        )

    with plan_path.open(
        "r",
        encoding="utf-8",
    ) as f:

        plan = json.load(f)

    if not isinstance(
        plan,
        dict,
    ):

        raise RuntimeError(
            "montage_plan.json имеет "
            "некорректную структуру."
        )

    plan["script"] = {
        "required": bool(script),
        "text": script,
    }

    with plan_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            plan,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        "[Pipeline] ✓ Script сохранён "
        "в montage_plan.json"
    )


# ============================================================
# VOICEOVER
# ============================================================

def run_voiceover(
    input_text: str,
    contract: dict,
):
    """
    Запускает существующий voiceover.py.

    Voiceover:

        voiceover.mp3

        +

        subtitles.srt

    генерируются только если voiceover включён.

    Если voiceover выключен:
        старые временные файлы удаляются.
    """

    audio = contract.get(
        "audio",
        {},
    )

    voiceover_enabled = bool(
        audio.get(
            "voiceover"
        )
    )

    voiceover_path = (
        BASE_DIR / DEFAULT_VOICEOVER
    )

    subtitles_path = (
        BASE_DIR / DEFAULT_SUBTITLES
    )

    # --------------------------------------------------------
    # VOICEOVER OFF
    # --------------------------------------------------------

    if not voiceover_enabled:

        print()
        print("=" * 70)
        print(" VOICEOVER")
        print("=" * 70)

        print(
            "[Pipeline] Voiceover отключён."
        )

        if voiceover_path.exists():

            voiceover_path.unlink()

            print(
                f"[Pipeline] Удалён старый "
                f"voiceover: {voiceover_path}"
            )

        if subtitles_path.exists():

            subtitles_path.unlink()

            print(
                f"[Pipeline] Удалены старые "
                f"subtitles: {subtitles_path}"
            )

        return None, None

    # --------------------------------------------------------
    # SCRIPT
    # --------------------------------------------------------

    script = contract.get(
        "script",
        {},
    ).get(
        "text"
    )

    if not script:

        raise RuntimeError(
            "Voiceover включён, "
            "но script отсутствует."
        )

    voice = audio.get(
        "voice",
        DEFAULT_VOICE,
    )

    print()
    print("=" * 70)
    print(" VOICEOVER")
    print("=" * 70)

    print(
        f"[Pipeline] Голос: {voice}"
    )

    print(
        f"[Pipeline] Текст: {script}"
    )

    # --------------------------------------------------------
    # EXISTING VOICEOVER MODULE
    # --------------------------------------------------------

    from src.composer.voiceover import (
        create_voiceover
    )

    mp3_path, srt_path = (
        create_voiceover(
    text=script,
    output_mp3_rel=DEFAULT_VOICEOVER,
    output_srt_rel=DEFAULT_SUBTITLES,
    voice=voice,
    voice_style=audio.get(
        "voice_style",
        "friendly",
    ),
)
    )

    print(
        f"[Pipeline] ✓ Voiceover MP3: "
        f"{mp3_path}"
    )

    print(
        f"[Pipeline] ✓ Subtitles SRT: "
        f"{srt_path}"
    )

    return mp3_path, srt_path


# ============================================================
# DURATION RECONCILIATION
# ============================================================

def get_media_duration_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True,
    )

    value = result.stdout.strip()
    if not value:
        raise RuntimeError(
            f"Не удалось определить длительность: {path}"
        )

    return float(value)


def reconcile_plan_duration_with_voiceover(
    plan_path: Path,
    voiceover_path: Path | None,
    target_duration: float,
):
    if not voiceover_path or not voiceover_path.exists():
        return

    voiceover_duration = get_media_duration_seconds(
        voiceover_path
    )

    required_duration = max(
        target_duration,
        min(
            voiceover_duration,
            target_duration + MAX_DURATION_OVERRUN_SECONDS,
        ),
    )

    if voiceover_duration <= target_duration + 0.01:
        print(
            f"[Duration] Voiceover {voiceover_duration:.3f}s "
            f"укладывается в целевые {target_duration:.3f}s."
        )
        return

    if voiceover_duration > target_duration + MAX_DURATION_OVERRUN_SECONDS:
        raise RuntimeError(
            "Voiceover слишком длинный для допустимой погрешности: "
            f"{voiceover_duration:.3f}s при цели {target_duration:.3f}s "
            f"(максимум {target_duration + MAX_DURATION_OVERRUN_SECONDS:.3f}s)."
        )

    with plan_path.open(
        "r",
        encoding="utf-8",
    ) as f:
        plan = json.load(f)

    cuts = plan.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        raise RuntimeError(
            "Невозможно согласовать длительность: cuts отсутствуют."
        )

    current_duration = sum(
        float(cut["end"]) - float(cut["start"])
        for cut in cuts
    )

    delta = required_duration - current_duration
    if delta <= 0.01:
        return

    remaining = delta

    # Сначала расширяем последний кадр, затем предыдущие.
    # Расширение разрешено только внутри relevant_segment и до 6 секунд.
    for cut in reversed(cuts):
        if remaining <= 0.01:
            break

        start = float(cut["start"])
        end = float(cut["end"])
        relevant_segment = cut.get("relevant_segment") or {}

        segment_end = relevant_segment.get("end")
        if segment_end is None:
            continue

        segment_end = float(segment_end)
        current_cut_duration = end - start
        max_cut_end = min(
            segment_end,
            start + 6.0,
        )
        available = max(
            0.0,
            max_cut_end - end,
        )

        if available <= 0.01:
            continue

        extension = min(
            available,
            remaining,
        )

        cut["end"] = round(
            end + extension,
            3,
        )

        remaining -= extension

    if remaining > 0.01:
        raise RuntimeError(
            "Не удалось полностью расширить montage plan под voiceover: "
            f"не хватает {remaining:.3f}s доступного видеоматериала."
        )

    plan.setdefault("output", {})[
        "duration_seconds"
    ] = round(
        required_duration,
        3,
    )

    with plan_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            plan,
            f,
            ensure_ascii=False,
            indent=2,
        )

    actual_duration = sum(
        float(cut["end"]) - float(cut["start"])
        for cut in cuts
    )

    print()
    print(
        f"[Duration] Voiceover: {voiceover_duration:.3f}s"
    )
    print(
        f"[Duration] Цель: {target_duration:.3f}s"
    )
    print(
        f"[Duration] Видеоряд расширен до: {actual_duration:.3f}s"
    )
    print(
        "[Duration] ✓ Озвучка и субтитры не будут обрезаны."
    )


# ============================================================
# RETRIEVER
# ============================================================

def run_retriever(
    input_text: str,
    contract: dict,
):
    print()
    print("=" * 70)
    print(" RETRIEVER + GEMINI")
    print("=" * 70)

    print(
        "[Pipeline] ТЗ:"
    )

    print(input_text)

    print()

    print(
        "[Pipeline] Job / Content Contract:"
    )

    print(
        json.dumps(
            contract,
            ensure_ascii=False,
            indent=2,
        )
    )

    # --------------------------------------------------------
    # RETRIEVER
    # --------------------------------------------------------

    from src.retriever.retriever import (
        generate_montage_plan,
    )

    generate_montage_plan(
        input_text=input_text,
        is_post=True,
        top_k=12,
    )

    plan_path = (
        BASE_DIR
        / "06_COMPOSER"
        / "montage_plan.json"
    )

    if not plan_path.exists():

        raise RuntimeError(
            f"Retriever не создал "
            f"montage_plan.json: {plan_path}"
        )

    # --------------------------------------------------------
    # APPLY CONTRACT
    # --------------------------------------------------------

    apply_job_contract(
        plan_path=plan_path,
        contract=contract,
    )

    print(
        f"[Pipeline] ✓ Montage plan создан: "
        f"{plan_path}"
    )


# ============================================================
# FINAL OUTPUT CHECK
# ============================================================

def check_final_output() -> Path:
    """
    Проверяет существование итогового MP4.
    """

    output_path = (
        BASE_DIR
        / "07_OUTPUT"
        / "rendered_reel.mp4"
    )

    if not output_path.exists():

        raise RuntimeError(
            "Pipeline завершился, "
            "но итоговый файл не найден:\n"
            f"{output_path}"
        )

    if output_path.stat().st_size <= 0:

        raise RuntimeError(
            "Итоговый MP4 существует, "
            "но имеет нулевой размер."
        )

    return output_path


# ============================================================
# FULL PIPELINE
# ============================================================

def run_pipeline(
    input_text: str,
):
    print()
    print("=" * 70)
    print(
        " VIDEO AI ENGINE — PRODUCTION PIPELINE"
    )
    print("=" * 70)

    print()
    print(
        "[Pipeline] Получено новое ТЗ."
    )

    print(
        "[Pipeline] Запускаем полный "
        "производственный цикл."
    )

    # ---------------------------------------------------------
    # 1. JOB / CONTENT CONTRACT
    # ---------------------------------------------------------

    contract = build_job_contract(
        input_text
    )

    print()
    print("=" * 70)
    print(
        " JOB / CONTENT CONTRACT"
    )
    print("=" * 70)

    print(
        json.dumps(
            contract,
            ensure_ascii=False,
            indent=2,
        )
    )

    # ---------------------------------------------------------
    # 2. RETRIEVER + GEMINI
    # ---------------------------------------------------------

    run_retriever(
        input_text=input_text,
        contract=contract,
    )

    # ---------------------------------------------------------
    # 3. SCRIPT GENERATOR
    # ---------------------------------------------------------

    script = generate_voiceover_script(
        input_text=input_text,
        contract=contract,
    )

    apply_script_to_contract(
        contract=contract,
        script=script,
    )

    apply_script_to_plan(
        plan_path=MONTAGE_PLAN_PATH,
        script=script,
    )

    # ---------------------------------------------------------
    # 4. VOICEOVER + SUBTITLES
    # ---------------------------------------------------------

    voiceover_path, subtitles_path = run_voiceover(
        input_text=input_text,
        contract=contract,
    )

    # ---------------------------------------------------------
    # 4.1 DURATION RECONCILIATION
    # ---------------------------------------------------------
    reconcile_plan_duration_with_voiceover(
        plan_path=MONTAGE_PLAN_PATH,
        voiceover_path=(
            BASE_DIR / voiceover_path
            if voiceover_path
            and not Path(voiceover_path).is_absolute()
            else Path(voiceover_path)
            if voiceover_path
            else None
        ),
        target_duration=float(
            contract.get("output", {})
            .get("duration_seconds", DEFAULT_DURATION_SECONDS)
        ),
    )

    # ---------------------------------------------------------
    # 5. DOWNLOADER
    # ---------------------------------------------------------

    run_command(
        [
            sys.executable,
            "-m",
            DOWNLOADER_MODULE,
        ],
        "DRIVE DOWNLOADER",
    )

    # ---------------------------------------------------------
    # 6. FORMAT ADAPTER
    # ---------------------------------------------------------

    run_command(
        [
            sys.executable,
            "-m",
            FORMATTER_MODULE,
        ],
        "FORMAT ADAPTER",
    )

    # ---------------------------------------------------------
    # 7. ASSEMBLER
    # ---------------------------------------------------------

    run_command(
        [
            sys.executable,
            "-m",
            ASSEMBLER_MODULE,
        ],
        "ASSEMBLER",
    )

    # ---------------------------------------------------------
    # 7.1 COVER GENERATOR & OVERLAY (Генерация и вклейка обложки)
    # ---------------------------------------------------------
    print(
        "\n======================================================================"
    )
    print(" COVER GENERATOR & OVERLAY")
    print(
        "======================================================================"
    )

    try:
        from src.composer.assembler import (
            apply_cover_overlay,
            generate_cover_image,
        )

        # 1. Находим скомпонованный видеофайл в папке 07_OUTPUT
        output_dir = Path("07_OUTPUT")
        video_files = [
            f for f in output_dir.glob("*.mp4") 
            if not f.name.startswith("temp_")
        ]

        if not video_files:
            # Если нет финального файла, пробуем найти темповый
            video_files = list(output_dir.glob("*.mp4"))

        if not video_files:
            print("[Cover] Ошибка: Итоговый видеофайл в 07_OUTPUT не найден!")
        else:
            # Берем самый свежий собранный ролик
            target_video = max(video_files, key=lambda f: f.stat().st_mtime)
            print(f"[Cover] Целевое видео для обложки: {target_video}")

            # 2. Определяем ориентацию (landscape / vertical)
            is_landscape = False
            local_vars = locals()
            current_contract = local_vars.get("job_contract") or local_vars.get("contract", {})
            
            if isinstance(current_contract, dict):
                is_landscape = (
                    current_contract.get("output", {}).get("format") == "landscape"
                )

            cover_title = (
                current_contract.get("script", {}).get("title")
                if isinstance(current_contract, dict) and current_contract.get("script")
                else "ОТКРЫТ НАБОР В НОВЫЕ ГРУППЫ!"
            )

            # 3. Генерируем PNG-обложку из кадра видео
            cover_png = generate_cover_image(
                video_path=target_video,
                cover_title=cover_title,
                brand_name="dance_kids",
                is_landscape=is_landscape,
                output_png_path="07_OUTPUT/video_cover.png",
            )
            print(f"[Pipeline] ✓ Сохранена статичная обложка: {cover_png}")

            # 4. Накладываем обложку на первые 1.5 сек этого же ролика
            apply_cover_overlay(
                input_video_path=target_video,
                cover_image_path=cover_png,
                output_video_path=target_video,
                duration=1.5,
            )
            print(f"[Pipeline] ✓ Обложка успешно вшита в первые 1.5 секунды видео!")

    except Exception as e:
        print(f"[Pipeline] Ошибка при обработке обложки: {e}")

    # ---------------------------------------------------------
    # 8. FINAL CHECK
    # ---------------------------------------------------------

    output_path = check_final_output()

    print()
    print("=" * 70)
    print(
        " PRODUCTION COMPLETE"
    )
    print("=" * 70)

    print(
        f"✓ Итоговый файл: {output_path}"
    )

    print(
        f"✓ Размер файла: "
        f"{output_path.stat().st_size / 1024 / 1024:.2f} MB"
    )

    print()
    print(
        "🎉 Production pipeline "
        "успешно завершён."
    )


# ============================================================
# CLI
# ============================================================

def main():

    if len(sys.argv) < 2:

        print()
        print(
            "Использование:"
        )

        print()

        print(
            'python -m src.core.production_pipeline '
            '"Ваше ТЗ на создание ролика"'
        )

        print()

        return

    input_text = " ".join(
        sys.argv[1:]
    ).strip()

    if not input_text:

        raise ValueError(
            "ТЗ не может быть пустым."
        )

    run_pipeline(
        input_text
    )


if __name__ == "__main__":
    main()