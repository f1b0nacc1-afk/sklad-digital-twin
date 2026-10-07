"""Стенд и случайная расстановка объектов в его ячейках."""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.services import layout

STANDS_DIR = Path(__file__).parent / "stands"
CLASS_NAMES = ["box", "pallet", "container", "person"]
CLASS_INDEX = {name: i for i, name in enumerate(CLASS_NAMES)}


@dataclass(frozen=True)
class StandCell:
    address: str
    zone: str
    shelf: str | None
    polygon: list[list[float]]
    surface_z: float  # height of the surface objects stand on

    @property
    def centre(self) -> tuple[float, float]:
        xs, ys = zip(*self.polygon, strict=True)
        return sum(xs) / len(xs), sum(ys) / len(ys)

    @property
    def size(self) -> tuple[float, float]:
        """Extent along X and Y (cells of the demo stand are axis-aligned)."""
        xs, ys = zip(*self.polygon, strict=True)
        return max(xs) - min(xs), max(ys) - min(ys)


@dataclass
class Stand:
    spec: dict
    cells: list[StandCell]

    @property
    def length(self) -> float:
        return self.spec["size"][0]

    @property
    def width(self) -> float:
        return self.spec["size"][1]

    def shelf_top_z(self, shelf: dict) -> float:
        """Surface of the top level: the only one visible from above (ФТ-ЛОК-06)."""
        return shelf["height"] * (shelf["levels"] - 1) / shelf["levels"]

    @classmethod
    def load(cls, name: str = "maquette_a") -> "Stand":
        spec = json.loads((STANDS_DIR / f"{name}.json").read_text(encoding="utf-8-sig"))
        cells: list[StandCell] = []
        for s in spec["shelves"]:
            geom = layout.ShelfGeometry(s["code"], s["x"], s["y"], s["width"], s["depth"],
                                        s["rotation_deg"])
            top = s["levels"]
            top_z = s["height"] * (top - 1) / top
            for c in layout.generate_shelf_cells(geom, s["levels"], s["places"]):
                if c.level == top:
                    cells.append(StandCell(c.address, s["zone"], s["code"], c.polygon, top_z))
        zones = {z["code"]: z for z in spec["zones"]}
        for code, step in spec["floor_cells"].items():
            for c in layout.generate_floor_cells(code, zones[code]["polygon"], step):
                cells.append(StandCell(c.address, code, None, c.polygon, 0.0))
        return cls(spec, cells)


@dataclass
class SceneObject:
    cls: str
    x: float
    y: float
    z: float  # bottom
    size: tuple[float, float, float]  # length (along yaw), width, height
    yaw_deg: float
    cell: str | None
    zone: str | None
    loaded: bool = False  # pallet with cargo on top
    shade: float = 0.7
    has_label: bool = False

    @property
    def top_z(self) -> float:
        return self.z + self.size[2] + (0.03 if self.loaded else 0.0)

    def corners(self) -> np.ndarray:
        """8 world corners: bottom ring then top ring."""
        length, width, _ = self.size
        a = math.radians(self.yaw_deg)
        c, s = math.cos(a), math.sin(a)
        ring = []
        for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
            lx, ly = dx * length / 2, dy * width / 2
            ring.append([self.x + lx * c - ly * s, self.y + lx * s + ly * c])
        bottom = [[x, y, self.z] for x, y in ring]
        top = [[x, y, self.top_z] for x, y in ring]
        return np.array(bottom + top)


@dataclass
class Scene:
    objects: list[SceneObject] = field(default_factory=list)
    distractors: list[dict] = field(default_factory=list)
    person: dict | None = None  # arm entering the frame


