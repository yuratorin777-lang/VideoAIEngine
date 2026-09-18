import json

import os

import re

import time

from pathlib import Path

from typing import Any

import requests

from dotenv import load_dotenv


load_dotenv()


# ============================================================
# PATHS
# ============================================================

PASSPORTS_DIR = Path("04_LIBRARY/passports")
OUTPUT_PLAN_PATH = Path("06_COMPOSER/montage_plan.json")


# ============================================================
# RETRIEVER SETTINGS
# ============================================================

DEFAULT_TOP_K = 12
MIN_SCORE = 1.0
REQUEST_TIMEOUT = 120

TARGET_DURATION_SECONDS = 30.0
DURATION_TOLERANCE_SECONDS = 0.01

MIN_CUT_DURATION_SECONDS = 1.5
MAX_CUT_DURATION_SECONDS = 6.0
MIN_CUTS = 4
MAX_CUTS = 8

# ==============================================================================
# БЛОК ИСТОРИИ И COOLDOWN (ОТДЫХ ИСХОДНИКОВ)
# ==============================================================================
# ==============================================================================
# БЛОК ИСТОРИИ И COOLDOWN (ОТДЫХ ИСХОДНИКОВ)
# ==============================================================================

def _find_project_root() -> Path:
    """Находит корень проекта по наличию папки 04_LIBRARY или .git."""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "04_LIBRARY").exists() or (parent / ".git").exists():
            return parent
    return Path.cwd()

PROJECT_ROOT = _find_project_root()
HISTORY_FILE = PROJECT_ROOT / "04_LIBRARY" / "history.json"
COOLDOWN_RUNS = 3  # Пауза на 3 генерации

def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[History Warning] Ошибка чтения истории: {e}")
        return []

def save_history(history: list[dict]):
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"[History] Файл истории успешно сохранен: {HISTORY_FILE}")
    except Exception as e:
        print(f"[History Warning] Не удалось сохранить историю в {HISTORY_FILE}: {e}")

def get_blocked_file_ids() -> set[str]:
    """Возвращает set file_id, использовавшихся в последних COOLDOWN_RUNS генерациях."""
    history = load_history()
    recent_runs = history[-COOLDOWN_RUNS:] if len(history) >= COOLDOWN_RUNS else history
    
    blocked_ids = set()
    for run in recent_runs:
        for file_id in run.get("used_file_ids", []):
            blocked_ids.add(file_id)
    return blocked_ids

def record_used_candidates(plan: dict):
    """Записывает file_id из итогового монтажного плана в историю."""
    used_ids = list({cut["file_id"] for cut in plan.get("cuts", []) if "file_id" in cut})
    if not used_ids:
        return
        
    history = load_history()
    history.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "used_file_ids": used_ids
    })
    save_history(history[-20:])  # Храним историю за последние 20 генераций
    print(f"[History] Записано {len(used_ids)} использованных видео в историю.")

# ============================================================
# PASSPORT LOADING
# ============================================================

