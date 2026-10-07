import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.bootstrap import bootstrap
from app.core.db import Base, get_db
from app.core.security import hash_password
from app.main import create_app
from app.models import User
from app.models.types import Role


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    bootstrap(session)
    session.add(User(login="operator", password_hash=hash_password("operator123"),
                     role=Role.operator))
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(db: Session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _token(client: TestClient, login: str, password: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"login": login, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    return _token(client, "admin", "admin12345")


@pytest.fixture
def operator_headers(client: TestClient) -> dict[str, str]:
    return _token(client, "operator", "operator123")
