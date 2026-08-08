from fastapi.testclient import TestClient


def test_v1_root_confirms_availability(client: TestClient) -> None:
    response = client.get("/api/v1")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert "version" in body
