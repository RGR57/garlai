import os

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.mark.skipif(
    os.environ.get("GARL_RUN_LIVE_LLM_TESTS") != "1",
    reason="Live provider smoke test is opt-in.",
)
def test_live_chat_hey_returns_useful_response():
    client = TestClient(app)

    response = client.post(
        "/api/v1/chat",
        json={"conversation_id": "live-hey-smoke", "message": "hey"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["response"].strip()
