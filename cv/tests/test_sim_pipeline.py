import numpy as np

from cv.camera_model import CameraModel
from cv.detector import Detection, Detector, DetectorConfig
from cv.pipeline import (
    FloorHomographyMapper,
    PipelineConfig,
    Surface,
    SurfaceAwareMapper,
    process_frame,
    stand_locator,
)
from cv.quality import assess
from cv.sim.render import render
from cv.sim.scene import CLASS_INDEX, Stand, random_scene


def stand_and_cam():
    stand = Stand.load()
    cam = CameraModel.looking_down(0.6, 0.4, 1.15, tilt_x_deg=0.8, yaw_deg=1.5)
    return stand, cam


def test_stand_cells():
    stand = Stand.load()
    shelf_cells = [c for c in stand.cells if c.shelf]
    floor_cells = [c for c in stand.cells if not c.shelf]
    assert len(shelf_cells) == 4 * 3  # top level only
    assert all(c.address.endswith(("-03-01", "-03-02", "-03-03")) for c in shelf_cells)
    assert len(floor_cells) == 10
    assert all(c.surface_z > 0.1 for c in shelf_cells)


def test_markers_and_cells_are_in_view():
    stand, cam = stand_and_cam()
    pts = [[x, y, 0.0] for x, y in stand.spec["markers"]]
    pts += [[x, y, c.surface_z] for c in stand.cells for x, y in c.polygon]
    uv = cam.project(np.array(pts))
    assert (uv[:, 0] > 0).all() and (uv[:, 0] < cam.width).all()
    assert (uv[:, 1] > 0).all() and (uv[:, 1] < cam.height).all()


def test_render_produces_consistent_labels():
    stand, cam = stand_and_cam()
    rng = np.random.default_rng(1)
    scene = random_scene(stand, rng, occupancy=0.6, person_prob=0.0)
    r = render(stand, scene, cam, rng, scale=0.25)
    assert r.image.shape == (912, 1368) and r.image.dtype == np.uint8
    assert len(r.truths) == len(scene.objects)
    for line in r.yolo_labels():
        c, *vals = line.split()
        assert int(c) in CLASS_INDEX.values()
        assert all(0 <= float(v) <= 1 for v in vals)
    assert assess(r.image).ok


def test_oracle_detector_pipeline_assigns_cells():
    """With perfect detections the camera-model mapper puts every shelf object in its cell."""
    stand, cam = stand_and_cam()
    rng = np.random.default_rng(7)
    scene = random_scene(stand, rng, occupancy=1.0, loose=0, distractors=0, person_prob=0.0)
    r = render(stand, scene, cam, rng, scale=1.0)

    def predict_batch(images):
        rows = [[*np.array(t.bbox) * 0.25, 0.99, CLASS_INDEX[t.cls]] for t in r.truths]
        return [np.array(rows)]

    detector = Detector(predict_batch, DetectorConfig(scale=0.25))
    surfaces = [Surface([[s["x"] - s["width"] / 2, s["y"] - s["depth"] / 2],
                         [s["x"] + s["width"] / 2, s["y"] - s["depth"] / 2],
                         [s["x"] + s["width"] / 2, s["y"] + s["depth"] / 2],
                         [s["x"] - s["width"] / 2, s["y"] + s["depth"] / 2]],
                        stand.shelf_top_z(s)) for s in stand.spec["shelves"]]
    locator, addr, _ = stand_locator(stand.cells, stand.spec["zones"])
    res = process_frame(r.image, detector, SurfaceAwareMapper(cam, surfaces), locator,
                        PipelineConfig())
    assert res.rejected is None
    got = sorted(addr[ld.cell_id] for ld in res.detections if ld.cell_id)
    want = sorted(o.cell for o in scene.objects)
    assert got == want


def test_floor_homography_mapper_uses_anchor():
    h = [[0.001, 0, 0], [0, 0.001, 0], [0, 0, 1]]
    d = Detection("box", 0.9, 100, 200, 300, 400)
    assert FloorHomographyMapper(h).to_world(d) == (0.2, 0.3)
    assert FloorHomographyMapper(h, view="oblique").to_world(d) == (0.2, 0.4)