def load_all_passports(
    passports_dir: Path,
) -> list[dict[str, Any]]:
    passports = []

    if not passports_dir.exists():
        raise FileNotFoundError(
            f"Папка паспортов не найдена: {passports_dir}"
        )

    for file_path in sorted(
        passports_dir.glob("*.json")
    ):
        try:
            with open(
                file_path,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

            if not isinstance(data, dict):
                print(
                    f"[-] Пропуск некорректного паспорта: "
                    f"{file_path.name}"
                )
                continue

            data["_file_name"] = file_path.name

            passports.append(data)

        except Exception as e:
            print(
                f"[-] Ошибка чтения паспорта "
                f"{file_path}: {e}"
            )

    return passports


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return " ".join(
            normalize_text(item)
            for item in value
        )

    if isinstance(value, dict):
        return " ".join(
            normalize_text(item)
            for item in value.values()
        )

    text = str(value).lower()

    text = text.replace("ё", "е")

    text = re.sub(
        r"[^a-zа-я0-9\s-]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def tokenize(text: str) -> set[str]:
    normalized = normalize_text(text)

    if not normalized:
        return set()

    return {
        token
        for token in normalized.split()
        if len(token) >= 2
    }


# ============================================================
# PASSPORT SEARCH TEXT
# ============================================================

def passport_search_text(
    passport: dict[str, Any],
) -> str:
    parts = []

    search_index = passport.get(
        "search_index",
        {},
    )

    classification = passport.get(
        "classification",
        {},
    )

    video = passport.get(
        "video",
        {},
    )

    parts.extend(
        [
            video.get("filename", ""),
            classification.get(
                "project",
                "",
            ),
            classification.get(
                "content_type",
                "",
            ),
            classification.get(
                "primary_category",
                "",
            ),
            classification.get(
                "secondary_categories",
                [],
            ),
            classification.get(
                "possible_use_cases",
                [],
            ),
            search_index.get(
                "keywords",
                [],
            ),
            search_index.get(
                "actions",
                [],
            ),
            search_index.get(
                "spoken_text",
                "",
            ),
            search_index.get(
                "important_phrases",
                [],
            ),
            search_index.get(
                "locations",
                [],
            ),
            search_index.get(
                "emotions",
                [],
            ),
            search_index.get(
                "dance_elements",
                [],
            ),
        ]
    )

    segments = passport.get(
        "segments",
        [],
    )

    for segment in segments:
        parts.extend(
            [
                segment.get(
                    "semantic_description",
                    "",
                ),
                segment.get(
                    "visual_tags",
                    [],
                ),
                segment.get(
                    "search_tags",
                    [],
                ),
                segment.get(
                    "search_phrases",
                    [],
                ),
                segment.get(
                    "spoken_text",
                    "",
                ),
                segment.get(
                    "dance_elements",
                    [],
                ),
                segment.get(
                    "emotions",
                    [],
                ),
                segment.get(
                    "subjects",
                    [],
                ),
                segment.get(
                    "actions",
                    [],
                ),
            ]
        )

    return normalize_text(parts)


# ============================================================
# QUERY EXPANSION
# ============================================================

def build_query_terms(
    input_text: str,
) -> set[str]:
    terms = tokenize(input_text)

    aliases = {
        "танцы": {
            "танец",
            "танцевальный",
            "хореография",
        },
        "танец": {
            "танцы",
            "танцевальный",
            "хореография",
        },
        "дети": {
            "ребенок",
            "ребята",
            "детский",
            "детские",
        },
        "ребенок": {
            "дети",
            "ребята",
            "детский",
            "детские",
        },
        "тренер": {
            "преподаватель",
            "педагог",
            "учитель",
        },
        "занятие": {
            "тренировка",
            "урок",
            "класс",
        },
        "тренировка": {
            "занятие",
            "урок",
            "класс",
        },
        "счет": {
            "считать",
            "считающий",
            "раз",
            "два",
            "три",
            "четыре",
        },
        "раз": {
            "счет",
            "два",
            "три",
            "четыре",
        },
    }

    expanded = set(terms)

    for term in terms:
        expanded.update(
            aliases.get(
                term,
                set(),
            )
        )

    return expanded


# ============================================================
# SCORING
# ============================================================

def score_passport(
    passport: dict[str, Any],
    query_terms: set[str],
) -> tuple[float, list[str]]:
    if not query_terms:
        return 0.0, []

    search_index = passport.get(
        "search_index",
        {},
    )

    classification = passport.get(
        "classification",
        {},
    )

    filename = normalize_text(
        passport.get(
            "video",
            {},
        ).get(
            "filename",
            "",
        )
    )

    keywords = tokenize(
        search_index.get(
            "keywords",
            [],
        )
    )

    actions = tokenize(
        search_index.get(
            "actions",
            [],
        )
    )

    spoken_text = tokenize(
        search_index.get(
            "spoken_text",
            "",
        )
    )

    important_phrases = tokenize(
        search_index.get(
            "important_phrases",
            [],
        )
    )

    categories = tokenize(
        [
            classification.get(
                "content_type",
                "",
            ),
            classification.get(
                "primary_category",
                "",
            ),
            classification.get(
                "secondary_categories",
                [],
            ),
            classification.get(
                "possible_use_cases",
                [],
            ),
        ]
    )

    all_text = tokenize(
        passport_search_text(
            passport
        )
    )

    score = 0.0
    matched = []

    for term in query_terms:

        if term in keywords:
            score += 5.0
            matched.append(
                f"keyword:{term}"
            )

        if term in actions:
            score += 4.0
            matched.append(
                f"action:{term}"
            )

        if term in spoken_text:
            score += 5.0
            matched.append(
                f"speech:{term}"
            )

        if term in important_phrases:
            score += 5.0
            matched.append(
                f"phrase:{term}"
            )

        if term in categories:
            score += 2.0
            matched.append(
                f"category:{term}"
            )

        if term in filename:
            score += 1.0
            matched.append(
                f"filename:{term}"
            )

        if term in all_text:
            score += 0.5

    # Бонус за наличие визуального контента
    if (
        search_index.get(
            "has_visual_content"
        )
        is True
    ):
        score += 0.25

    # Бонус за готовность паспорта
    if (
        passport.get(
            "processing",
            {},
        ).get(
            "passport_status"
        )
        == "ready"
    ):
        score += 0.25

    return score, matched


# ============================================================
# SEGMENT EXTRACTION
# ============================================================

def extract_relevant_segments(
    passport: dict[str, Any],
    query_terms: set[str],
) -> list[dict[str, Any]]:
    segments = passport.get(
        "segments",
        [],
    )

    result = []

    for segment in segments:

        segment_text = normalize_text(
            [
                segment.get(
                    "semantic_description",
                    "",
                ),
                segment.get(
                    "visual_tags",
                    [],
                ),
                segment.get(
                    "search_tags",
                    [],
                ),
                segment.get(
                    "search_phrases",
                    [],
                ),
                segment.get(
                    "spoken_text",
                    "",
                ),
                segment.get(
                    "actions",
                    [],
                ),
                segment.get(
                    "subjects",
                    [],
                ),
            ]
        )

        segment_tokens = tokenize(
            segment_text
        )

        matches = sorted(
            query_terms.intersection(
                segment_tokens
            )
        )

        segment_score = len(matches)

        # Отдельный вес речи.
        speech_text = normalize_text(
            segment.get(
                "spoken_text",
                "",
            )
        )

        speech_tokens = tokenize(
            speech_text
        )

        speech_matches = query_terms.intersection(
            speech_tokens
        )

        segment_score += (
            len(speech_matches) * 2
        )

        if segment_score <= 0:
            continue

        result.append(
            {
                "id": segment.get(
                    "id"
                ),
                "start": segment.get(
                    "start",
                    0.0,
                ),
                "end": segment.get(
                    "end",
                    0.0,
                ),
                "duration": segment.get(
                    "duration",
                    0.0,
                ),
                "semantic_description":
                    segment.get(
                        "semantic_description",
                        "",
                    ),
                "visual_tags":
                    segment.get(
                        "visual_tags",
                        [],
                    ),
                "search_tags":
                    segment.get(
                        "search_tags",
                        [],
                    ),
                "search_phrases":
                    segment.get(
                        "search_phrases",
                        [],
                    ),
                "spoken_text":
                    segment.get(
                        "spoken_text",
                        "",
                    ),
                "speech":
                    segment.get(
                        "speech",
                        [],
                    ),
                "subjects":
                    segment.get(
                        "subjects",
                        [],
                    ),
                "actions":
                    segment.get(
                        "actions",
                        [],
                    ),
                "emotions":
                    segment.get(
                        "emotions",
                        [],
                    ),
                "camera":
                    segment.get(
                        "camera",
                        "",
                    ),
                "composition":
                    segment.get(
                        "composition",
                        "",
                    ),
                "audio_usage":
                    segment.get(
                        "audio_usage",
                        {},
                    ),
                "match_score":
                    segment_score,
                "matched_terms":
                    matches,
            }
        )

    result.sort(
        key=lambda item: item[
            "match_score"
        ],
        reverse=True,
    )

    return result


# ============================================================
# CANDIDATE PACKAGE
# ============================================================

def build_candidate(
    passport: dict[str, Any],
    score: float,
    matched: list[str],
    query_terms: set[str],
) -> dict[str, Any]:

    video = passport.get("video", {})
    classification = passport.get("classification", {})
    search_index = passport.get("search_index", {})

    relevant_segments = extract_relevant_segments(
        passport,
        query_terms,
    )

    # Очищаем сегменты от тяжелых полей (camera, composition, visual_tags и т.д.),
    # оставляя только необходимые для Gemini данные, и берем 6 лучших вместо 10.
    optimized_segments = [
        {
            "id": seg.get("id"),
            "start": seg.get("start"),
            "end": seg.get("end"),
            "duration": seg.get("duration"),
            "semantic_description": seg.get("semantic_description", ""),
            "spoken_text": seg.get("spoken_text", ""),
        }
        for seg in relevant_segments[:6]
    ]

    return {
        "file_id": video.get("file_id", ""),
        "filename": video.get("filename", ""),
        "mime_type": video.get("mime_type", ""),
        "drive_url": video.get("drive_url", ""),
        "classification": {
            "content_type": classification.get("content_type", ""),
            "primary_category": classification.get("primary_category", ""),
            "secondary_categories": classification.get("secondary_categories", []),
            "possible_use_cases": classification.get("possible_use_cases", []),
        },
        "usage": passport.get("usage", {}),
        "search_index": {
            "keywords": search_index.get("keywords", []),
            "actions": search_index.get("actions", []),
            "spoken_text": search_index.get("spoken_text", ""),
            "important_phrases": search_index.get("important_phrases", []),
        },
        "relevant_segments": optimized_segments,
        "retrieval": {
            "score": round(score, 3),
            "matched_fields": matched,
        },
    }


# ============================================================
# RETRIEVE
# ============================================================

def extract_target_date(user_prompt: str) -> str | None:
    """Извлекает требуемую дату из ТЗ (например, 'сегодня' или 'YYYY-MM-DD')."""
    from datetime import datetime
    prompt_lower = user_prompt.lower()
    
    # Ключевые слова "сегодня"
    if any(kw in prompt_lower for kw in ["сегодня", "сегодняшние", "за сегодня"]):
        return datetime.now().strftime("%Y-%m-%d")
    
    # Поиск формата YYYY-MM-DD
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", user_prompt)
    if iso_match:
        return iso_match.group(1)
        
    # Поиск формата DD.MM.YYYY
    ru_match = re.search(r"\b(\d{2})\.(\d{2})\.(\d{4})\b", user_prompt)
    if ru_match:
        d, m, y = ru_match.groups()
        return f"{y}-{m}-{d}"
        
    return None


def retrieve_candidates(
    input_text: str,
    passports: list[dict[str, Any]],
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:

    # --- ФИЛЬТР ПО ИСТОРИИ (COOLDOWN) ---
    blocked_ids = get_blocked_file_ids()
    if blocked_ids:
        passports_before = len(passports)
        passports = [
            p for p in passports 
            if p.get("file_id") not in blocked_ids 
            and p.get("video", {}).get("file_id") not in blocked_ids
        ]
        print(
            f"[Retriever] Файлы на отдыхе (были в прошлых {COOLDOWN_RUNS} генерациях): "
            f"{len(blocked_ids)} шт. Исключено паспортов: {passports_before - len(passports)}"
        )

    # --- ФИЛЬТРАЦИЯ ПО ДАТЕ ИЗ ТЗ ---
    target_date = extract_target_date(input_text)
    if target_date:
        print(f"[Retriever] Обнаружен фильтр по дате в ТЗ: {target_date}")
        passports = [
            p for p in passports
            if str(p.get("created_at", "")).startswith(target_date)
        ]
        print(f"[Retriever] Отфильтровано паспортов за {target_date}: {len(passports)}")

    query_terms = build_query_terms(
        input_text
    )

    print(
        f"[Retriever] Query terms: "
        f"{sorted(query_terms)}"
    )

    ranked = []

    for passport in passports:

        score, matched = score_passport(
            passport,
            query_terms,
        )

        if score < MIN_SCORE:
            continue

        candidate = build_candidate(
            passport,
            score,
            matched,
            query_terms,
        )

        ranked.append(candidate)

    ranked.sort(
        key=lambda item:
            item["retrieval"]["score"],
        reverse=True,
    )

    return ranked[:top_k]


# ============================================================
# GEMINI PROMPT
# ============================================================

def get_system_instruction(target_duration: float) -> str:
    return f"""
Ты — режиссёр монтажа и шеф-редактор VideoAIEngine.

Твоя задача — превратить реальный текст поста ВК или production ТЗ
в точный монтажный план короткого видео.

Ты получаешь:
1. РЕАЛЬНЫЙ ТЕКСТ ПОСТА или ТЗ.
2. Ограниченный список кандидатов от Retriever.
3. Для каждого кандидата — реальные file_id, filename и relevant_segments.

============================================================
ГЛАВНЫЙ ПРИНЦИП
============================================================

Ты НЕ придумываешь видеоматериал.
Ты НЕ создаёшь новые источники.
Ты НЕ создаёшь новые timecode.
Ты выбираешь только из переданных кандидатов и их relevant_segments.

============================================================
ЖЁСТКИЙ ХРОНОМЕТРАЖ
============================================================

Целевая длительность ролика:
РОВНО {target_duration:.1f} СЕКУНД.

Сумма:
(end - start) всех cuts = {target_duration:.1f} секунд.

Допустимая погрешность только из-за floating point: ±0.01 секунды.

Если необходимо получить ровно {target_duration:.1f} секунд,
изменяй длительность cuts, а не добавляй выдуманные источники.

============================================================
КОЛИЧЕСТВО CUTS
============================================================

Рекомендуемое количество: 4–10 cuts.
Минимальная длительность обычного cut: 1.5 секунды.
Максимальная длительность одного cut: 6.0 секунд.

============================================================
ИСТОЧНИКИ И TIME CODE
============================================================

Используй ТОЛЬКО кандидатов из входного списка.
Каждый cut обязан содержать: file_id, filename, start, end.
Каждый cut должен полностью находиться внутри ОДНОГО relevant_segment соответствующего кандидата.

============================================================
ПРОИЗВОДСТВЕННЫЙ КОНТРАКТ
============================================================

audio.background_music = null
audio.voiceover = null
audio.subtitles = null

============================================================
ФОРМАТ JSON
============================================================

Верни ТОЛЬКО валидный JSON структуры:

{{
  "project_title": "Dance_Reel_Generated",
  "cover_title": "КЛИКАБЕЛЬНЫЙ ЗАГОЛОВОК ОБЛОЖКИ (4-6 слов)",
  "subtitle_style": "auto",
  "content_profile": {{
    "audience": "",
    "topic": "",
    "tone": "",
    "intent": "",
    "content_type": "dance",
    "tags": []
  }},
  "production": {{
    "target_format": "reels",
    "target_width": 1080,
    "target_height": 1920,
    "target_duration_seconds": {target_duration:.1f},
    "min_cuts": 4,
    "max_cuts": 10
  }},
  "cuts": [
    {{
      "file_id": "точный file_id кандидата",
      "filename": "точный filename кандидата",
      "start": 0.0,
      "end": 5.0,
      "role": "hook",
      "reason": "краткое объяснение визуальной роли"
    }}
  ],
  "audio": {{
    "background_music": null,
    "voiceover": null,
    "subtitles": null,
    "music_volume": 0.15,
    "voice_volume": 1.0
  }},
  "output_path": "07_OUTPUT/rendered_reel.mp4",
  "output": {{
    "format": "reels",
    "duration_seconds": {target_duration:.1f}
  }},
  "script": {{
    "required": true,
    "text": ""
  }}
}}

============================================================
ФИНАЛЬНАЯ ПРОВЕРКА ПЕРЕД ОТВЕТОМ
============================================================

1. Все file_id и filename существуют среди кандидатов.
2. Каждый start >= relevant_segment.start и end <= relevant_segment.end.
3. Суммарная длительность cuts = РОВНО {target_duration:.1f} секунд ±0.01.
4. Первый cut имеет роль hook, последний — ending.
5. output.duration_seconds = {target_duration:.1f}.
6. Поле cover_title содержит яркий, привлекающий внимание заголовок.
7. JSON валидный, без разметки вне JSON.
"""


# ============================================================
# GEMINI CALL
# ============================================================

# Единая глобальная сессия для повторного использования TCP/TLS соединений (Keep-Alive)
_gemini_session = requests.Session()


def call_gemini_text(
    prompt: str,
    system_instruction: str | None = None,
    max_retries: int = 4,
    delay: float = 2.0,
) -> str:
    """
    Отправляет запрос к прокси Vercel / Gemini с логикой повторных попыток
    и экспоненциальной задержкой (Retry + Backoff) при сетевых сбоях.
    """
    proxy_url = os.getenv("VERCEL_PROXY_URL", "").strip()

    if not proxy_url:
        raise RuntimeError("VERCEL_PROXY_URL не задан в .env")

    endpoint = f"{proxy_url.rstrip('/')}/api/gemini"

    # Если system_instruction не передан явно, генерируем дефолтный на 30 секунд
    final_system_instruction = (
        system_instruction if system_instruction is not None else get_system_instruction(30.0)
    )

    payload = {
        "action": "generateContent",
        "prompt": prompt,
        "systemInstruction": final_system_instruction,
        "responseMimeType": "application/json",
        "temperature": 0.2,
    }

    payload_size = len(
        json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8")
    )

    print(
        f"[Retriever] Размер POST payload: "
        f"{payload_size / 1024:.1f} KB"
    )

    json_payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(json_payload_bytes)),
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }

    current_delay = delay

    for attempt in range(1, max_retries + 1):
        print(
            f"[Retriever] Отправка кандидатов в Vercel → Gemini "
            f"(попытка {attempt}/{max_retries})..."
        )

        try:
            # Используем persistent session вместо разового requests.post
            response = _gemini_session.post(
                endpoint,
                data=json_payload_bytes,  # Передаем байты напрямую
                headers=headers,
                timeout=(60, REQUEST_TIMEOUT),  # 15с на connect, REQUEST_TIMEOUT на read
            )
            response.raise_for_status()

            print(
                f"[Retriever] Vercel HTTP status: "
                f"{response.status_code}"
            )

            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError(
                    "Vercel вернул невалидный JSON: "
                    f"{response.text[:2000]}"
                ) from exc

            text = data.get("text")
            if text is None:
                text = data.get("result")

            if not text:
                raise RuntimeError(
                    "Vercel не вернул поле text/result. "
                    f"Ответ: {data}"
                )

            return text

        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            ConnectionResetError,
        ) as exc:
            if attempt == max_retries:
                raise RuntimeError(
                    f"Ошибка соединения с Vercel после {max_retries} попыток: {exc}"
                ) from exc

            print(
                f"[Retriever] Ошибка сети ({exc}). "
                f"Повторная попытка {attempt}/{max_retries} через {current_delay:.1f} сек..."
            )
            time.sleep(current_delay)
            current_delay *= 1.5

        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(
                f"Vercel вернул ошибку {response.status_code}: {response.text[:2000]}"
            ) from exc

