import pytest
from fastapi.testclient import TestClient
from aura_assistant.api.app import app
from aura_assistant.services.chat_service import is_safe_external_url

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
    payload = {
        "prompt": "Hello Aura, status report",
        "channel": "text",
        "session_id": "test_audit_session"
    }
    response = client.post("/api/v1/chat/stream", json=payload, headers=headers)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "data: " in content

def test_profile_get_and_post_persistence():
    headers = {"Authorization": "Bearer aura_sec_default_change_me"}
    update_payload = {
        "name": "Lovekush Kumar",
        "headline": "Senior Software Engineer / AI Architect",
        "skills": "Python, TypeScript, React, FastAPI, NVIDIA NIM"
    }
    post_resp = client.post("/api/v1/chat/profile", json=update_payload, headers=headers)
    assert post_resp.status_code == 200
    assert post_resp.json()["ok"] is True

    get_resp = client.get("/api/v1/chat/profile", headers=headers)
    assert get_resp.status_code == 200
    profile = get_resp.json()["profile"]
    assert profile["name"] == "Lovekush Kumar"
    assert "NVIDIA NIM" in profile["skills"]

def test_ssrf_url_guard_blocks_loopback_and_private_ips():
    assert is_safe_external_url("http://127.0.0.1:8000/health") is False
    assert is_safe_external_url("http://localhost:8100/") is False
    assert is_safe_external_url("http://169.254.169.254/latest/meta-data/") is False
    assert is_safe_external_url("file:///etc/passwd") is False
