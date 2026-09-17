import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union, Literal, TypedDict

# ======================================================================
# КОНТРАКТЫ ДАННЫХ И ДОПУСТИМЫЕ ЗНАЧЕНИЯ (ДЛЯ IDE И ВАЛИДАЦИИ)
# ======================================================================

AudioType = Literal[
    "dialogue",
    "voiceover_command",
    "ambient_noise",
    "clean_music",
    "none",
    "unknown"
]

SoundCategory = Literal[
    "speech",
    "music",
    "ambient",
    "noise"
]

ALLOWED_AUDIO_TYPES: List[AudioType] = [
    "dialogue",
    "voiceover_command",
    "ambient_noise",
    "clean_music",
    "none",
    "unknown"
]

ALLOWED_SOUND_CATEGORIES: List[SoundCategory] = [
    "speech",
    "music",
    "ambient",
    "noise"
]


class ActionItem(TypedDict):
    action: str
    start: float
    end: float


class SoundClassification(TypedDict):
    primary_category: SoundCategory
    detected_categories: List[SoundCategory]
    confidence_notes: str


class AudioData(TypedDict):
    has_audio: bool
    has_speech: bool
    has_voice_over: bool
    has_music: bool
    has_ambient_sound: bool
    has_noise: bool
    has_silence: bool
    audio_type: AudioType
    sound_classification: SoundClassification
    original_audio_present: bool
    preserve_original_audio: bool
    audio_description: str
    music_description: str
    voice_over_description: str
    notes: str


