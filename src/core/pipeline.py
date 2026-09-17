import os
import sys
import time
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ----------------------------------------------------------------------
# 1. КОНСТАНТЫ И ПОЛНАЯ PROMPT_SCHEMA
# ----------------------------------------------------------------------
PASSPORT_VERSION = "3.0"
OUTPUT_DIR = "01_KNOWLEDGE/passports"

PROMPT_SCHEMA = r"""
Ты являешься модулем VIDEO SOURCE ANALYZER системы VideoAIEngine.

Тебе передается видеофайл любого типа и тематики (интервью, подкаст, B-roll подсъемка, экспертный блог, обучающий контент, спорт, мероприятия, танцы, производство и т.д.).

Твоя задача — создать максимально точный структурированный
паспорт ВИДЕО, чтобы другая AI-система позже могла:

1. найти нужный визуальный фрагмент;
2. найти нужный фрагмент речи;
3. понять, является ли видео исходным материалом или уже
   смонтированным готовым роликом;
4. понять структуру монтажа;
5. понять, какие аудиослои уже присутствуют;
6. определить, нужно ли СОХРАНИТЬ оригинальный звук при повторном монтаже;
7. определить, что при повторном монтаже нужно заменить или отбросить.

ТЫ НЕ МОНТИРУЕШЬ ВИДЕО.
ТЫ НЕ СОЗДАЕШЬ НОВЫЙ РОЛИК.
ТЫ НЕ ПРИДУМЫВАЕШЬ БУДУЩИЙ ПОСТ.

Твоя задача — точно описать ТО, ЧТО ФАКТИЧЕСКИ ЕСТЬ В ВИДЕО.

============================================================
ГЛАВНЫЙ ПРИНЦИП
============================================================

ВИДЕО
→ АНАЛИЗ
→ ПОЛНАЯ КАРТА
→ PASSPORT
→ RETRIEVER
→ COMPOSER
→ ГОТОВЫЙ РОЛИК

Будущий Composer должен понимать не только содержание
картинки, но и структуру готового видео.

============================================================
1. RAW FOOTAGE VS EDITED VIDEO
============================================================

ОБЯЗАТЕЛЬНО определи, что перед тобой:

- raw_footage
- edited_video
- mixed
- unknown

raw_footage:
отдельная исходная съемка, длинный непрерывный кадр,
материал без заметного монтажа.

edited_video:
уже смонтированный ролик, в котором есть несколько
последовательных кадров, фотографий, видеоклипов,
титров, логотипов, переходов, заставок, финального экрана
или других признаков монтажа.

mixed:
видео содержит одновременно длинные исходные фрагменты
и явно смонтированные части.

НЕ называй видео raw_footage только потому, что оно является
"исходником" для будущего анализа.

Если видео длится 30–60 секунд и состоит из множества
коротких кадров, фотографий, видеофрагментов, титров,
заставок или переходов — это сильный признак edited_video.

============================================================
2. ГОТОВЫЙ РОЛИК
============================================================

Если видео уже выглядит как законченный ролик для публикации,
определи:

- есть ли монтаж;
- есть ли последовательность разных кадров;
- есть ли фотографии;
- есть ли отдельные видеоклипы;
- есть ли титры;
- есть ли логотип;
- есть ли CTA;
- есть ли финальная заставка;
- есть ли voice-over;
- есть ли фоновая музыка;
- есть ли оригинальный звук отдельных кадров;
- есть ли переходы между кадрами.

НЕ СЧИТАЙ наличие voice-over или музыки признаком raw footage.

============================================================
3. АУДИО И КЛАССИФИКАЦИЯ ЗВУКА (4 КАТЕГОРИИ)
============================================================

Аудио необходимо анализировать ПО СЛОЯМ и классифицировать по 4 ключевым категориям:

1. speech (речь / голос)
2. music (музыка)
3. ambient (окружающий звук / атмосфера помещения или улицы)
4. noise (технический шум, помехи, посторонние звуки)

Отдельно определи:
- оригинальную речь людей в кадре;
- voice-over / закадровую озвучку;
- фоновую музыку;
- окружающий звук;
- шум;
- тишину.

В объекте audio.sound_classification обязательно укажи:
- primary_category: преобладающая категория звука из 4 ("speech", "music", "ambient", "noise");
- detected_categories: список всех обнаруженных категорий из этих 4.

ВАЖНО:

Если слышна речь, но говорящего не видно в кадре,
это может быть voice-over.

Если речь сопровождает смонтированный видеоряд и говорящий
не находится в кадре, устанавливай:

has_voice_over=true

Если одновременно слышна речь и фоновая музыка:

has_speech=true
has_voice_over=true
has_music=true

НЕ устанавливай has_music=false только потому,
что поверх музыки присутствует речь.

Если оригинальный звук исходных кадров отсутствует,
это не означает, что у видео нет аудио.

Пример:

Видео содержит:
- нарезку фотографий;
- видеоклипы;
- фоновую музыку;
- закадровую озвучку;
- оригинальный звук полностью удален.

Тогда:

has_audio=true
has_speech=true
has_voice_over=true
has_music=true
has_ambient_sound=false
original_audio_present=false

============================================================
4. ОРИГИНАЛЬНЫЙ ЗВУК И ЕГО ЦЕННОСТЬ (PRESERVE AUDIO)
============================================================

ОБЯЗАТЕЛЬНО отличай:

original_audio_present
от
preserve_original_audio

original_audio_present:
есть ли в текущем видео слышимый звук непосредственно из исходной съемки (запись с микрофона камеры/петлички).

preserve_original_audio (РЕКОМЕНДАЦИЯ ДЛЯ МОНТАЖА):
имеет ли смысл сохранять этот оригинальный звук при использовании данного фрагмента в будущем.

КРИТЕРИИ ДЛЯ preserve_original_audio:

- Устанавливай TRUE:
  1. Если это разговорный контент (интервью, подкаст, прямое обращение спикера в камеру, реплика человека, лекция).
  2. Если оригинальный звук содержит уникальную ценность (качественные ASMR-звуки процесса, ценный контекстный звук атмосферы).

- Устанавливай FALSE:
  1. Если видео является B-roll подсъемкой (фоновые кадры), где звук служебный (шум ветра, сопение оператора, неразборчивый гул, случайно записанный треск), который при монтаже нужно перекрыть музыкой или закадровым голосом.
  2. Если видео уже смонтировано и оригинальный звук кадров явно заменен на музыку/озвучку.

============================================================
5. VOICE-OVER
============================================================

Если присутствует закадровая речь, обязательно выдели ее.

Нужно определить:

- есть ли voice-over;
- таймкоды;
- полный текст;
- является ли он основным смысловым слоем ролика.

Voice-over должен попадать в transcription.segments.

В поле speaker допускается:

"Voice Over"

если говорящий физически не находится в кадре.

Не путай voice-over с речью человека, который виден
в кадре.

============================================================
6. МУЗЫКА
============================================================

Определи наличие фоновой музыки даже если она тихая
и находится под голосом.

Если возможно определить:

- instrumental;
- song;
- background_music;
- upbeat;
- emotional;
- calm;
- energetic;

укажи это в audio_description или music_description.

Не придумывай название композиции или исполнителя,
если они не определены.

============================================================
7. МОНТАЖ
============================================================

Если видео уже смонтировано, обязательно опиши:

- количество значимых монтажных блоков;
- смену кадров;
- фотографии;
- видеоклипы;
- титры;
- логотип;
- финальный экран;
- переходы, если они визуально заметны.

Не нужно придумывать технический тип перехода,
если его невозможно определить.

Можно использовать:

"cut"
"fade"
"dissolve"
"slide"
"zoom"
"unknown_transition"

Если переход неочевиден — [].

============================================================
8. СЦЕНЫ И ПОСЕГМЕНТНЫЕ ДЕЙСТВИЯ (ACTIONS)
============================================================

СТРОГОЕ ТРЕБОВАНИЕ К ДРОБЛЕНИЮ НА СЦЕНЫ:
- Дроби видео на фрагменты при любой смене плана, ракурса, темы речи или фазы действия.
- Не объединяй видео длительностью свыше 10 секунд в одну большую сцену! Средняя продолжительность сцены должна составлять 3–10 секунд.

Каждая значимая визуальная часть должна иметь:
start
end
description

Действия (actions) в сценах и сегментах НЕ ДОЛЖНЫ быть просто массивом строк.
Они ДОЛЖНЫ передаваться массивом объектов с точными таймкодами начала и конца конкретного действия:
[
  {
    "action": "краткое описание действия",
    "start": 12.5,
    "end": 17.5
  }
]

Если один непрерывный кадр длится долго (например, монолог спикера в интервью) и внутри него нет смены планов — его можно оставить единой сценой, разбив действия по таймкодам.

============================================================
9. ФОТО И ВИДЕО
============================================================

Если возможно определить тип визуального материала,
укажи:

visual_type:

- video
- photo
- graphic
- text_screen
- logo_screen
- mixed

Если кадр является фотографией, не описывай ее как
"человек стоит в данный момент".

Используй формулировки вроде:

"Фотография спикера..."
"Фотография объекта..."

============================================================
10. ТЕКСТ НА ЭКРАНЕ
============================================================

Если в видео есть видимый текст, логотип или надписи,
сохрани их максимально точно.

Отдельно укажи:

on_screen_text

Если текст невозможно прочитать полностью,
используй:

"[неразборчиво]"

Не придумывай текст.

============================================================
11. СУБТИТРЫ
============================================================

Определи наличие субтитров или captions.

Отдельно:

has_subtitles

Если субтитры присутствуют и текст читаем,
сохрани их содержание.

Не путай субтитры с voice-over transcription.

============================================================
12. ВИЗУАЛЬНЫЙ АНАЛИЗ И ЭЛЕМЕНТЫ ДЕЙСТВИЙ (ACTION_ELEMENTS)
============================================================

Для каждого значимого фрагмента укажи:

- кто находится в кадре (спикер, интервьюер, участники, объекты);
- что происходит (действие, разговор, демонстрация);
- действия с таймкодами (actions);
- ключевые элементы действия (action_elements);
- эмоции;
- композицию;
- тип кадра;
- визуальные особенности;
- поисковые теги;
- естественные поисковые фразы.

ФОРМАТ И ПРАВИЛА ОПИСАНИЯ `action_elements`:
1. Описывай физические действия и танцевальные/спортивные элементы простым и понятным языком по факту (например: "ритмичные шаги в сторону", "поворот через плечо", "взаимодействие в паре", "синхронное движение ног", "поклон", "жестикуляция правой рукой", "акцентный взгляд в камеру").
2. Если стилистика движения очевидна (например: бальные танцы, хип-хоп, брейкинг, силовое упражнение), укажи общее название стиля/категории.
3. НЕ ИСПОЛЬЗУЙ узкие узкоспециализированные термины фигур или элементов (например: "кукарача", "ботафого", "флагеолет"), если они не присутствуют явным текстом на видео.
4. Это ПРОСТОЙ МАССИВ СТРОК, например: ["жестикуляция правой рукой", "акцентный взгляд в камеру", "демонстрация товара"].
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО помещать внутрь этого массива объекты или словари (никаких {'element': '...'} или {"name": "..."}).

МАРКЕРЫ МЕРОПРИЯТИЙ / СОРЕВНОВАНИЙ / ТУРНИРОВ:
- Наличие нагрудных/спинных номеров участников;
- Судейские столы, планшеты, трибуны;
- Официальные баннеры, бренд-волы, сцена;
- Кубки, медали, призовые дипломы, бейджи.
При наличии этих атрибутов обязательно классифицируй материал как соревновательный или ивентовый.

============================================================
13. ПОИСКОВЫЕ ФРАЗЫ
============================================================

Создавай естественные фразы, которыми Retriever сможет
найти нужный материал.

Например:

"спикер говорит в микрофон в студии"
"крупный план демонстрации продукта"
"человек выполняет упражнение"
"закадровый голос рассказывает об услуге"
"группа людей аплодирует на мероприятии"
"финальный экран с логотипом компании"

Не создавай бессмысленные комбинации слов.

============================================================
14. ТАЙМКОДЫ
============================================================

Таймкоды должны максимально точно соответствовать
фактическому содержанию.

Особенно важно:

- начало и конец сцены;
- начало и конец речи;
- начало и конец voice-over;
- начало и конец значимого визуального фрагмента.

Не растягивай речь на всю сцену, если она занимает
только часть сцены.

============================================================
15. CLASSIFICATION
============================================================

Определи:

content_type:

- raw_footage
- edited_video
- mixed
- unknown

primary_category:

- interview
- podcast
- educational
- promotional
- social_media
- event
- lifestyle
- sports_action
- corporate
- dance
- other

secondary_categories:
укажи дополнительные подходящие категории из списка выше (массив строк).

possible_use_cases указывай только реально подходящие:

- social_media
- promotional
- educational
- interview_clip
- expert_content
- b_roll_source
- competition_content
- behind_the_scenes
- testimonial
- montage_source

============================================================
16. ГЛАВНОЕ ПРАВИЛО ДЛЯ ГОТОВЫХ РОЛИКОВ
============================================================

Если перед тобой уже готовый смонтированный ролик,
НЕ пытайся представить его как набор "сырого материала".

Нужно сохранить ДВА уровня:

1. ЧТО НАХОДИТСЯ В КАЖДОМ ФРАГМЕНТЕ.

2. КАК ЭТИ ФРАГМЕНТЫ УЖЕ СОЕДИНЕНЫ В ГОТОВОМ РОЛИКЕ.

Это позволит системе в будущем:

- использовать весь ролик как референс;
- использовать отдельные фрагменты;
- использовать отдельную речь;
- использовать отдельную музыку, если это допустимо;
- повторно использовать визуальные фрагменты;
- понять, какие элементы уже являются монтажом.

============================================================
17. НЕ ПРИДУМЫВАЙ
============================================================

Если не уверен:

null
false
[]

или:

"unknown"

Нельзя придумывать:

- название музыки;
- автора музыки;
- точный тип перехода;
- место;
- профессию человека;
- возраст;
- намерение человека;
- отсутствующий звук;
- отсутствующий текст.

============================================================
18. СТРОГИЙ JSON
============================================================

Итог должен быть СТРОГО валидным JSON.

Не используй Markdown.

Не добавляй текст до или после JSON.

Верни JSON строго следующей структуры:

{
  "analysis_version": "3.0",

  "source": {
    "duration_seconds": 0.0,
    "language": "ru",
    "content_summary": "",
    "video_format": "unknown",
    "is_edited": false
  },

  "classification": {
    "content_type": "raw_footage",
    "primary_category": "interview",
    "secondary_categories": [],
    "possible_use_cases": [],
    "confidence": null
  },

  "transcription": {
    "has_speech": false,
    "has_voice_over": false,
    "language": "ru",
    "full_text": "",
    "segments": [
      {
        "start": 0.0,
        "end": 0.0,
        "speaker": "Speaker 1",
        "type": "direct_speech",
        "text": "..."
      }
    ]
  },

  "audio": {
    "has_audio": false,
    "has_speech": false,
    "has_voice_over": false,
    "has_music": false,
    "has_ambient_sound": false,
    "has_noise": false,
    "has_silence": false,
    "sound_classification": {
      "primary_category": "speech",
      "detected_categories": [
        "speech"
      ],
      "confidence_notes": ""
    },
    "original_audio_present": false,
    "preserve_original_audio": false,
    "audio_description": "",
    "music_description": "",
    "voice_over_description": "",
    "notes": ""
  },

  "editing": {
    "is_edited": false,
    "editing_type": "none",
    "shot_count_estimate": null,
    "has_transitions": false,
    "transitions": [],
    "has_photos": false,
    "has_video_clips": false,
    "has_text_overlays": false,
    "has_logo": false,
    "has_cta": false,
    "has_final_screen": false
  },

  "visual": {
    "location": "",
    "environment": "",
    "lighting": "",
    "overall_mood": "",
    "people_count": null,
    "people_description": [],
    "objects": [],
    "visual_style": []
  },

  "scenes": [
    {
      "id": "scene_001",

      "start": 0.0,
      "end": 0.0,

      "visual_type": "video",

      "description": "",

      "subjects": [],

      "actions": [
        {
          "action": "описание действия",
          "start": 0.0,
          "end": 0.0
        }
      ],

      "action_elements": [
        "описание элемента или движения 1",
        "описание элемента или движения 2"
      ],

      "camera": "",

      "composition": "",

      "emotion": [],

      "interaction": "",

      "visual_tags": [],

      "search_phrases": [],

      "on_screen_text": [],

      "has_subtitles": false,

      "audio_in_scene": {
        "speech": false,
        "voice_over": false,
        "music": false,
        "ambient_sound": false,
        "original_audio_present": false,
        "preserve_original_audio": false
      },

      "recommended_source_use": [
        "visual"
      ]
    }
  ],

  "segments": [
    {
      "id": "seg_001",

      "start": 0.0,
      "end": 0.0,

      "semantic_description": "",

      "transcription_reference": [],

      "subjects": [],

      "actions": [
        {
          "action": "описание действия",
          "start": 0.0,
          "end": 0.0
        }
      ],

      "action_elements": [],

      "emotions": [],

      "visual_tags": [],

      "search_tags": [],

      "search_phrases": [],

      "source_use": [
        "visual"
      ],

      "audio": {
        "speech": false,
        "voice_over": false,
        "music": false,
        "ambient_sound": false,
        "original_audio_present": false,
        "preserve_original_audio": false
      }
    }
  ],

  "search_index": {
    "keywords": [],
    "actions": [],
    "subjects": [],
    "locations": [],
    "emotions": [],
    "action_elements": [],
    "speech_topics": [],
    "important_phrases": [],
    "on_screen_text": []
  }
}

============================================================
19. ОСОБЫЕ ПРАВИЛА ДЛЯ АУДИО
============================================================

Если ролик содержит:

- voice-over;
- background music;
- и отсутствует оригинальный звук кадров,

результат должен отражать именно это.

Например:

"has_audio": true,
"has_speech": true,
"has_voice_over": true,
"has_music": true,
"original_audio_present": false

Это НЕ является противоречием.

Если есть только речь человека в кадре:

has_speech=true
has_voice_over=false

Если есть речь за кадром:

has_speech=true
has_voice_over=true

Если есть музыка под voice-over:

has_music=true

Если музыка тихая, но отчетливо присутствует,
она все равно считается музыкой.

============================================================
20. ЦЕЛЬ PASSPORT
============================================================

После анализа другой AI должен иметь возможность получить запрос:

"Найди фрагмент со спикером у микрофона."

или:

"Найди фрагмент с voice-over об услуге."

или:

"Найди готовый смонтированный ролик с динамичной музыкой."

или:

"Найди видео, где есть закадровая озвучка,
но нет оригинального звука."

или:

"Найди подсъемку (B-roll) крупным планом."

и определить:

1. какой файл использовать;
2. какой segment использовать;
3. start;
4. end;
5. что находится в кадре;
6. какой тип визуального материала;
7. есть ли речь;
8. является ли речь voice-over;
9. есть ли музыка;
10. есть ли оригинальный звук;
11. можно ли сохранить оригинальный звук;
12. является ли исходник уже смонтированным видео.

Не создавай итоговый ролик.
Только анализируй видео.
"""


