from fastapi.testclient import TestClient


def test_root_returns_project_info(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "SentinelAI API"
    assert body["docs_url"] == "/docs"
    assert "description" in body
    assert "version" in body
