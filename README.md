# Цифровой двойник склада (ЦДС-2026)

Информационная система контроля состояния склада по данным промышленной камеры: распознавание
объектов, привязка к ячейкам, история изменений, 2D-план, отчёты.

## Документация

- [Техническое задание (ред. 2.0)](docs/01_ТЗ_Цифровой_двойник_склада.md)
- [План реализации](docs/02_План_реализации.md) — календарный план на 16 недель
- [Рецензия на исходное ТЗ](docs/03_Рецензия_на_ТЗ.md)
- [Дорожная карта разработки](docs/04_Дорожная_карта_разработки.md) — статус по модулям кода
- [Виртуальный стенд](docs/05_Виртуальный_стенд.md) — распознавание на синтетических кадрах камеры, результаты испытания
- [Журнал работ](docs/06_Журнал_работ.md) — что сделано по датам
- Отчёты по оборудованию (открыть `index.html`):
  [Basler acA5472-17um](docs/equipment/basler-aca5472-17um-report/index.html),
  [Hikrobot MV-CE200-10UM](docs/equipment/hikrobot-mv-ce200-10um-report/index.html)

## Быстрый старт (Docker)

```bash
cp .env.example .env            # Windows: Copy-Item .env.example .env
docker compose up -d --build
docker compose exec api python /srv/scripts/seed_demo.py   # демо-склад и макет (необязательно)
```

- UI: http://localhost:8080 — вход `admin` / `admin12345` (меняется в `.env`)
- API и Swagger: http://localhost:8000/api/docs

## Локальная разработка

Требуется: Python 3.11, [uv](https://docs.astral.sh/uv/), Node.js 24, Docker.

```bash
uv sync                               # .venv с backend + CV (без torch)
docker compose up -d db redis         # PostgreSQL и Redis в контейнерах
cd backend
uv run alembic upgrade head           # схема БД
uv run python -m app.bootstrap        # админ, справочник типов, настройки
uv run uvicorn app.main:app --reload  # API на :8000
cd ..
uv run python scripts/seed_demo.py    # демо-данные (--replace — пересоздать)

cd frontend && npm install && npm run dev   # UI на :5173, /api проксируется на :8000
```

Дополнительные зависимости:

| Команда | Что ставит |
|---|---|
| `uv sync --extra ml` | Ultralytics YOLO + SAHI (тянет PyTorch) — детектор и обучение |
| `uv sync --extra basler` | `pypylon` для Basler; кадр с камеры: `uv run python scripts/grab_one.py` |
| `uv sync --extra barcode` | `zxing-cpp` для штрихкодов/QR |

Hikrobot MVS SDK ставится с сайта производителя, `MvImport` добавляется в `PYTHONPATH`.

## Проверки

```bash
uv run pytest --cov          # unit + API тесты (SQLite in-memory, БД не нужна)
uv run ruff check .
cd backend && uv run alembic check      # модели и миграции совпадают
cd frontend && npm run lint && npm run build
```

Новая миграция после изменения моделей: `cd backend && uv run alembic revision --autogenerate -m "..."`.

## Структура

```
backend/app/
  core/       конфигурация, БД, JWT/bcrypt
  models/     SQLAlchemy-модели (ТЗ 4.4.3)
  schemas/    Pydantic-схемы API
  api/        роутеры FastAPI
  services/   бизнес-логика: layout (ячейки, валидация), geo (гомография, привязка),
              structure, audit; далее matching, occupancy, reports
backend/alembic/   миграции
cv/
  sources/    CameraSource: file, video, basler, hikrobot
  quality.py  контроль качества кадра
  camera_model.py   модель камеры: K + поза, проекция на плоскость заданной высоты
  detector.py, tiling.py   YOLO, масштаб, тайлинг, NMS
  pipeline.py       кадр -> качество -> детекции -> координаты -> ячейки
  sim/        виртуальный стенд: сцена, рендер, датасет, испытание
  training/   обучение YOLO
frontend/src/
  pages/      экраны
  components/plan/   2D-план склада (react-konva)
scripts/      seed_demo.py, grab_one.py, backup.sh
datasets/     данные для обучения (вне git)
docs/         ТЗ, план, рецензия, отчёты по оборудованию
```

Соглашения: код, API и коды классов — на английском; интерфейс, сообщения об ошибках и
документация — на русском. Координаты — метры склада, начало в левом нижнем углу плана.