# ----------------------------------------------------------------------
# 2. ИЗВЛЕЧЕНИЕ ТЕХНИЧЕСКИХ МЕТАДАННЫХ ВИДЕО (OPENCV / FFPROBE)
# ----------------------------------------------------------------------
def extract_video_metadata(video_path: str) -> dict:
    """
    Извлечение технических параметров видеофайла (width, height, fps, aspect_ratio, duration).
    """
    logging.info(f"[Metadata] Извлечение технических параметров видео: {video_path}")
    
    meta = {
        "filename": os.path.basename(video_path),
        "filepath": os.path.abspath(video_path),
        "size_bytes": os.path.getsize(video_path) if os.path.exists(video_path) else 0,
        "width": None,
        "height": None,
        "fps": None,
        "aspect_ratio": None,
        "duration": None
    }

    # Попытка 1: Используем OpenCV (если установлен)
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = round(frame_count / fps, 2) if fps > 0 else 0.0

            if w > 0 and h > 0:
                meta["width"] = w
                meta["height"] = h
                meta["aspect_ratio"] = round(w / h, 2)
            if fps > 0:
                meta["fps"] = round(fps, 2)
            if duration > 0:
                meta["duration"] = duration

            cap.release()
            logging.info(f"[Metadata] Параметры считаны через OpenCV: {meta['width']}x{meta['height']}, {meta['fps']} fps, {meta['duration']}s")
    except Exception as e:
        logging.warning(f"[Metadata] Не удалось считать параметры через cv2: {e}")

    # Попытка 2: Фолбэк на ffprobe (если cv2 не дал полные данные)
    if meta["duration"] is None or meta["width"] is None:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate,duration",
                "-show_entries", "format=duration",
                "-of", "json", video_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            
            streams = data.get("streams", [])
            format_info = data.get("format", {})
            
            if streams:
                stream = streams[0]
                w = int(stream.get("width", 0))
                h = int(stream.get("height", 0))
                if w > 0 and h > 0:
                    meta["width"] = w
                    meta["height"] = h
                    meta["aspect_ratio"] = round(w / h, 2)
                
                r_fps = stream.get("r_frame_rate", "")
                if "/" in r_fps:
                    num, den = map(float, r_fps.split("/"))
                    if den > 0:
                        meta["fps"] = round(num / den, 2)
                elif r_fps:
                    meta["fps"] = round(float(r_fps), 2)

                dur_str = stream.get("duration") or format_info.get("duration")
                if dur_str:
                    meta["duration"] = round(float(dur_str), 2)

            logging.info(f"[Metadata] Параметры считаны через ffprobe: {meta['width']}x{meta['height']}, {meta['fps']} fps, {meta['duration']}s")
        except Exception as e:
            logging.warning(f"[Metadata] Не удалось получить метаданные через ffprobe: {e}")

    return meta