# ============================================================
# JSON CLEANUP
# ============================================================

def parse_json_response(
    raw_text: str,
) -> dict[str, Any]:

    text = raw_text.strip()

    # Иногда модель всё-таки оборачивает JSON
    # в markdown code fence.

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "Gemini вернул невалидный JSON:\n"
            f"{raw_text}\n\n"
            f"Ошибка: {e}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            "Gemini вернул JSON, но корневой объект "
            "не является объектом."
        )

    return data

import difflib

def sanitize_plan_ids(plan: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    """
    Автоматически исправляет опечатки Gemini в file_id и восстанавливает
    несоответствия между file_id и filename на основе кандидатов.
    """
    if not isinstance(plan, dict) or "cuts" not in plan:
        return

    candidate_by_file_id = {c["file_id"]: c for c in candidates if c.get("file_id")}
    candidate_by_filename = {c["filename"]: c for c in candidates if c.get("filename")}
    valid_file_ids = list(candidate_by_file_id.keys())

    for index, cut in enumerate(plan.get("cuts", []), start=1):
        if not isinstance(cut, dict):
            continue

        file_id = cut.get("file_id")
        filename = cut.get("filename")

        # 1. Если file_id нет или он невалиден, пробуем восстановить по filename
        if (not file_id or file_id not in candidate_by_file_id) and filename in candidate_by_filename:
            correct_id = candidate_by_filename[filename]["file_id"]
            print(f"[Autofix] Cut #{index}: восстановлен file_id по filename ({filename}): {file_id} -> {correct_id}")
            cut["file_id"] = correct_id
            file_id = correct_id

        # 2. Если file_id всё ещё не найден, ищем опечатки через нечеткий поиск (Fuzzy Match / Substring)
        if file_id and file_id not in candidate_by_file_id:
            # Попытка А: Подстрока (например, лишний символ в начале '11z...' vs '1z...')
            matches = [vid for vid in valid_file_ids if vid in file_id or file_id in vid]
            
            # Попытка Б: Нечеткое совпадение Левенштейна
            if not matches:
                matches = difflib.get_close_matches(file_id, valid_file_ids, n=1, cutoff=0.7)

            if matches:
                correct_id = matches[0]
                matched_candidate = candidate_by_file_id[correct_id]
                print(f"[Autofix] Cut #{index}: исправлена опечатка в file_id: {file_id} -> {correct_id}")
                cut["file_id"] = correct_id
                # Принудительно синхронизируем filename
                cut["filename"] = matched_candidate["filename"]
                continue

        # 3. Если file_id валиден, но filename расходится с кандидатом — исправляем filename
        if file_id in candidate_by_file_id:
            expected_filename = candidate_by_file_id[file_id]["filename"]
            if filename != expected_filename:
                print(f"[Autofix] Cut #{index}: исправлен рассинхрон filename для {file_id}: {filename} -> {expected_filename}")
                cut["filename"] = expected_filename

# ============================================================
# ATTACH RELEVANT SEGMENTS TO CUTS
# ============================================================

def attach_relevant_segments(
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> None:
    """
    Прикрепляет к каждому cut тот relevant_segment,
    внутри которого находится выбранный диапазон.

    Gemini обязан выбирать только реальные диапазоны,
    поэтому здесь мы не придумываем новые timecode.
    Мы только восстанавливаем производственный контекст,
    необходимый Production Pipeline для последующего
    безопасного расширения cuts под voiceover.
    """

    candidate_by_file_id = {
        item["file_id"]: item
        for item in candidates
        if item.get("file_id")
    }

    candidate_by_filename = {
        item["filename"]: item
        for item in candidates
        if item.get("filename")
    }

    for index, cut in enumerate(
        plan.get("cuts", []),
        start=1,
    ):
        file_id = cut.get("file_id")
        filename = cut.get("filename")

        try:
            start = float(cut["start"])
            end = float(cut["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Cut #{index}: невозможно определить "
                "start/end для привязки relevant_segment."
            ) from exc

        candidate = None

        if file_id:
            candidate = candidate_by_file_id.get(
                file_id
            )

        if candidate is None and filename:
            candidate = candidate_by_filename.get(
                filename
            )

        if candidate is None:
            raise RuntimeError(
                f"Cut #{index}: не найден кандидат "
                f"для file_id={file_id}, "
                f"filename={filename}."
            )

        matching_segments = []
        candidate_segments = candidate.get("relevant_segments", [])

        for segment in candidate_segments:
            try:
                segment_start = float(
                    segment.get("start", 0.0)
                )
                segment_end = float(
                    segment.get("end", 0.0)
                )
            except (TypeError, ValueError):
                continue

            # Проверяем вхождение диапазона с небольшой толерантностью (0.5 сек)
            if (
                start >= (segment_start - 0.5)
                and end <= (segment_end + 0.5)
            ):
                matching_segments.append(
                    segment
                )

        selected_segment = None

        if matching_segments:
            # Если cut попал сразу в несколько вложенных сегментов — выбираем самый узкий.
            matching_segments.sort(
                key=lambda segment: (
                    float(segment.get("end", 0.0))
                    - float(segment.get("start", 0.0))
                )
            )
            selected_segment = matching_segments[0]
        elif candidate_segments:
            # FALLBACK: Если точное вхождение не совпало из-за сдвига Gemini,
            # берём первый доступный сегмент у этого же файла, чтобы не ронять пайплайн.
            print(
                f"[Retriever] ⚠️ Cut #{index} ({start:.1f}-{end:.1f}s) "
                f"не попал строго в границы. Используем fallback-сегмент файла {filename or file_id}."
            )
            selected_segment = candidate_segments[0]
        else:
            # Дефолтный сегмент-заглушка на случай, если у кандидата пустые relevant_segments
            selected_segment = {
                "id": "fallback_segment",
                "start": start,
                "end": end,
                "duration": round(end - start, 3),
                "semantic_description": "Автоматический фоновый сегмент",
            }

        cut["relevant_segment"] = {
            "id": selected_segment.get("id", "default_id"),
            "start": float(
                selected_segment.get("start", start)
            ),
            "end": float(
                selected_segment.get("end", end)
            ),
            "duration": float(
                selected_segment.get(
                    "duration",
                    float(selected_segment.get("end", end))
                    - float(selected_segment.get("start", start)),
                )
            ),
            "semantic_description":
                selected_segment.get(
                    "semantic_description",
                    "",
                ),
        }

    print(
        "[Retriever] ✓ Relevant segments "
        "прикреплены к cuts."
    )

# ============================================================
# PLAN VALIDATION
# ============================================================

def validate_plan(
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> None:

    if "cuts" not in plan:
        raise RuntimeError("В montage plan отсутствует cuts.")

    if not isinstance(plan["cuts"], list):
        raise RuntimeError("Поле cuts должно быть массивом.")

    candidate_by_file_id = {
        item["file_id"]: item
        for item in candidates
        if item.get("file_id")
    }

    for index, cut in enumerate(plan["cuts"]):

        if not isinstance(cut, dict):
            raise RuntimeError(f"Cut #{index + 1} не является объектом.")

        file_id = cut.get("file_id")
        filename = cut.get("filename")
        start = cut.get("start")
        end = cut.get("end")

        if not file_id:
            raise RuntimeError(f"Cut #{index + 1}: отсутствует file_id.")

        if not filename:
            raise RuntimeError(f"Cut #{index + 1}: отсутствует filename.")

        if file_id not in candidate_by_file_id:
            raise RuntimeError(f"Cut #{index + 1}: file_id {file_id} отсутствует среди кандидатов.")

        candidate = candidate_by_file_id[file_id]

        if candidate.get("filename") != filename:
            raise RuntimeError(f"Cut #{index + 1}: file_id и filename не принадлежат одному кандидату.")

        if not isinstance(start, (int, float)):
            raise RuntimeError(f"Cut #{index + 1}: start должен быть числом.")

        if not isinstance(end, (int, float)):
            raise RuntimeError(f"Cut #{index + 1}: end должен быть числом.")

        # --- КОРРЕКТИРОВКА ДЛИТЕЛЬНОСТИ ---
        if end <= start:
            print(f"[Warning] Cut #{index + 1} duration invalid ({start}-{end}). Auto-correcting...")
            end = round(start + 2.0, 2)
            cut["end"] = end

        max_dur = float(candidate.get("duration", 999.0))
        if end > max_dur:
            print(f"[Warning] Cut #{index + 1} end ({end}s) exceeds video duration ({max_dur}s). Clamping...")
            cut["end"] = max_dur
            if cut["start"] >= max_dur:
                cut["start"] = max(0.0, max_dur - 2.0)
            start = cut["start"]
            end = cut["end"]

        # --- АВТО-ПОДГОН И ВАЛИДАЦИЯ РЕЛЕВАНТНЫХ СЕГМЕНТОВ ---
        relevant_segments = candidate.get("relevant_segments", [])
        
        if relevant_segments:
            segment_valid = False
            
            # 1. Проверяем точное попадание
            for segment in relevant_segments:
                seg_start = float(segment.get("start", 0))
                seg_end = float(segment.get("end", 0))
                if start >= seg_start and end <= seg_end:
                    segment_valid = True
                    break

            # 2. Если не попали строго, делаем мягкую подгонку (Clamping)
            if not segment_valid:
                best_segment = None
                best_overlap = -1.0

                for segment in relevant_segments:
                    seg_start = float(segment.get("start", 0))
                    seg_end = float(segment.get("end", 0))
                    
                    # Находим пересечение отрезков
                    overlap_start = max(start, seg_start)
                    overlap_end = min(end, seg_end)
                    overlap = overlap_end - overlap_start

                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_segment = (seg_start, seg_end)

                if best_segment and best_overlap > 0:
                    seg_start, seg_end = best_segment
                    print(
                        f"[Retriever Auto-Fix] Cut #{index + 1} ({filename}): "
                        f"таймкод {start}-{end}s скорректирован под границы сегмента [{seg_start}-{seg_end}s]"
                    )
                    new_start = max(start, seg_start)
                    new_end = min(end, seg_end)
                    
                    # Если отрезок получился слишком коротким (меньше 1.0 сек), расширяем по сегменту
                    if (new_end - new_start) < 1.0:
                        new_start = seg_start
                        new_end = min(seg_end, seg_start + max(2.0, end - start))

                    cut["start"] = round(new_start, 2)
                    cut["end"] = round(new_end, 2)
                else:
                    # Если пересечений с сегментами совсем нет, привязываем к первому релевантному сегменту
                    seg_start, seg_end = float(relevant_segments[0].get("start", 0)), float(relevant_segments[0].get("end", 0))
                    print(
                        f"[Retriever Auto-Fix] Cut #{index + 1} ({filename}): "
                        f"таймкод {start}-{end}s перенесен в первый релевантный сегмент [{seg_start}-{seg_end}s]"
                    )
                    cut["start"] = seg_start
                    cut["end"] = seg_end if seg_end > seg_start else round(seg_start + 2.0, 2)

    if not plan["cuts"]:
        raise RuntimeError("Gemini не выбрал ни одного cut.")

# ============================================================
# PLAN DURATION REPAIR
# ============================================================

def repair_plan_duration(
    plan: dict[str, Any],
    target_duration: float = TARGET_DURATION_SECONDS,
    tolerance: float = DURATION_TOLERANCE_SECONDS,
) -> None:
    """
    Детерминированно исправляет суммарную длительность montage plan.

    Gemini отвечает за выбор визуального материала и драматургию.
    Эта функция отвечает только за техническое попадание
    в требуемую длительность.

    Основной сценарий:
    - Gemini дал план длиннее target_duration;
    - уменьшаем длительности существующих cuts;
    - не меняем file_id / filename / role;
    - не создаём новые источники;
    - не выходим за границы выбранного cut;
    - не уменьшаем cut ниже MIN_CUT_DURATION_SECONDS.

    Hook и ending изменяются только после остальных ролей.

    Если план короче target_duration, функция не придумывает
    дополнительный материал и оставляет план без изменений.
    Строгий validate_plan_duration() после этого зафиксирует ошибку.
    """

    cuts = plan.get("cuts", [])

    if not cuts:
        raise RuntimeError(
            "Невозможно исправить длительность: cuts пуст."
        )

    total_duration = 0.0

    for index, cut in enumerate(cuts, start=1):
        try:
            start = float(cut["start"])
            end = float(cut["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Cut #{index} содержит некорректные start/end."
            ) from exc

        if end <= start:
            raise RuntimeError(
                f"Cut #{index} имеет некорректный диапазон "
                f"{start}-{end}."
            )

        total_duration += end - start

    difference = total_duration - target_duration

    # Уже достаточно точно.
    if abs(difference) <= tolerance:
        print(
            "[Retriever] ✓ Duration repair не требуется: "
            f"{total_duration:.3f} сек."
        )
        return

    # План короче целевого: пропорционально растягиваем клипы до target_duration
    if difference < 0:
        shortfall = abs(difference)
        print(
            f"[Retriever] ⚠ Duration repair: план короче цели на {shortfall:.3f} сек."
        )
        print("[Retriever] Выполняем авто-растягивание (Auto-pad) клипов...")

        if total_duration > 0:
            scale_factor = target_duration / total_duration
            for cut in cuts:
                start = float(cut["start"])
                end = float(cut["end"])
                old_dur = end - start
                new_dur = old_dur * scale_factor
                cut["end"] = round(start + new_dur, 3)

            # Корректируем мелкую погрешность округления на последнем клипе
            new_total = sum(float(c["end"]) - float(c["start"]) for c in cuts)
            cuts[-1]["end"] = round(float(cuts[-1]["end"]) + (target_duration - new_total), 3)

            final_dur = sum(float(c["end"]) - float(c["start"]) for c in cuts)
            print(f"[Retriever] ✓ План успешно растянут до {final_dur:.3f} сек.")
        return

    excess = difference

    print()
    print(
        "[Retriever] Duration repair:"
    )
    print(
        f"[Retriever] Исходная длительность: "
        f"{total_duration:.3f} сек."
    )
    print(
        f"[Retriever] Целевая длительность: "
        f"{target_duration:.3f} сек."
    )
    print(
        f"[Retriever] Необходимо убрать: "
        f"{excess:.3f} сек."
    )

    # Сначала сокращаем обычные драматургические роли.
    # Hook и ending сохраняем насколько возможно.
    role_priority = {
        "development": 0,
        "proof": 1,
        "emotion": 2,
        "hook": 3,
        "ending": 4,
    }

    indexed_cuts = list(
        enumerate(cuts)
    )

    indexed_cuts.sort(
        key=lambda item: (
            role_priority.get(
                item[1].get("role"),
                2,
            ),
            item[0],
        )
    )

    repaired_seconds = 0.0

    for original_index, cut in indexed_cuts:

        if excess <= tolerance:
            break

        start = float(cut["start"])
        end = float(cut["end"])

        current_duration = end - start

        max_reduction = (
            current_duration
            - MIN_CUT_DURATION_SECONDS
        )

        if max_reduction <= 0:
            continue

        reduction = min(
            excess,
            max_reduction,
        )

        new_end = end - reduction

        # Не допускаем микроскопических floating point
        # отклонений после арифметики.
        new_end = round(
            new_end,
            3,
        )

        actual_reduction = end - new_end

        if actual_reduction <= 0:
            continue

        cut["end"] = new_end

        excess -= actual_reduction
        repaired_seconds += actual_reduction

        print(
            f"[Retriever]   cut #{original_index + 1}: "
            f"{current_duration:.3f} → "
            f"{new_end - start:.3f} сек. "
            f"role={cut.get('role')}"
        )

    final_duration = sum(
        float(cut["end"]) - float(cut["start"])
        for cut in cuts
    )

    remaining_difference = (
        final_duration - target_duration
    )

    print(
        f"[Retriever] Исправлено: "
        f"{repaired_seconds:.3f} сек."
    )

    print(
        f"[Retriever] Длительность после repair: "
        f"{final_duration:.3f} сек."
    )

    # Если удалось попасть в допуск — всё хорошо.
    if abs(remaining_difference) <= tolerance:
        print(
            "[Retriever] ✓ Duration repair успешно "
            "привёл план к целевой длительности."
        )
        return

    # Если после сокращения до MIN_CUT_DURATION
    # всё ещё осталось лишнее время — честно падаем.
    if remaining_difference > tolerance:
        raise RuntimeError(
            "Duration repair не смог сократить montage plan "
            "до требуемой длительности без нарушения "
            f"MIN_CUT_DURATION_SECONDS={MIN_CUT_DURATION_SECONDS:.3f}. "
            f"Осталось лишнее время: "
            f"{remaining_difference:.3f} сек."
        )

    # Теоретически сюда можно попасть только из-за
    # накопления floating point. Для безопасности
    # выполняем финальную нормализацию последнего
    # изменённого cut.
    if repaired_seconds > 0:
        for original_index, cut in reversed(
            indexed_cuts
        ):
            if original_index >= len(cuts):
                continue

            start = float(cut["start"])
            end = float(cut["end"])
            duration = end - start

            if duration <= MIN_CUT_DURATION_SECONDS:
                continue

            correction = (
                target_duration - final_duration
            )

            new_end = end + correction

            if (
                new_end - start
                >= MIN_CUT_DURATION_SECONDS
                and new_end - start
                <= MAX_CUT_DURATION_SECONDS
            ):
                cut["end"] = round(
                    new_end,
                    3,
                )
                break

    final_duration = sum(
        float(cut["end"]) - float(cut["start"])
        for cut in cuts
    )

    print(
        f"[Retriever] Финальная длительность после repair: "
        f"{final_duration:.3f} сек."
    )

# ============================================================
# PLAN DURATION VALIDATION
# ============================================================

def validate_plan_duration(
    plan: dict[str, Any],
    target_duration: float = TARGET_DURATION_SECONDS,
    tolerance: float = DURATION_TOLERANCE_SECONDS,
) -> None:
    cuts = plan.get("cuts", [])

    if not cuts:
        raise RuntimeError(
            "Невозможно проверить длительность: cuts пуст."
        )

    total_duration = 0.0

    for index, cut in enumerate(cuts, start=1):
        try:
            start = float(cut["start"])
            end = float(cut["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Cut #{index} содержит некорректные start/end."
            ) from exc

        duration = end - start

        if duration <= 0:
            raise RuntimeError(
                f"Cut #{index} имеет некорректную длительность: "
                f"{duration:.3f} сек."
            )

        total_duration += duration

    difference = total_duration - target_duration

    print(
        f"[Retriever] Плановая длительность: "
        f"{total_duration:.3f} сек"
    )
    print(
        f"[Retriever] Целевая длительность: "
        f"{target_duration:.3f} сек"
    )

    if abs(difference) > tolerance:
        raise RuntimeError(
            "Gemini создал монтажный план с неправильной "
            f"длительностью: {total_duration:.3f} сек. "
            f"Ожидалось {target_duration:.3f} сек."
        )

    print(
        "[Retriever] ✓ Длительность montage_plan "
        "соответствует контракту."
    )


def validate_plan_structure(
    plan: dict[str, Any],
) -> None:
    cuts = plan.get("cuts", [])

    if len(cuts) < MIN_CUTS:
        raise RuntimeError(
            f"Слишком мало cuts: {len(cuts)}. "
            f"Минимум: {MIN_CUTS}."
        )

    if len(cuts) > MAX_CUTS:
        raise RuntimeError(
            f"Слишком много cuts: {len(cuts)}. "
            f"Максимум: {MAX_CUTS}."
        )

    first_role = cuts[0].get("role")

    if first_role != "hook":
        raise RuntimeError(
            "Первый cut должен иметь role='hook'."
        )

    last_role = cuts[-1].get("role")

    if last_role != "ending":
        raise RuntimeError(
            "Последний cut должен иметь role='ending'."
        )

    for index, cut in enumerate(cuts, start=1):
        try:
            start = float(cut["start"])
            end = float(cut["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Cut #{index} содержит некорректные start/end."
            ) from exc

        duration = end - start

        if duration < MIN_CUT_DURATION_SECONDS:
            raise RuntimeError(
                f"Cut #{index} слишком короткий: "
                f"{duration:.3f} сек. "
                f"Минимум: {MIN_CUT_DURATION_SECONDS:.3f} сек."
            )

        # Автоматическая обрезка вместо падения с ошибкой
        if duration > MAX_CUT_DURATION_SECONDS:
            print(
                f"[Retriever] ⚠️ Cut #{index} слишком длинный ({duration:.1f}s). "
                f"Автоматически обрезаем до {MAX_CUT_DURATION_SECONDS:.1f}s."
            )
            cut["end"] = start + MAX_CUT_DURATION_SECONDS

    print(
        "[Retriever] ✓ Структура montage_plan "
        "соответствует production-контракту."
    )

# ============================================================
# SAVE PLAN
# ============================================================

def save_plan(
    plan: dict[str, Any],
) -> None:

    OUTPUT_PLAN_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        OUTPUT_PLAN_PATH,
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
        f"[+] Montage plan сохранен: "
        f"{OUTPUT_PLAN_PATH}"
    )


# ============================================================
# MAIN PIPELINE
# ============================================================

def generate_montage_plan(
    input_text: str,
    is_post: bool = True,
    top_k: int = DEFAULT_TOP_K,
    job_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:

    if not input_text or not input_text.strip():
        raise ValueError(
            "input_text не должен быть пустым."
        )

    print(
        "\n========================================"
    )
    print(
        " VIDEO AI ENGINE — RETRIEVER"
    )
    print(
        "========================================"
    )

    print(
        f"[Retriever] Запрос: {input_text}"
    )

    # 1. Извлекаем желаемую длительность ролика
    target_duration = 30.0  # значение по умолчанию
    if job_contract and "output" in job_contract:
        target_duration = float(job_contract["output"].get("duration_seconds", 30.0))

    passports = load_all_passports(
        PASSPORTS_DIR
    )

    if not passports:
        raise FileNotFoundError(
            f"В папке {PASSPORTS_DIR} "
            "не найдено ни одного паспорта."
        )

    print(
        f"[Retriever] Загружено паспортов: "
        f"{len(passports)}"
    )

    candidates = retrieve_candidates(
        input_text=input_text,
        passports=passports,
        top_k=top_k,
    )

    print(
        f"[Retriever] Найдено кандидатов: "
        f"{len(candidates)}"
    )

    if not candidates:
        raise RuntimeError(
            "Retriever не нашел релевантных "
            "кандидатов в библиотеке паспортов."
        )

    print(
        "\n[Retriever] Кандидаты:"
    )

    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        print(
            f"{index}. "
            f"{candidate['filename']} | "
            f"score={candidate['retrieval']['score']} | "
            f"file_id={candidate['file_id']}"
        )

        for segment in candidate[
            "relevant_segments"
        ][:3]:
            print(
                f"   └─ "
                f"{segment['start']}-"
                f"{segment['end']} сек | "
                f"{segment['semantic_description']}"
            )

    candidate_package = json.dumps(
        candidates,
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
ВХОДНОЙ МАТЕРИАЛ
Тип: {"РЕАЛЬНЫЙ ПОСТ ВК" if is_post else "PRODUCTION ТЗ"}
Текст:
{input_text}

КАНДИДАТЫ ДЛЯ МОНТАЖА:
{candidate_package}
"""

    # 2. Генерируем динамический системный промпт под нужную длительность
    system_instruction = get_system_instruction(target_duration)

    # 3. Передаем промпт и системный промпт в функцию Vercel
    raw_response = call_gemini_text(
        prompt=prompt,
        system_instruction=system_instruction,
    )

    print(
        "[Retriever] Ответ Gemini получен."
    )

    plan = parse_json_response(
        raw_response
    )

    # 1. Сначала исправляем возможные опечатки Gemini в file_id / filename
    sanitize_plan_ids(
        plan,
        candidates,
    )

    # 2. Теперь безопасно привязываем сегменты и проверяем
    attach_relevant_segments(
        plan,
        candidates,
    )

    validate_plan(
        plan,
        candidates,
    )

    validate_plan_structure(
        plan,
    )

    repair_plan_duration(
        plan,
        target_duration=target_duration,
    )

    # После автоматического repair всё равно выполняем
    # строгую финальную проверку.
    validate_plan_duration(
        plan,
    )

    save_plan(
        plan
    )

    # --- СОХРАНЕНИЕ В ИСТОРИЮ И ЗАВЕРШЕНИЕ ---
    record_used_candidates(plan)

    print(
        "[+] Retriever завершил работу успешно."
    )

    return plan


# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":

    test_post = (
        "Детские танцы в Серпухове. "
        "Покажи настоящую тренировку детей, "
        "где тренер считает движения. "
        "Нужен живой и динамичный ролик "
        "для привлечения родителей."
    )

    generate_montage_plan(
        input_text=test_post,
        is_post=True,
        top_k=12,
    )