class PassportStore:
    """
    Video Passport storage (Schema v3.0).

    Video Passport — структурированное описание исходного видео,
    которое используется системой для:

    1. поиска релевантных исходников;
    2. поиска конкретных временных фрагментов;
    3. понимания содержания изображения;
    4. понимания речи и ее таймкодов;
    5. определения возможности использования оригинального звука;
    6. последующей сборки конечного видео из нескольких исходников.

    Сам видеофайл в Passport НЕ хранится.
    Passport содержит идентификатор и ссылку на исходник в Google Drive.
    """

    PASSPORT_VERSION = "3.0"

    def __init__(
        self,
        base_dir: str = "04_LIBRARY/passports"
    ):
        self.passports_dir = base_dir
        os.makedirs(
            self.passports_dir,
            exist_ok=True
        )

    # =============================================================
    # PUBLIC API
    # =============================================================

    def save_passport(
        self,
        video_event: dict,
        raw_ai_response: Any,
        merge_existing: bool = True
    ) -> str:
        """
        Создает и сохраняет Video Passport (Schema v3.0).

        video_event:
            Метаданные файла Google Drive / локального файла.

        raw_ai_response:
            JSON-ответ Gemini с анализом видео или готовый dict.

        merge_existing:
            Если True, при наличии файла на диске сохраняются существующие
            ручные правки и списки, а не сбрасываются в значения по умолчанию.
        """

        ai_data = self._parse_ai_response(
            raw_ai_response
        )

        # ---------------------------------------------------------
        # SOURCE METADATA
        # ---------------------------------------------------------

        video = self._build_video_metadata(
            video_event
        )

        file_id = video["file_id"]

        passport_filename = (
            f"passport_{file_id}.json"
        )

        filepath = os.path.join(
            self.passports_dir,
            passport_filename
        )

        # ---------------------------------------------------------
        # LOAD EXISTING PASSPORT (IF EXISTS)
        # ---------------------------------------------------------

        existing_passport: Dict[str, Any] = {}

        if merge_existing and os.path.exists(filepath):
            try:
                with open(
                    filepath,
                    "r",
                    encoding="utf-8"
                ) as f:
                    existing_passport = json.load(f)
            except Exception:
                existing_passport = {}

        merged_video = self._merge_dict(
            existing_passport.get("video", {}),
            video
        )

        # ---------------------------------------------------------
        # AI DATA WITH MERGE SUPPORT
        # ---------------------------------------------------------

        classification = self._normalize_classification(
            ai_data.get("classification", {}),
            existing=existing_passport.get("classification")
        )

        transcription = self._normalize_transcription(
            ai_data.get("transcription", {}),
            existing=existing_passport.get("transcription")
        )

        audio = self._normalize_audio(
            ai_data.get("audio", {}),
            existing=existing_passport.get("audio")
        )

        scenes = self._normalize_scenes(
            ai_data.get("scenes", []),
            existing=existing_passport.get("scenes", [])
        )

        # ---------------------------------------------------------
        # SEARCHABLE SEGMENTS
        # ---------------------------------------------------------

        segments = self._build_search_segments(
            scenes=scenes,
            transcription=transcription,
            audio=audio
        )

        # ---------------------------------------------------------
        # SEARCH INDEX
        # ---------------------------------------------------------

        search_index = self._build_search_index(
            filename=merged_video["filename"],
            scenes=scenes,
            transcription=transcription,
            audio=audio,
            segments=segments,
            ai_data=ai_data
        )

        # ---------------------------------------------------------
        # USAGE POLICY
        # ---------------------------------------------------------

        usage = self._build_usage(
            audio=audio,
            transcription=transcription
        )

        # ---------------------------------------------------------
        # PASSPORT ASSEMBLY
        # ---------------------------------------------------------

        created_at = (
            existing_passport.get("created_at")
            or self._now()
        )

        passport = {
            "passport_version": self.PASSPORT_VERSION,

            "created_at": created_at,

            "updated_at": self._now(),

            # =====================================================
            # 1. SOURCE VIDEO
            # =====================================================

            "video": merged_video,

            # =====================================================
            # 2. CLASSIFICATION
            # =====================================================

            "classification": classification,

            # =====================================================
            # 3. TRANSCRIPTION
            # =====================================================

            "transcription": transcription,

            # =====================================================
            # 4. AUDIO
            # =====================================================

            "audio": audio,

            # =====================================================
            # 5. SCENES
            # =====================================================

            "scenes": scenes,

            # =====================================================
            # 6. SEARCHABLE SEGMENTS
            # =====================================================

            "segments": segments,

            # =====================================================
            # 7. SEARCH INDEX
            # =====================================================

            "search_index": search_index,

            # =====================================================
            # 8. SOURCE USAGE
            # =====================================================

            "usage": usage,

            # =====================================================
            # 9. PROCESSING INFO
            # =====================================================

            "processing": {
                "analysis_provider": "gemini",
                "analysis_status": "completed",
                "passport_status": "ready",
                "transcription_status": (
                    "completed"
                    if transcription["has_speech"]
                    else "no_speech_detected"
                )
            }
        }

        # ---------------------------------------------------------
        # SAVE FILE
        # ---------------------------------------------------------

        with open(
            filepath,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                passport,
                f,
                indent=2,
                ensure_ascii=False
            )

        return filepath

    # =============================================================
    # VIDEO METADATA
    # =============================================================

    def _build_video_metadata(
        self,
        video_event: dict
    ) -> dict:
        if not isinstance(video_event, dict):
            video_event = {}

        file_id = (
            video_event.get("file_id")
            or video_event.get("id")
            or video_event.get("fileId")
            or "unknown_id"
        )

        filename = (
            video_event.get("filename")
            or video_event.get("name")
            or video_event.get("title")
            or "unknown_video"
        )

        drive_url = (
            video_event.get("drive_url")
            or video_event.get("web_view_link")
            or video_event.get("webViewLink")
            or video_event.get("url")
            or ""
        )

        raw_size = (
            video_event.get("size_bytes")
            or video_event.get("size")
            or video_event.get("fileSize")
            or 0
        )
        try:
            size_bytes = int(raw_size)
        except (ValueError, TypeError):
            size_bytes = 0

        created_at = (
            video_event.get("created_at")
            or video_event.get("created_time")
            or video_event.get("createdTime")
            or ""
        )

        modified_at = (
            video_event.get("modified_at")
            or video_event.get("modified_time")
            or video_event.get("modifiedTime")
            or ""
        )

        mime_type = (
            video_event.get("mime_type")
            or video_event.get("mimeType")
            or "video/mp4"
        )

        return {
            "file_id": str(file_id),
            "filename": str(filename),
            "drive_url": str(drive_url),
            "mime_type": str(mime_type),
            "size_bytes": size_bytes,
            "created_at": str(created_at),
            "modified_at": str(modified_at)
        }

    # =============================================================
    # CLASSIFICATION
    # =============================================================

    def _normalize_classification(
        self,
        classification: dict,
        existing: Optional[dict] = None
    ) -> dict:

        if not isinstance(classification, dict):
            classification = {}

        if not isinstance(existing, dict):
            existing = {}

        project = (
            classification.get("project")
            or classification.get("project_id")
            or existing.get("project")
            or existing.get("project_id")
            or getattr(self, "default_project", None)
            or "Pending_Classification"
        )

        content_type = (
            classification.get("content_type")
            or existing.get("content_type")
            or "raw_footage"
        )

        status = (
            classification.get("status")
            or existing.get("status")
            or "pending"
        )

        primary_category = (
            classification.get("primary_category")
            or existing.get("primary_category")
        )

        confidence = (
            classification.get("confidence")
            if classification.get("confidence") is not None
            else existing.get("confidence")
        )

        categories = self._unique(
            self._string_list(existing.get("categories", []))
            + self._string_list(classification.get("categories", []))
        )

        secondary_categories = self._unique(
            self._string_list(existing.get("secondary_categories", []))
            + self._string_list(classification.get("secondary_categories", []))
        )

        possible_use_cases = self._unique(
            self._string_list(existing.get("possible_use_cases", []))
            + self._string_list(classification.get("possible_use_cases", []))
        )

        return {
            "project": project,
            "content_type": content_type,
            "status": status,
            "primary_category": primary_category,
            "confidence": confidence,
            "categories": categories,
            "secondary_categories": secondary_categories,
            "possible_use_cases": possible_use_cases
        }

    # =============================================================
    # TRANSCRIPTION
    # =============================================================

    def _normalize_transcription(
        self,
        transcription: dict,
        existing: Optional[dict] = None
    ) -> dict:

        if not isinstance(
            transcription,
            dict
        ):
            transcription = {}

        if not isinstance(
            existing,
            dict
        ):
            existing = {}

        raw_segments = (
            transcription.get("segments")
            or existing.get("segments", [])
        )

        normalized_segments = []

        if isinstance(raw_segments, list):

            for item in raw_segments:

                if not isinstance(item, dict):
                    continue

                start = self._float(
                    item.get("start", 0.0)
                )

                end = self._float(
                    item.get("end", start)
                )

                text = str(
                    item.get("text", "")
                ).strip()

                speaker = str(
                    item.get("speaker", "")
                ).strip()

                if end < start:
                    end = start

                normalized_segments.append({
                    "start": start,
                    "end": end,
                    "speaker": speaker,
                    "text": text
                })

        has_speech = bool(
            transcription.get(
                "has_speech",
                existing.get(
                    "has_speech",
                    len(normalized_segments) > 0
                )
            )
        )

        language = str(
            transcription.get(
                "language",
                existing.get("language", "")
            )
        ).strip()

        provided_full_text = (
            transcription.get("full_text")
            or existing.get("full_text", "")
        )

        if provided_full_text:
            full_text = str(
                provided_full_text
            ).strip()
        else:
            full_text = " ".join(
                segment["text"]
                for segment in normalized_segments
                if segment["text"]
            )

        return {
            "has_speech": has_speech,

            "language": language,

            "full_text": full_text,

            "segments": normalized_segments,

            "segment_count": len(
                normalized_segments
            )
        }

    # =============================================================
    # AUDIO (С ПОДДЕРЖКОЙ AUDIO_TYPE И 4-КАТЕГОРИЙНОЙ КЛАССИФИКАЦИИ)
    # =============================================================

    def _normalize_audio(
        self,
        audio: dict,
        existing: Optional[dict] = None
    ) -> AudioData:

        if not isinstance(audio, dict):
            audio = {}

        if not isinstance(existing, dict):
            existing = {}

        def resolve_bool(key: str, default: bool = False) -> bool:
            if key in audio:
                return bool(audio[key])
            if key in existing:
                return bool(existing[key])
            return default

        has_audio = resolve_bool("has_audio", False)
        has_speech = resolve_bool("has_speech", False)
        has_voice_over = resolve_bool("has_voice_over", False)
        has_music = resolve_bool("has_music", False)
        has_ambient_sound = resolve_bool("has_ambient_sound", False)
        has_noise = resolve_bool("has_noise", False)
        has_silence = resolve_bool("has_silence", False)
        original_audio_present = resolve_bool("original_audio_present", False)
        preserve_original_audio = resolve_bool("preserve_original_audio", has_audio)

        # ---------------------------------------------------------
        # AUDIO_TYPE ВАЛИДАЦИЯ
        # Допустимые значения: dialogue, voiceover_command, ambient_noise, clean_music, none, unknown
        # ---------------------------------------------------------
        raw_audio_type = str(
            audio.get("audio_type")
            or existing.get("audio_type", "unknown")
        ).strip().lower()

        audio_type: AudioType = raw_audio_type if raw_audio_type in ALLOWED_AUDIO_TYPES else "unknown"

        # ---------------------------------------------------------
        # SOUND CLASSIFICATION (4 КАТЕГОРИИ)
        # ---------------------------------------------------------
        raw_sound_class = (
            audio.get("sound_classification")
            or existing.get("sound_classification")
            or {}
        )
        if not isinstance(raw_sound_class, dict):
            raw_sound_class = {}

        raw_primary = str(
            raw_sound_class.get("primary_category", "speech")
        ).strip().lower()
        primary_category: SoundCategory = raw_primary if raw_primary in ALLOWED_SOUND_CATEGORIES else "speech"

        raw_detected = self._string_list(raw_sound_class.get("detected_categories", []))
        detected_categories: List[SoundCategory] = [
            cat for cat in raw_detected if cat in ALLOWED_SOUND_CATEGORIES
        ]

        confidence_notes = str(raw_sound_class.get("confidence_notes", "")).strip()

        sound_classification: SoundClassification = {
            "primary_category": primary_category,
            "detected_categories": detected_categories,
            "confidence_notes": confidence_notes
        }

        audio_description = str(
            audio.get("audio_description")
            or existing.get("audio_description", "")
        ).strip()

        music_description = str(
            audio.get("music_description")
            or existing.get("music_description", "")
        ).strip()

        voice_over_description = str(
            audio.get("voice_over_description")
            or existing.get("voice_over_description", "")
        ).strip()

        notes = str(
            audio.get("notes")
            or existing.get("notes", "")
        ).strip()

        return {
            "has_audio": has_audio,
            "has_speech": has_speech,
            "has_voice_over": has_voice_over,
            "has_music": has_music,
            "has_ambient_sound": has_ambient_sound,
            "has_noise": has_noise,
            "has_silence": has_silence,
            "audio_type": audio_type,
            "sound_classification": sound_classification,
            "original_audio_present": original_audio_present,
            "preserve_original_audio": preserve_original_audio,
            "audio_description": audio_description,
            "music_description": music_description,
            "voice_over_description": voice_over_description,
            "notes": notes
        }

    # =============================================================
    # SCENES (С ПОДДЕРЖКОЙ ОБЪЕКТОВ ACTIONS С ТАЙМКОДАМИ)
    # =============================================================

    def _normalize_scenes(
        self,
        scenes: list,
        existing: Optional[list] = None
    ) -> list:

        target_scenes = (
            scenes if scenes
            else (existing if isinstance(existing, list) else [])
        )

        if not isinstance(
            target_scenes,
            list
        ):
            return []

        normalized = []

        for idx, scene in enumerate(
            target_scenes,
            start=1
        ):

            if not isinstance(
                scene,
                dict
            ):
                continue

            start = self._float(
                scene.get("start", 0.0)
            )

            end = self._float(
                scene.get("end", start)
            )

            if end < start:
                end = start

            description = str(
                scene.get(
                    "description",
                    ""
                )
            ).strip()

            subjects = self._string_list(
                scene.get(
                    "subjects",
                    []
                )
            )

            # ВАЖНО: Нормализация действий (из action_elements или actions)
            raw_actions = (
                scene.get("action_elements")
                or scene.get("actions", [])
            )
            
            # Структурированные действия (с таймкодами/объектами)
            actions = self._normalize_actions(raw_actions)

            # Плоский список текстовых элементов действий для Schema v3.0
            action_elements = self._string_list([
                act["action"] if isinstance(act, dict) and "action" in act else act
                for act in (raw_actions if isinstance(raw_actions, list) else [raw_actions])
            ])

            dance_elements = self._string_list(
                scene.get(
                    "dance_elements",
                    []
                )
            )

            emotions = self._string_list(
                scene.get(
                    "emotion",
                    scene.get(
                        "emotions",
                        []
                    )
                )
            )

            locations = self._string_list(
                scene.get(
                    "location",
                    scene.get(
                        "locations",
                        []
                    )
                )
            )

            visual_tags = self._string_list(
                scene.get(
                    "visual_tags",
                    []
                )
            )

            search_phrases = self._string_list(
                scene.get(
                    "search_phrases",
                    []
                )
            )

            camera = str(
                scene.get(
                    "camera",
                    ""
                )
            ).strip()

            composition = str(
                scene.get(
                    "composition",
                    ""
                )
            ).strip()

            interaction = str(
                scene.get(
                    "interaction",
                    ""
                )
            ).strip()

            audio_in_scene = scene.get(
                "audio_in_scene",
                {}
            )

            if not isinstance(
                audio_in_scene,
                dict
            ):
                audio_in_scene = {}

            recommended_source_use = self._string_list(
                scene.get(
                    "recommended_source_use",
                    []
                )
            )

            normalized.append({

                "id": scene.get(
                    "id",
                    f"scene_{idx:03d}"
                ),

                "start": start,

                "end": end,

                "duration": round(
                    max(0.0, end - start),
                    3
                ),

                "description": description,

                "subjects": subjects,

                "actions": actions,

                "action_elements": action_elements,

                "dance_elements": dance_elements,

                "camera": camera,

                "composition": composition,

                "emotion": emotions,

                "location": locations,

                "interaction": interaction,

                "visual_tags": visual_tags,

                "search_phrases": search_phrases,

                "audio_in_scene": {
                    "speech": bool(
                        audio_in_scene.get(
                            "speech",
                            False
                        )
                    ),

                    "voice_over": bool(
                        audio_in_scene.get(
                            "voice_over",
                            False
                        )
                    ),

                    "music": bool(
                        audio_in_scene.get(
                            "music",
                            False
                        )
                    ),

                    "ambient_sound": bool(
                        audio_in_scene.get(
                            "ambient_sound",
                            False
                        )
                    ),

                    "original_audio_present": bool(
                        audio_in_scene.get(
                            "original_audio_present",
                            False
                        )
                    )
                },

                "recommended_source_use": (
                    recommended_source_use
                )
            })

        return normalized
    # =============================================================
    # SEARCH SEGMENTS
    # =============================================================

    def _build_search_segments(
        self,
        scenes: list,
        transcription: dict,
        audio: dict
    ) -> list:

        segments = []

        speech_segments = transcription.get(
            "segments",
            []
        )

        for idx, scene in enumerate(
            scenes,
            start=1
        ):

            start = scene.get(
                "start",
                0.0
            )

            end = scene.get(
                "end",
                0.0
            )

            # -----------------------------------------------------
            # SPEECH INSIDE SCENE
            # -----------------------------------------------------

            speech = []

            for item in speech_segments:

                speech_start = self._float(
                    item.get(
                        "start",
                        0.0
                    )
                )

                speech_end = self._float(
                    item.get(
                        "end",
                        speech_start
                    )
                )

                if (
                    speech_start < end
                    and speech_end > start
                ):

                    speech.append({
                        "start": speech_start,
                        "end": speech_end,
                        "speaker": item.get(
                            "speaker",
                            ""
                        ),
                        "text": item.get(
                            "text",
                            ""
                        )
                    })

            # -----------------------------------------------------
            # TAGS & ACTIONS
            # -----------------------------------------------------

            visual_tags = scene.get(
                "visual_tags",
                []
            )

            actions = scene.get(
                "actions",
                []
            )

            # Извлечение чистых строк действий для поиска
            action_names = [
                act["action"] if isinstance(act, dict) else str(act)
                for act in actions
            ]

            subjects = scene.get(
                "subjects",
                []
            )

            emotions = scene.get(
                "emotion",
                []
            )

            dance_elements = scene.get(
                "dance_elements",
                []
            )

            search_phrases = scene.get(
                "search_phrases",
                []
            )

            search_tags = self._unique(
                visual_tags
                + action_names
                + subjects
                + emotions
                + dance_elements
            )

            spoken_words = [
                item["text"]
                for item in speech
                if item.get("text")
            ]

            # -----------------------------------------------------
            # AUDIO USAGE
            # -----------------------------------------------------

            segment_has_speech = (
                len(speech) > 0
            )

            segment_can_use_audio = (
                audio.get(
                    "has_audio",
                    False
                )
                and audio.get(
                    "preserve_original_audio",
                    False
                )
            )

            segment_has_music = audio.get(
                "has_music",
                False
            )

            segment_has_ambient_sound = audio.get(
                "has_ambient_sound",
                False
            )

            # -----------------------------------------------------
            # SEGMENT
            # -----------------------------------------------------

            segment = {

                "id": f"seg_{idx:03d}",

                "start": start,

                "end": end,

                "duration": round(
                    max(0.0, end - start),
                    3
                ),

                "semantic_description": scene.get(
                    "description",
                    ""
                ),

                "subjects": subjects,

                "actions": actions,

                "dance_elements": dance_elements,

                "emotions": emotions,

                "camera": scene.get(
                    "camera",
                    ""
                ),

                "visual_tags": visual_tags,

                "search_tags": search_tags,

                "search_phrases": search_phrases,

                # -------------------------------------------------
                # SPEECH
                # -------------------------------------------------

                "speech": speech,

                "spoken_text": " ".join(
                    spoken_words
                ),

                "has_speech": segment_has_speech,

                # -------------------------------------------------
                # AUDIO
                # -------------------------------------------------

                "audio_usage": {

                    "has_audio": audio.get(
                        "has_audio",
                        False
                    ),

                    "has_speech": (
                        segment_has_speech
                    ),

                    "has_music": (
                        segment_has_music
                    ),

                    "has_ambient_sound": (
                        segment_has_ambient_sound
                    ),

                    "has_noise": audio.get(
                        "has_noise",
                        False
                    ),

                    "can_use_original_audio": (
                        segment_can_use_audio
                    ),

                    "can_use_original_speech": (
                        segment_has_speech
                        and segment_can_use_audio
                    ),

                    "can_use_original_music": (
                        segment_has_music
                        and segment_can_use_audio
                    )
                }
            }

            segments.append(
                segment
            )

        return segments

    # =============================================================
    # SEARCH INDEX
    # =============================================================

    def _build_search_index(
        self,
        filename: str,
        scenes: list,
        transcription: dict,
        audio: dict,
        segments: list,
        ai_data: Optional[dict] = None
    ) -> dict:

        tags = []

        actions_list = []

        locations = []

        emotions = []

        dance_elements = []

        speech_topics = []

        important_phrases = []

        if ai_data and isinstance(ai_data, dict):
            speech_topics.extend(
                self._string_list(
                    ai_data.get("speech_topics", [])
                )
            )

        # ---------------------------------------------------------
        # VISUAL TAGS, ACTIONS & CATEGORIES
        # ---------------------------------------------------------

        for scene in scenes:

            tags.extend(
                scene.get(
                    "visual_tags",
                    []
                )
            )

            # Извлечение действий (безопасно от объектов и строк)
            for act in scene.get("actions", []):
                if isinstance(act, dict) and "action" in act:
                    actions_list.append(act["action"])
                elif isinstance(act, str):
                    actions_list.append(act)

            tags.extend(
                scene.get(
                    "subjects",
                    []
                )
            )

            emotions.extend(
                scene.get(
                    "emotion",
                    []
                )
            )

            dance_elements.extend(
                scene.get(
                    "dance_elements",
                    []
                )
            )

            locations.extend(
                self._string_list(
                    scene.get(
                        "location",
                        []
                    )
                )
            )

            important_phrases.extend(
                scene.get(
                    "search_phrases",
                    []
                )
            )

        # ---------------------------------------------------------
        # SPEECH
        # ---------------------------------------------------------

        spoken_text = transcription.get(
            "full_text",
            ""
        )

        # ---------------------------------------------------------
        # SEGMENT TAGS
        # ---------------------------------------------------------

        for segment in segments:

            tags.extend(
                segment.get(
                    "search_tags",
                    []
                )
            )

            important_phrases.extend(
                segment.get(
                    "search_phrases",
                    []
                )
            )

        return {

            "filename": filename,

            "keywords": self._unique(
                tags
            ),

            "actions": self._unique(
                actions_list
            ),

            "spoken_text": spoken_text,

            "has_visual_content": (
                len(scenes) > 0
            ),

            "has_audio": audio.get(
                "has_audio",
                False
            ),

            "has_speech": audio.get(
                "has_speech",
                False
            ),

            "has_music": audio.get(
                "has_music",
                False
            ),

            "has_ambient_sound": audio.get(
                "has_ambient_sound",
                False
            ),

            "has_noise": audio.get(
                "has_noise",
                False
            ),

            "preserve_original_audio": (
                audio.get(
                    "preserve_original_audio",
                    False
                )
            ),

            "segment_count": len(
                segments
            ),

            "locations": self._unique(
                locations
            ),

            "emotions": self._unique(
                emotions
            ),

            "dance_elements": self._unique(
                dance_elements
            ),

            "speech_topics": self._unique(
                speech_topics
            ),

            "important_phrases": self._unique(
                important_phrases
            )
        }

    # =============================================================
    # USAGE POLICY
    # =============================================================

    def _build_usage(
        self,
        audio: dict,
        transcription: dict
    ) -> dict:

        has_audio = audio.get(
            "has_audio",
            False
        )

        has_speech = audio.get(
            "has_speech",
            False
        )

        has_music = audio.get(
            "has_music",
            False
        )

        has_ambient_sound = audio.get(
            "has_ambient_sound",
            False
        )

        preserve_original_audio = audio.get(
            "preserve_original_audio",
            False
        )

        return {

            "can_use_visual": True,

            "can_use_audio": (
                has_audio
            ),

            "can_use_speech": (
                has_speech
                and preserve_original_audio
                and transcription.get(
                    "has_speech",
                    False
                )
            ),

            "can_use_music": (
                has_music
                and preserve_original_audio
            ),

            "can_use_ambient_sound": (
                has_ambient_sound
                and preserve_original_audio
            ),

            "preserve_original_audio": (
                preserve_original_audio
            )
        }

    # =============================================================
    # AI RESPONSE PARSER
    # =============================================================

    def _parse_ai_response(
        self,
        raw_ai_response: Any
    ) -> dict:

        if isinstance(
            raw_ai_response,
            dict
        ):
            return raw_ai_response

        if not isinstance(
            raw_ai_response,
            str
        ):
            return self._fallback_ai_response(
                str(raw_ai_response)
            )

        text = raw_ai_response.strip()

        if not text:
            return self._fallback_ai_response(
                raw_ai_response
            )

        # ---------------------------------------------------------
        # 1. Обычный JSON
        # ---------------------------------------------------------

        try:

            data = json.loads(
                text
            )

            if isinstance(
                data,
                dict
            ):
                return data

        except Exception:
            pass

        # ---------------------------------------------------------
        # 2. JSON внутри Markdown code fence
        # ---------------------------------------------------------

        if text.startswith(
            "```"
        ):

            lines = text.splitlines()

            if len(lines) >= 3:

                lines = lines[1:]

                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]

                cleaned = "\n".join(
                    lines
                ).strip()

                try:

                    data = json.loads(
                        cleaned
                    )

                    if isinstance(
                        data,
                        dict
                    ):
                        return data

                except Exception:
                    pass

        # ---------------------------------------------------------
        # 3. Попытка найти JSON-объект внутри текста
        # ---------------------------------------------------------

        first_brace = text.find("{")
        last_brace = text.rfind("}")

        if (
            first_brace >= 0
            and last_brace > first_brace
        ):

            candidate = text[
                first_brace:last_brace + 1
            ]

            try:

                data = json.loads(
                    candidate
                )

                if isinstance(
                    data,
                    dict
                ):
                    return data

            except Exception:
                pass

        # ---------------------------------------------------------
        # FALLBACK
        # ---------------------------------------------------------

        return self._fallback_ai_response(
            raw_ai_response
        )

    # =============================================================
    # FALLBACK
    # =============================================================

    @staticmethod
    def _fallback_ai_response(
        raw_ai_response: str
    ) -> dict:

        return {

            "raw_text": raw_ai_response,

            "classification": {},

            "transcription": {
                "has_speech": False,
                "language": "",
                "full_text": "",
                "segments": []
            },

            "audio": {
                "has_audio": False,
                "has_speech": False,
                "has_voice_over": False,
                "has_music": False,
                "has_ambient_sound": False,
                "has_noise": False,
                "has_silence": False,
                "audio_type": "unknown",
                "sound_classification": {
                    "primary_category": "speech",
                    "detected_categories": [],
                    "confidence_notes": ""
                },
                "original_audio_present": False,
                "preserve_original_audio": False,
                "audio_description": "",
                "music_description": "",
                "voice_over_description": "",
                "notes": ""
            },

            "scenes": []
        }

    # =============================================================
    # HELPERS
    # =============================================================

    @staticmethod
    def _normalize_actions(actions_raw: Any) -> List[ActionItem]:
        """
        Приводит список действий к единой структуре [{"action": "...", "start": 0.0, "end": 0.0}]
        поддерживая как новые объекты с таймкодами, так и обычные строки.
        """
        if not isinstance(actions_raw, list):
            return []

        result: List[ActionItem] = []
        for item in actions_raw:
            if isinstance(item, dict):
                act_str = str(item.get("action", "")).strip()
                if act_str:
                    result.append({
                        "action": act_str,
                        "start": PassportStore._float(item.get("start", 0.0)),
                        "end": PassportStore._float(item.get("end", 0.0))
                    })
            elif isinstance(item, str) and item.strip():
                result.append({
                    "action": item.strip(),
                    "start": 0.0,
                    "end": 0.0
                })

        return result

    @staticmethod
    def _merge_dict(
        base: dict,
        incoming: dict
    ) -> dict:

        result = dict(base or {})

        for k, v in (incoming or {}).items():
            if v or k not in result:
                result[k] = v

        return result

    @staticmethod
    def _unique(
        items: list
    ) -> list:

        result = []

        if not isinstance(
            items,
            list
        ):
            return result

        for item in items:

            if not isinstance(
                item,
                str
            ):
                continue

            item = item.strip()

            if (
                item
                and item not in result
            ):
                result.append(
                    item
                )

        return result

    @staticmethod
    def _string_list(
        value: Any
    ) -> List[str]:

        if not isinstance(
            value,
            list
        ):
            return []

        result = []

        for item in value:

            if item is None:
                continue

            text = str(
                item
            ).strip()

            if text:
                result.append(
                    text
                )

        return result

    @staticmethod
    def _float(
        value: Any
    ) -> float:

        try:
            return float(
                value
            )

        except (
            TypeError,
            ValueError
        ):
            return 0.0

    @staticmethod
    def _now() -> str:

        return datetime.now(
            timezone.utc
        ).isoformat()