# ----------------------------------------------------------------------
# 3. ИНТЕГРАЦИИ (WHISPER & GEMINI)
# ----------------------------------------------------------------------
def run_whisper(video_path: str) -> dict:
    """
    Распознавание речи локально через Whisper (модель small).
    """
    logging.info(f"[Whisper] Запуск локальной транскрибации: {video_path}")
    try:
        import whisper
        model = whisper.load_model("small")
        result = model.transcribe(video_path, language="ru")
        
        full_text = result.get("text", "").strip()
        segments = result.get("segments", [])
        
        cleaned_segments = [
            {
                "start": round(seg.get("start", 0.0), 2),
                "end": round(seg.get("end", 0.0), 2),
                "speaker": "Speaker",
                "text": seg.get("text", "").strip()
            }
            for seg in segments
        ]
        
        return {
            "full_text": full_text,
            "segments": cleaned_segments,
            "language": result.get("language", "ru"),
            "has_speech": bool(full_text)
        }
    except Exception as e:
        logging.warning(f"[Whisper] Не удалось распознать текст через whisper import: {e}")
        return {"full_text": "", "segments": [], "language": "ru", "has_speech": False}


def run_gemini_analysis(video_path: str, prompt: str) -> dict:
    """
    Отправка видеофайла в Gemini API с обработкой асинхронной загрузки.
    """
    logging.info(f"[Gemini API] Начинаем загрузку видеофайла: {video_path}")
    
    try:
        import google.generativeai as genai
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logging.error("[Gemini API] GEMINI_API_KEY не установлен в окружении!")
            return {}
            
        genai.configure(api_key=api_key)

        # 1. Загрузка видео через Files API
        video_file = genai.upload_file(path=video_path)
        logging.info(f"[Gemini API] Файл загружен ({video_file.name}). Ожидаем завершения обработки...")

        # 2. Ожидание состояния ACTIVE
        while video_file.state.name == "PROCESSING":
            time.sleep(5)
            video_file = genai.get_file(video_file.name)
            logging.info("[Gemini API] Видео обрабатывается серверами Google...")

        if video_file.state.name == "FAILED":
            raise ValueError(f"Ошибка обработки видео серверами Gemini: {video_file.state.name}")

        logging.info("[Gemini API] Видео готово к анализу. Запрашиваем структуру...")

        # 3. Вызов модели
        model = genai.GenerativeModel(model_name="gemini-1.5-pro")
        response = model.generate_content(
            [video_file, prompt],
            generation_config={"temperature": 0.2, "response_mime_type": "application/json"}
        )

        # Удаление загруженного файла из облака
        try:
            genai.delete_file(video_file.name)
        except Exception:
            pass

        # 4. Парсинг ответа JSON
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        return json.loads(raw_text.strip())

    except Exception as e:
        logging.error(f"[Gemini API] Критическая ошибка при обработке {video_path}: {e}")
        return {}


