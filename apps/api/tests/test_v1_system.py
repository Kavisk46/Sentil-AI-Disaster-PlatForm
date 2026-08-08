from fastapi.testclient import TestClient


def test_system_info_returns_service_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/system/info")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "SentinelAI API"
    assert body["environment"] == "development"
    assert "version" in body
