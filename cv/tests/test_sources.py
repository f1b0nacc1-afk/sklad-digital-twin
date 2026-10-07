import cv2
import numpy as np
import pytest

from cv.sources import SourceError, create_source
from cv.sources.file import FileSource


def write_png(path, image):
    ok, buf = cv2.imencode(".png", image)
    assert ok
    buf.tofile(str(path))


def test_file_source_reads_mono_from_cyrillic_path(tmp_path):
    folder = tmp_path / "кадры"
    folder.mkdir()
    write_png(folder / "снимок_1.png", np.full((30, 40), 77, np.uint8))
    write_png(folder / "снимок_2.png", np.full((30, 40, 3), 10, np.uint8))

    with FileSource(folder) as src:
        first = src.grab()
        second = src.grab()
        assert src.remaining == 0
        with pytest.raises(SourceError):
            src.grab()

    assert first.is_mono and first.width == 40 and first.height == 30
    assert first.pixel_format == "Mono8"
    # gray-looking 3-channel PNG is collapsed to mono
    assert second.is_mono
    assert src.health().last_frame_at is not None


def test_file_source_missing_file(tmp_path):
    with pytest.raises(SourceError):
        FileSource(tmp_path / "nope.png").open()


def test_file_source_not_an_image(tmp_path):
    bad = tmp_path / "virus.png"
    bad.write_bytes(b"MZ\x90\x00 not an image")
    src = FileSource(bad)
    src.open()
    with pytest.raises(SourceError):
        src.grab()


def test_video_source_steps_through_frames(tmp_path):
    path = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for i in range(50):  # 5 seconds
        writer.write(np.full((48, 64, 3), i * 5, np.uint8))
    writer.release()

    src = create_source("video", path=str(path), params={"step_s": 2.0})
    with src:
        frames = []
        while True:
            try:
                frames.append(src.grab())
            except SourceError:
                break
    assert [f.meta["position_ms"] for f in frames] == [0.0, 2000.0, 4000.0]
    assert all(f.is_mono for f in frames)


def test_factory_unknown_connection():
    with pytest.raises(SourceError):
        create_source("carrier-pigeon")


def test_basler_without_sdk_gives_clear_error():
    try:
        import pypylon  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("pypylon installed; covered by hardware tests")
    with pytest.raises(SourceError, match="pypylon"):
        create_source("basler").open()