# ----------------------------------------------------------------------
# 4. СБОРКА ПАСПОРТА V3.0
# ----------------------------------------------------------------------
def build_v3_passport(video_meta: dict, gemini_res: dict, whisper_res: dict) -> dict:
    """
    Объединяет вывод Gemini (согласно схеме) и Whisper в паспорт версии 3.0.
    """
    scenes = gemini_res.get("scenes", [])
    segments = gemini_res.get("segments", [])
    gemini_transcription = gemini_res.get("transcription", {})
    gemini_audio = gemini_res.get("audio", {})
    gemini_search = gemini_res.get("search_index", {})
    classification = gemini_res.get("classification", {})

    # 1. Извлечение текста
    whisper_text = whisper_res.get("full_text", "").strip()
    gemini_text = gemini_transcription.get("full_text", "").strip()
    spoken_text = whisper_text if whisper_text else gemini_text

    whisper_segments = whisper_res.get("segments", [])
    gemini_segments = gemini_transcription.get("segments", [])
    speech_segments = whisper_segments if len(whisper_segments) > 0 else gemini_segments

    has_speech = whisper_res.get("has_speech", False) or gemini_audio.get("has_speech", False) or bool(spoken_text)

    # 2. Агрегация ключевых слов, действий и фраз в единый search_index
    keywords_set = set(gemini_search.get("keywords", []))
    actions_set = set()
    subjects_set = set(gemini_search.get("subjects", []))
    phrases_set = set(gemini_search.get("important_phrases", []))

    # Распаковка начального массива actions если он пришел строками
    for act in gemini_search.get("actions", []):
        if isinstance(act, str):
            actions_set.add(act)
        elif isinstance(act, dict) and "action" in act:
            actions_set.add(act["action"])

    # Чтение действий из сцен (поддержка объектов с таймкодами)
    for sc in scenes:
        keywords_set.update(sc.get("visual_tags", []))
        phrases_set.update(sc.get("search_phrases", []))
        subjects_set.update(sc.get("subjects", []))
        
        for act in sc.get("actions", []):
            if isinstance(act, dict) and "action" in act:
                actions_set.add(act["action"])
            elif isinstance(act, str):
                actions_set.add(act)

    # Чтение действий из сегментов (поддержка объектов с таймкодами)
    for seg in segments:
        keywords_set.update(seg.get("visual_tags", []))
        keywords_set.update(seg.get("search_tags", []))
        phrases_set.update(seg.get("search_phrases", []))
        subjects_set.update(seg.get("subjects", []))
        
        for act in seg.get("actions", []):
            if isinstance(act, dict) and "action" in act:
                actions_set.add(act["action"])
            elif isinstance(act, str):
                actions_set.add(act)

    search_index = {
        "filename": video_meta.get("filename", ""),
        "keywords": list(filter(None, keywords_set)),
        "actions": list(filter(None, actions_set)),
        "subjects": list(filter(None, subjects_set)),
        "important_phrases": list(filter(None, phrases_set)),
        "spoken_text": spoken_text,
        "has_visual_content": len(scenes) > 0,
        "has_audio": gemini_audio.get("has_audio", False) or has_speech,
        "has_speech": has_speech,
        "has_music": gemini_audio.get("has_music", False),
        "has_ambient_sound": gemini_audio.get("has_ambient_sound", False),
        "preserve_original_audio": gemini_audio.get("preserve_original_audio", False),
        "segment_count": len(scenes)
    }

    # 3. Флаги статусов
    is_success = len(scenes) > 0 or has_speech
    analysis_status = "completed" if is_success else "failed"
    passport_status = "ready" if is_success else "failed"
    transcription_status = "completed" if has_speech else "no_speech_detected"

    duration_val = video_meta.get("duration") or gemini_res.get("source", {}).get("duration_seconds", 0.0)

    return {
        "passport_version": PASSPORT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "video": video_meta,
        "source": {
            "duration_seconds": duration_val,
            "language": whisper_res.get("language") or gemini_res.get("source", {}).get("language", "ru"),
            "content_summary": gemini_res.get("source", {}).get("content_summary", ""),
            "video_format": gemini_res.get("source", {}).get("video_format", "unknown"),
            "is_edited": classification.get("content_type") == "edited_video"
        },
        "classification": classification,
        "transcription": {
            "has_speech": has_speech,
            "has_voice_over": gemini_audio.get("has_voice_over", False),
            "language": whisper_res.get("language") or gemini_transcription.get("language", "ru"),
            "full_text": spoken_text,
            "segments": speech_segments,
            "segment_count": len(speech_segments)
        },
        "audio": gemini_audio,
        "editing": gemini_res.get("editing", {}),
        "visual": gemini_res.get("visual", {}),
        "scenes": scenes,
        "segments": segments,
        "search_index": search_index,
        "usage": {
            "can_use_visual": len(scenes) > 0,
            "can_use_audio": gemini_audio.get("has_audio", False),
            "can_use_speech": has_speech,
            "can_use_music": gemini_audio.get("has_music", False),
            "preserve_original_audio": gemini_audio.get("preserve_original_audio", False)
        },
        "processing": {
            "analysis_provider": "gemini-1.5-pro",
            "analysis_status": analysis_status,
            "passport_status": passport_status,
            "transcription_status": transcription_status
        }
    }


