from fastapi.testclient import TestClient


def test_health_without_startup():
    from app.main import app

    # No `with` block: skips lifespan, so no DB/S3 is needed for this test.
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
