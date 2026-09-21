import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.seed import reset_demo, seed_database


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    seed_database(session)
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def zoho_token(client):
    r = client.post("/api/v1/dev/token", json={"sub": "zoho-simulator", "tenant_id": "company-a", "role": "zoho-simulator"})
    return r.json()["access_token"]


@pytest.fixture
def teams_token(client):
    r = client.post("/api/v1/dev/token", json={"sub": "sales-user-01", "tenant_id": "company-a", "role": "sales-user"})
    return r.json()["access_token"]


@pytest.fixture
def scheduler_token(client):
    r = client.post("/api/v1/dev/token", json={"sub": "scheduler", "tenant_id": "company-a", "role": "scheduler"})
    return r.json()["access_token"]
