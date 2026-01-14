import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.src.core.database import get_db, Base, engine
from unittest.mock import MagicMock

# ----- Mock DB nếu muốn ----- #
mock_session = MagicMock()

def override_get_db():
    try:
        yield mock_session
    finally:
        pass

# override dependency (chỉ dùng cho unit test mock)
app.dependency_overrides[get_db] = override_get_db

# ----- Tạo bảng rỗng cho integration test ----- #
@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    # tạo bảng 1 lần cho toàn bộ session
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

# ----- TestClient ----- #
@pytest.fixture(scope="session")
def client():
    return TestClient(app)
