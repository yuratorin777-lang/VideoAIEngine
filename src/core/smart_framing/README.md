# Smart Framing

Локальный модуль интеллектуального кадрирования VideoAIEngine.

## Назначение

Smart Framing отвечает за принятие решения:

> какую область исходного кадра необходимо сохранить при приведении видео
> к целевому формату.

Модуль не занимается финальным рендерингом видео.

FFmpeg остаётся исполнителем решения.

---

# Архитектура

```text
Smart Framing
│
├── Level 1 — Geometry
│   ├── source dimensions
│   ├── target aspect ratio
│   ├── crop dimensions
│   └── crop boundaries
│
├── Level 2 — Visual Awareness
│   ├── person detection
│   ├── face/head detection
│   ├── text detection
│   ├── logo detection
│   └── safe zones
│
└── Level 3 — Tracking
    └── dynamic crop movement