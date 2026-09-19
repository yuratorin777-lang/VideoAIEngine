# src/core/smart_framing/analyzer.py

from __future__ import annotations

from typing import Iterable, List, Tuple

from .models import (
    BoundingBox,
    CropDecision,
    CropStrategy,
    Detection,
    DetectionType,
    FrameAnalysis,
    SmartFramingConfig,
)


class SmartFramingAnalyzer:
    """
    Converts visual detections into a stable crop decision.
    Optimized for dance performance tracking with floor and body preservation.
    """

    def __init__(
        self,
        config: SmartFramingConfig | None = None,
    ) -> None:
        self.config = config or SmartFramingConfig()

    def analyze(
        self,
        analyses: Iterable[FrameAnalysis],
        target_width: int,
        target_height: int,
    ) -> CropDecision:
        analyses_list = list(analyses)

        if not analyses_list:
            raise ValueError(
                "Smart Framing requires at least one frame analysis."
            )

        source_width = analyses_list[0].frame_width
        source_height = analyses_list[0].frame_height

        crop_width, crop_height = self._calculate_crop_size(
            source_width=source_width,
            source_height=source_height,
            target_width=target_width,
            target_height=target_height,
        )

        # Выделяем и фильтруем ключевые детекции для танца
        detections = self._aggregate_and_filter_detections(analyses_list)

        if not detections:
            return self._center_crop_decision(
                source_width=source_width,
                source_height=source_height,
                crop_width=crop_width,
                crop_height=crop_height,
                target_width=target_width,
                target_height=target_height,
                strategy=CropStrategy.CENTER_CROP,
                reason="No semantic objects detected.",
            )

        safe_region = self._calculate_safe_region(
            detections=detections,
            source_width=source_width,
            source_height=source_height,
        )

        crop_x, crop_y = self._find_best_crop_position(
            safe_region=safe_region,
            source_width=source_width,
            source_height=source_height,
            crop_width=crop_width,
            crop_height=crop_height,
        )

        score = self._score_crop(
            crop_x=crop_x,
            crop_y=crop_y,
            crop_width=crop_width,
            crop_height=crop_height,
            detections=detections,
            source_width=source_width,
            source_height=source_height,
        )

        strategy = self._select_strategy(detections)

        return CropDecision(
            x=crop_x,
            y=crop_y,
            width=crop_width,
            height=crop_height,
            source_width=source_width,
            source_height=source_height,
            target_width=target_width,
            target_height=target_height,
            strategy=strategy,
            score=score,
            reason="Stable multi-frame crop focused on main dancers and movement area.",
            detected_people=sum(
                1 for d in detections if d.detection_type == DetectionType.PERSON
            ),
            detected_faces=sum(
                1 for d in detections if d.detection_type == DetectionType.FACE
            ),
            detected_heads=sum(
                1 for d in detections if d.detection_type == DetectionType.HEAD
            ),
            detected_text_regions=sum(
                1 for d in detections if d.detection_type == DetectionType.TEXT
            ),
            detected_logos=sum(
                1 for d in detections if d.detection_type == DetectionType.LOGO
            ),
        )

    def _calculate_crop_size(
        self,
        source_width: int,
        source_height: int,
        target_width: int,
        target_height: int,
    ) -> Tuple[int, int]:
        target_ratio = target_width / target_height

        crop_width = source_width
        crop_height = int(round(crop_width / target_ratio))

        if crop_height > source_height:
            crop_height = source_height
            crop_width = int(round(crop_height * target_ratio))

        crop_width = max(1, min(crop_width, source_width))
        crop_height = max(1, min(crop_height, source_height))

        return crop_width, crop_height

    def _aggregate_and_filter_detections(
        self,
        analyses: List[FrameAnalysis],
    ) -> List[Detection]:
        """
        Фильтрует мелкий шум и фокусируется на главном танцоре / объекте в кадре.
        """
        filtered_detections: List[Detection] = []

        for analysis in analyses:
            persons = [
                d for d in analysis.detections 
                if d.detection_type == DetectionType.PERSON
            ]
            
            if persons:
                # Находим ведущего танцора на кадре по площади и уверенности
                primary_person = max(
                    persons,
                    key=lambda p: (p.bbox.width * p.bbox.height) * getattr(p, 'confidence', 1.0)
                )
                primary_area = primary_person.bbox.width * primary_person.bbox.height
                
                # Оставляем только значимые детекции людей (≥ 20% площади главного объекта)
                valid_persons = [
                    p for p in persons 
                    if (p.bbox.width * p.bbox.height) >= primary_area * 0.20
                ]
                filtered_detections.extend(valid_persons)
            
            # Добавляем лица, головы, текст и логотипы для сохранения контекста
            other_detections = [
                d for d in analysis.detections 
                if d.detection_type != DetectionType.PERSON
            ]
            filtered_detections.extend(other_detections)

        return filtered_detections

    def _calculate_safe_region(
        self,
        detections: List[Detection],
        source_width: int,
        source_height: int,
    ) -> BoundingBox:
        if not detections:
            return BoundingBox(
                x=0,
                y=0,
                width=source_width,
                height=source_height,
            )

        min_x = source_width
        min_y = source_height
        max_x = 0
        max_y = 0

        for detection in detections:
            bbox = detection.bbox
            margin_ratio = self._margin_for_detection(detection.detection_type)

            margin_x = int(bbox.width * margin_ratio)
            
            # Для людей закладываем запас снизу для защиты ног и паркета
            if detection.detection_type == DetectionType.PERSON:
                margin_y_top = int(bbox.height * self.config.head_margin_ratio)
                margin_y_bottom = int(bbox.height * margin_ratio * 1.5)
            else:
                margin_y_top = int(bbox.height * margin_ratio)
                margin_y_bottom = margin_y_top

            min_x = min(min_x, bbox.x - margin_x)
            min_y = min(min_y, bbox.y - margin_y_top)

            max_x = max(max_x, bbox.x2 + margin_x)
            max_y = max(max_y, bbox.y2 + margin_y_bottom)

        safe_x = max(0, min_x)
        safe_y = max(0, min_y)
        safe_w = min(source_width, max_x) - safe_x
        safe_h = min(source_height, max_y) - safe_y

        return BoundingBox(
            x=safe_x,
            y=safe_y,
            width=safe_w,
            height=safe_h,
        )

    def _margin_for_detection(
        self,
        detection_type: DetectionType,
    ) -> float:
        if detection_type == DetectionType.FACE:
            return self.config.face_margin_ratio
        if detection_type == DetectionType.HEAD:
            return self.config.head_margin_ratio
        if detection_type == DetectionType.TEXT:
            return self.config.text_margin_ratio
        if detection_type == DetectionType.PERSON:
            return self.config.person_margin_ratio
        return self.config.person_margin_ratio

    def _find_best_crop_position(
        self,
        safe_region: BoundingBox,
        source_width: int,
        source_height: int,
        crop_width: int,
        crop_height: int,
    ) -> Tuple[int, int]:
        max_x = source_width - crop_width
        max_y = source_height - crop_height

        # 1. Горизонталь: по центру масс
        desired_center_x = safe_region.center_x
        x = int(round(desired_center_x - crop_width / 2))

        # 2. Вертикаль: по центру фигуры
        desired_center_y = safe_region.center_y
        y = int(round(desired_center_y - crop_height / 2))

        # 3. Мягкая защита головы (возвращаем 8% воздуха)
        # safe_region.y — верхняя граница головы
        headroom = int(crop_height * 0.08)
        
        if y > (safe_region.y - headroom):
            y = safe_region.y - headroom

        # 4. Зажим в пределах кадра [0, max]
        x = max(0, min(x, max_x))
        y = max(0, min(y, max_y))

        return x, y

    def _score_crop(
        self,
        crop_x: int,
        crop_y: int,
        crop_width: int,
        crop_height: int,
        detections: List[Detection],
        source_width: int,
        source_height: int,
    ) -> float:
        crop = BoundingBox(
            x=crop_x,
            y=crop_y,
            width=crop_width,
            height=crop_height,
        )

        total_weight = 0.0
        preserved_weight = 0.0

        for detection in detections:
            weight = self._weight_for_detection(detection.detection_type)
            total_weight += weight

            if self._contains_with_margin(crop=crop, bbox=detection.bbox):
                preserved_weight += weight
            elif self._intersects(crop, detection.bbox):
                preserved_weight += weight * 0.35

        if total_weight <= 0:
            return 0.0

        return preserved_weight / total_weight

    def _contains_with_margin(
        self,
        crop: BoundingBox,
        bbox: BoundingBox,
    ) -> bool:
        margin_x = int(bbox.width * 0.05)
        margin_y = int(bbox.height * 0.05)

        return (
            bbox.x >= crop.x + margin_x
            and bbox.y >= crop.y + margin_y
            and bbox.x2 <= crop.x2 - margin_x
            and bbox.y2 <= crop.y2 - margin_y
        )

    @staticmethod
    def _intersects(
        first: BoundingBox,
        second: BoundingBox,
    ) -> bool:
        return not (
            first.x2 <= second.x
            or first.x >= second.x2
            or first.y2 <= second.y
            or first.y >= second.y2
        )

    def _weight_for_detection(
        self,
        detection_type: DetectionType,
    ) -> float:
        if detection_type == DetectionType.FACE:
            return self.config.face_weight
        if detection_type == DetectionType.HEAD:
            return self.config.head_weight
        if detection_type == DetectionType.PERSON:
            return self.config.person_weight
        if detection_type == DetectionType.TEXT:
            return self.config.text_weight
        if detection_type == DetectionType.LOGO:
            return self.config.logo_weight
        return 1.0

    def _select_strategy(
        self,
        detections: List[Detection],
    ) -> CropStrategy:
        types = {detection.detection_type for detection in detections}

        if DetectionType.PERSON in types:
            return CropStrategy.SMART_PERSON_CROP
        if DetectionType.FACE in types or DetectionType.HEAD in types:
            return CropStrategy.SMART_FACE_CROP
        if DetectionType.TEXT in types or DetectionType.LOGO in types:
            return CropStrategy.SMART_TEXT_CROP

        return CropStrategy.SMART_COMPOSITION_CROP

    def _center_crop_decision(
        self,
        source_width: int,
        source_height: int,
        crop_width: int,
        crop_height: int,
        target_width: int,
        target_height: int,
        strategy: CropStrategy,
        reason: str,
    ) -> CropDecision:
        x = max(0, (source_width - crop_width) // 2)
        y = max(0, (source_height - crop_height) // 2)

        return CropDecision(
            x=x,
            y=y,
            width=crop_width,
            height=crop_height,
            source_width=source_width,
            source_height=source_height,
            target_width=target_width,
            target_height=target_height,
            strategy=strategy,
            score=0.0,
            reason=reason,
        )