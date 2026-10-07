"""Результаты виртуального стенда (cv/sim/demo.py) для страницы «Виртуальный стенд»."""

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser
from app.core.config import get_settings

router = APIRouter(prefix="/api/stand", tags=["stand"])

_ID = re.compile(r"^[A-Za-z0-9_\-]+$")
_FILE_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".json": "application/json"}


def _root() -> Path:
    return (get_settings().storage_dir / "stand_demo").resolve()


def _run_dir(run_id: str) -> Path:
    if not _ID.match(run_id) or not (_root() / run_id / "summary.json").is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Прогон не найден")
    return _root() / run_id


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/runs")
def list_runs(_: CurrentUser) -> list[dict]:
    root = _root()
    if not root.is_dir():
        return []
    runs = []
    for d in sorted(root.iterdir(), reverse=True):
        summary = d / "summary.json"
        if summary.is_file():
            s = _read(summary)
            runs.append({"run": s["run"], "created": s["created"], "weights": s["weights"],
                         "totals": s["totals"]})
    return runs


@router.get("/runs/{run_id}")
def get_run(run_id: str, _: CurrentUser) -> dict:
    return _read(_run_dir(run_id) / "summary.json")


@router.get("/runs/{run_id}/scenes/{scene_id}")
def get_scene(run_id: str, scene_id: str, _: CurrentUser) -> dict:
    if not _ID.match(scene_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сцена не найдена")
    path = _run_dir(run_id) / "scenes" / scene_id / "scene.json"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сцена не найдена")
    return _read(path)


@router.get("/runs/{run_id}/files/{file_path:path}")
def get_file(run_id: str, file_path: str, _: CurrentUser) -> FileResponse:
    run = _run_dir(run_id).resolve()
    target = (run / file_path).resolve()
    if not target.is_relative_to(run) or not target.is_file() or target.suffix not in _FILE_TYPES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    return FileResponse(target, media_type=_FILE_TYPES[target.suffix],
                        headers={"Cache-Control": "private, max-age=86400"})
