import pytest
from fastapi.testclient import TestClient
from aura_assistant.api.app import app

client = TestClient(app)

def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["version"] == "3.5.0"
    assert "vram_status" in data

def test_unauthenticated_request_rejected():
    response = client.get("/api/v1/workspace/tree")
    assert response.status_code == 401

def test_authenticated_tree_request():
    headers = {"Authorization": "Bearer aura_sec_default_change_me"}
    response = client.get("/api/v1/workspace/tree", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "files" in data

def test_chat_stream_endpoint():
    headers = {"Authorization": "Bearer aura_sec_default_change_me"}
    payload = {"prompt": "Hello Aura, status report", "channel": "text"}
    response = client.post("/api/v1/chat/stream", json=payload, headers=headers)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "data: " in content
