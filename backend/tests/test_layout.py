import pytest
from shapely.geometry import Polygon

from app.services.layout import (
    ShelfGeometry,
    generate_floor_cells,
    generate_shelf_cells,
    point_in_polygon,
    shelf_footprint,
    validate_layout,
    validate_zone_polygon,
)


def shelf(code="A-01", x=5.0, y=5.0, w=3.0, d=1.0, rot=0.0) -> ShelfGeometry:
    return ShelfGeometry(code, x, y, w, d, rot)


def test_footprint_axis_aligned():
    assert shelf_footprint(shelf()) == [[3.5, 4.5], [6.5, 4.5], [6.5, 5.5], [3.5, 5.5]]


def test_footprint_rotated_90_swaps_dimensions():
    poly = Polygon(shelf_footprint(shelf(rot=90)))
    min_x, min_y, max_x, max_y = poly.bounds
    assert max_x - min_x == pytest.approx(1.0)
    assert max_y - min_y == pytest.approx(3.0)
    assert poly.area == pytest.approx(3.0)


def test_generate_cells_count_and_addresses():
    cells = generate_shelf_cells(shelf(), levels=4, places_per_level=3)
    assert len(cells) == 12
    assert cells[0].address == "A-01-01-01"
    assert cells[-1].address == "A-01-04-03"
    assert len({c.address for c in cells}) == 12


def test_cells_tile_the_shelf_footprint():
    s = shelf(rot=30)
    cells = [c for c in generate_shelf_cells(s, 1, 4)]
    total = sum(Polygon(c.polygon).area for c in cells)
    assert total == pytest.approx(Polygon(shelf_footprint(s)).area)


def test_same_place_shares_footprint_across_levels():
    cells = generate_shelf_cells(shelf(), 3, 2)
    by_place = {}
    for c in cells:
        by_place.setdefault(c.place, []).append(c.polygon)
    for polys in by_place.values():
        assert all(p == polys[0] for p in polys)


def test_generate_cells_rejects_zero_levels():
    with pytest.raises(ValueError):
        generate_shelf_cells(shelf(), 0, 3)


def test_acceptance_t03_five_shelves_give_60_cells():
    shelves = [shelf(f"A-0{i}", x=3 + i * 4) for i in range(1, 6)]
    total = sum(len(generate_shelf_cells(s, 4, 3)) for s in shelves)
    assert total == 60
    assert validate_layout(30, 15, shelves) == []


def test_validate_outside_room():
    errors = validate_layout(10, 10, [shelf(x=9.5)])
    assert errors and "границы" in errors[0]


def test_validate_overlap():
    errors = validate_layout(30, 15, [shelf("A-01", x=5), shelf("A-02", x=6)])
    assert errors == ["Стеллажи A-01 и A-02 пересекаются"]


def test_touching_shelves_are_valid():
    assert validate_layout(30, 15, [shelf("A-01", x=5), shelf("A-02", x=8)]) == []


def test_rotated_shelf_overlap_detected():
    # Rotated 45° shelf pokes into the neighbour even though centres are 2.5 m apart.
    errors = validate_layout(30, 15, [shelf("A-01", x=5, rot=45), shelf("A-02", x=7.5)])
    assert len(errors) == 1


def test_floor_cells_grid():
    cells = generate_floor_cells("C", [[0, 0], [2, 0], [2, 1], [0, 1]], 0.5)
    assert len(cells) == 8
    assert cells[0].address == "C-F-01"
    assert cells[-1].address == "C-F-08"


def test_floor_cells_skip_squares_outside_l_shape():
    l_shape = [[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]]
    assert len(generate_floor_cells("C", l_shape, 1.0)) == 3


def test_zone_polygon_validation():
    assert validate_zone_polygon(10, 10, [[0, 0], [5, 0], [5, 5]]) == []
    assert validate_zone_polygon(10, 10, [[0, 0], [11, 0], [11, 5]])
    assert validate_zone_polygon(10, 10, [[0, 0], [5, 5], [5, 0], [0, 5]])  # bow-tie
    assert validate_zone_polygon(10, 10, [[0, 0], [1, 1]])


def test_point_in_polygon_includes_boundary():
    square = [[0, 0], [1, 0], [1, 1], [0, 1]]
    assert point_in_polygon(0.5, 0.5, square)
    assert point_in_polygon(1.0, 0.5, square)
    assert not point_in_polygon(1.5, 0.5, square)
