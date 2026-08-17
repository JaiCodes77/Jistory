from __future__ import annotations

import time
from datetime import date, timedelta

from fastapi.testclient import TestClient

from tests.helpers import chatgpt_conversation, export_zip


def test_dashboard_time_series_is_padded_daily(client: TestClient) -> None:
    now = time.time()
    payload = export_zip(
        [
            chatgpt_conversation(conversation_id="g1", title="Grafana alert architecture", create_time=now),
            chatgpt_conversation(conversation_id="r1", title="Redis caching", create_time=now),
        ]
    )
    uploaded = client.post("/api/import/chatgpt", files={"file": ("a.zip", payload, "application/zip")})
    parsed = client.post(f"/api/import/{uploaded.json()['importId']}/parse")
    assert parsed.status_code == 200

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    series = response.json()["conversations_over_time"]
    assert len(series) >= 30

    dates = [row["date"] for row in series]
    start = date.fromisoformat(dates[0])
    expected = [(start + timedelta(days=index)).isoformat() for index in range(len(dates))]
    assert dates == expected
    assert sum(row["count"] for row in series) == 2