def random_scene(stand: Stand, rng: np.random.Generator, *, occupancy: float | None = None,
                 loose: int | None = None, distractors: int | None = None,
                 person_prob: float = 0.1) -> Scene:
    sizes = stand.spec["object_sizes"]
    occ = rng.uniform(0.15, 0.95) if occupancy is None else occupancy
    scene = Scene()

    for cell in stand.cells:
        if rng.random() > occ:
            continue
        if cell.shelf:
            cls_name = "box" if rng.random() < 0.7 else "container"
        else:
            cls_name = "pallet" if rng.random() < 0.8 else "box"
        size = tuple(sizes[cls_name][rng.integers(len(sizes[cls_name]))])
        cw, ch = cell.size
        yaw = rng.uniform(-8, 8) + (90 if cls_name != "pallet" and rng.random() < 0.3 else 0)
        ext_x, ext_y = _extent(size, yaw)
        slack_x, slack_y = max(0.0, (cw - ext_x) / 2 * 0.8), max(0.0, (ch - ext_y) / 2 * 0.8)
        cx, cy = cell.centre
        scene.objects.append(SceneObject(
            cls=cls_name, x=cx + rng.uniform(-slack_x, slack_x),
            y=cy + rng.uniform(-slack_y, slack_y), z=cell.surface_z, size=size, yaw_deg=yaw,
            cell=cell.address, zone=cell.zone,
            loaded=cls_name == "pallet" and rng.random() < 0.6,
            shade=rng.uniform(0.45, 0.85), has_label=cls_name == "box" and rng.random() < 0.35,
        ))

    # Objects left outside addressed storage (ФТ-ЛОК-05): in aisles or free zone space.
    n_loose = rng.integers(0, 3) if loose is None else loose
    for _ in range(n_loose):
        for _attempt in range(30):
            x, y = rng.uniform(0.05, stand.length - 0.05), rng.uniform(0.05, stand.width - 0.05)
            if not _blocked(stand, scene, x, y, 0.06):
                cls_name = "box" if rng.random() < 0.7 else "container"
                size = tuple(sizes[cls_name][rng.integers(len(sizes[cls_name]))])
                scene.objects.append(SceneObject(
                    cls=cls_name, x=x, y=y, z=0.0, size=size, yaw_deg=rng.uniform(0, 180),
                    cell=None, zone=_zone_at(stand, x, y), shade=rng.uniform(0.45, 0.85),
                ))
                break

    n_distr = rng.integers(0, 4) if distractors is None else distractors
    for _ in range(n_distr):
        for _attempt in range(30):
            x, y = rng.uniform(0.03, stand.length - 0.03), rng.uniform(0.03, stand.width - 0.03)
            if not _blocked(stand, scene, x, y, 0.03):
                kind = rng.choice(["roll", "pen", "sheet"])
                scene.distractors.append({"kind": str(kind), "x": x, "y": y,
                                          "yaw": float(rng.uniform(0, 180))})
                break

    if rng.random() < person_prob:
        edge = rng.choice(["left", "right", "top", "bottom"])
        scene.person = {"edge": str(edge), "pos": float(rng.uniform(0.2, 0.8)),
                        "reach": float(rng.uniform(0.12, 0.3)), "z": 0.35}
    return scene


def _extent(size: tuple, yaw_deg: float) -> tuple[float, float]:
    a = math.radians(yaw_deg)
    length, width = size[0], size[1]
    return (abs(length * math.cos(a)) + abs(width * math.sin(a)),
            abs(length * math.sin(a)) + abs(width * math.cos(a)))


def _zone_at(stand: Stand, x: float, y: float) -> str | None:
    for z in stand.spec["zones"]:
        if layout.point_in_polygon(x, y, z["polygon"]):
            return z["code"]
    return None


def _blocked(stand: Stand, scene: Scene, x: float, y: float, r: float) -> bool:
    for s in stand.spec["shelves"]:
        if abs(x - s["x"]) < s["width"] / 2 + r and abs(y - s["y"]) < s["depth"] / 2 + r:
            return True
    for c in stand.cells:
        if c.shelf is None:
            xs, ys = zip(*c.polygon, strict=True)
            if min(xs) - r < x < max(xs) + r and min(ys) - r < y < max(ys) + r:
                return True
    return any(math.hypot(o.x - x, o.y - y) < r + 0.05 for o in scene.objects)
