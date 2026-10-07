def make_warehouse(client, headers, **overrides):
    body = {"name": "Склад №1", "length_m": 30, "width_m": 15, "height_m": 6, **overrides}
    resp = client.post("/api/warehouses", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_zone(client, headers, warehouse_id, code="A", polygon=None):
    body = {
        "warehouse_id": warehouse_id,
        "code": code,
        "name": f"Зона {code}",
        "polygon": polygon or [[0, 0], [30, 0], [30, 15], [0, 15]],
    }
    resp = client.post("/api/zones", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def shelf_body(zone_id, code="A-01", x=5.0, **overrides):
    return {
        "zone_id": zone_id, "code": code, "x_m": x, "y_m": 5.0, "width_m": 3.0,
        "depth_m": 1.0, "height_m": 2.0, "levels": 4, "places_per_level": 3, **overrides,
    }


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"login": "admin", "password": "nope"})
    assert resp.status_code == 401


def test_me(client, admin_headers):
    resp = client.get("/api/auth/me", headers=admin_headers)
    assert resp.json()["role"] == "admin"


def test_request_without_token_is_401(client):
    assert client.get("/api/warehouses").status_code == 401


def test_bad_token_is_401(client):
    resp = client.get("/api/warehouses", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_operator_cannot_write_structure(client, operator_headers):
    body = {"name": "x", "length_m": 1, "width_m": 1, "height_m": 1}
    assert client.post("/api/warehouses", json=body, headers=operator_headers).status_code == 403
    assert client.get("/api/users", headers=operator_headers).status_code == 403


def test_operator_can_read(client, admin_headers, operator_headers):
    make_warehouse(client, admin_headers)
    resp = client.get("/api/warehouses", headers=operator_headers)
    assert resp.status_code == 200 and len(resp.json()) == 1


def test_default_object_types_seeded(client, operator_headers):
    codes = {t["code"] for t in client.get("/api/object-types", headers=operator_headers).json()}
    assert {"box", "pallet", "container", "person"} <= codes


def test_acceptance_t03_structure_and_cells(client, admin_headers):
    wh = make_warehouse(client, admin_headers)
    zone = make_zone(client, admin_headers, wh["id"])
    for i in range(1, 6):
        resp = client.post(
            "/api/shelves", json=shelf_body(zone["id"], f"A-0{i}", x=3 + i * 4),
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
    twin = client.get(f"/api/warehouses/{wh['id']}/twin", headers=admin_headers).json()
    assert len(twin["shelves"]) == 5
    assert len(twin["cells"]) == 60
    assert {c["address"] for c in twin["cells"]} >= {"A-01-01-01", "A-05-04-03"}


def test_acceptance_t04_validation(client, admin_headers):
    wh = make_warehouse(client, admin_headers)
    zone = make_zone(client, admin_headers, wh["id"])
    client.post("/api/shelves", json=shelf_body(zone["id"]), headers=admin_headers)

    overlap = client.post(
        "/api/shelves", json=shelf_body(zone["id"], "A-02", x=6), headers=admin_headers
    )
    assert overlap.status_code == 422
    assert "пересекаются" in overlap.json()["detail"]["errors"][0]

    outside = client.post(
        "/api/shelves", json=shelf_body(zone["id"], "A-03", x=29.5), headers=admin_headers
    )
    assert outside.status_code == 422

    bad_zone = client.post("/api/zones", json={
        "warehouse_id": wh["id"], "code": "Z", "polygon": [[0, 0], [40, 0], [40, 5]],
    }, headers=admin_headers)
    assert bad_zone.status_code == 422


def test_shelf_update_regenerates_and_archives_cells(client, admin_headers, db):
    from app.models import Cell

    wh = make_warehouse(client, admin_headers)
    zone = make_zone(client, admin_headers, wh["id"])
    shelf = client.post("/api/shelves", json=shelf_body(zone["id"]), headers=admin_headers).json()

    resp = client.patch(f"/api/shelves/{shelf['id']}", json={"levels": 2}, headers=admin_headers)
    assert resp.status_code == 200
    active = client.get(f"/api/cells?shelf_id={shelf['id']}", headers=admin_headers).json()
    assert len(active) == 6
    assert db.query(Cell).filter(Cell.archived_at.isnot(None)).count() == 12


def test_invalid_shelf_update_is_rolled_back(client, admin_headers):
    wh = make_warehouse(client, admin_headers)
    zone = make_zone(client, admin_headers, wh["id"])
    shelf = client.post("/api/shelves", json=shelf_body(zone["id"]), headers=admin_headers).json()
    resp = client.patch(f"/api/shelves/{shelf['id']}", json={"x_m": 100}, headers=admin_headers)
    assert resp.status_code == 422
    shelves = client.get(f"/api/shelves?warehouse_id={wh['id']}", headers=admin_headers).json()
    assert shelves[0]["x_m"] == 5.0


def test_floor_cells_endpoint(client, admin_headers):
    wh = make_warehouse(client, admin_headers)
    zone = make_zone(client, admin_headers, wh["id"], "C", [[20, 0], [30, 0], [30, 3], [20, 3]])
    resp = client.post(
        f"/api/zones/{zone['id']}/generate-floor-cells", json={"step_m": 1.0},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 30


def test_archived_shelf_disappears_from_twin(client, admin_headers):
    wh = make_warehouse(client, admin_headers)
    zone = make_zone(client, admin_headers, wh["id"])
    shelf = client.post("/api/shelves", json=shelf_body(zone["id"]), headers=admin_headers).json()
    assert client.delete(f"/api/shelves/{shelf['id']}", headers=admin_headers).status_code == 204
    twin = client.get(f"/api/warehouses/{wh['id']}/twin", headers=admin_headers).json()
    assert twin["shelves"] == [] and twin["cells"] == []


def test_user_management_and_audit(client, admin_headers, db):
    from app.models import AuditLog

    resp = client.post("/api/users", json={
        "login": "ivanov", "password": "password1", "role": "viewer",
    }, headers=admin_headers)
    assert resp.status_code == 201
    dup = client.post("/api/users", json={"login": "ivanov", "password": "password1"},
                      headers=admin_headers)
    assert dup.status_code == 409
    actions = {(a.action, a.entity) for a in db.query(AuditLog).all()}
    assert ("create", "user") in actions and ("login", "user") in actions