def save_passport(passport: dict, output_dir: str = OUTPUT_DIR) -> str:
    """
    Сохранение паспорта в JSON-файл.
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = passport.get("video", {}).get("filename", "video_passport")
    base_name = Path(filename).stem
    out_path = os.path.join(output_dir, f"{base_name}_passport.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(passport, f, ensure_ascii=False, indent=2)

    logging.info(f"[Pipeline] Паспорт сохранен: {out_path}")
    return out_path


# ----------------------------------------------------------------------
# 5. ОСНОВНОЙ ПАЙПЛАЙН
# ----------------------------------------------------------------------
def run_pipeline(video_path: str, video_meta: dict = None) -> dict:
    """
    Запуск полного цикла обработки файла.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Файл {video_path} не найден на диске.")

    if os.path.getsize(video_path) == 0:
        raise ValueError(f"Файл {video_path} является пустым (0 байт). Пропуск.")

    # 1. Автоматическое извлечение метаданных (ширина, высота, fps, aspect_ratio, duration)
    extracted_meta = extract_video_metadata(video_path)
    if video_meta:
        extracted_meta.update(video_meta)
    video_meta = extracted_meta

    logging.info(f"=== [START] Обработка видео: {video_meta['filename']} ===")

    # 2. Запуск Whisper
    whisper_res = run_whisper(video_path)

    # 3. Запуск Gemini (с полной PROMPT_SCHEMA)
    gemini_res = run_gemini_analysis(video_path, PROMPT_SCHEMA)

    # 4. Сборка паспорта v3.0
    passport = build_v3_passport(video_meta, gemini_res, whisper_res)

    # 5. Сохранение результатов
    save_passport(passport)

    logging.info(f"=== [FINISH] Обработка завершена: {video_meta['filename']} ===")
    return passport


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
        run_pipeline(target_path)
    else:
        print("Использование: python pipeline.py <путь_к_видеофайлу>")