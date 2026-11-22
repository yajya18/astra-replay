from fastapi.testclient import TestClient


def test_health_reports_providers(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["vlm"] == {"name": "mock", "model": "mock-1", "mock": True}
    assert body["llm"]["name"] == "mock"
    assert body["mock_mode"] is True
    assert isinstance(body["ffmpeg"], bool)
    assert body["embedding"].startswith("hash")


def test_unknown_route_uses_error_shape(client: TestClient) -> None:
    res = client.get("/api/does-not-exist")
    assert res.status_code == 404
    assert res.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_cors_allows_lan_origin(client: TestClient) -> None:
    res = client.get("/api/health", headers={"Origin": "http://192.168.1.20:3000"})
    assert res.headers.get("access-control-allow-origin") == "http://192.168.1.20:3000"
