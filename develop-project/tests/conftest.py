from fastapi.testclient import TestClient
import pytest
from app.main import app



@pytest.fixture(scope="session")
def client():
    client = TestClient(app)
    client.get("/")
    return client
