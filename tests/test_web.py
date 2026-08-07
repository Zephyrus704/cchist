# SPDX-License-Identifier: MIT
"""Web API 测试。需要 httpx(TestClient)。"""
import pytest

pytest.importorskip("httpx")
pytest.importorskip("fastapi")


@pytest.fixture
def client(fake_claude):
    from fastapi.testclient import TestClient
    from cchist.web.server import app
    return TestClient(app)


def test_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "cchist" in r.text


def test_stats(client):
    s = client.get("/api/stats").json()
    assert s["total"] == 3
    assert s["trivial"] == 1
    assert s["orphan"] == 1


def test_sessions_list(client):
    d = client.get("/api/sessions").json()
    assert d["count"] == 3
    assert "project_label" in d["sessions"][0]


def test_sessions_search(client):
    d = client.get("/api/sessions?q=快速排序").json()
    assert d["count"] == 1


def test_session_detail(client):
    d = client.get("/api/sessions").json()
    sid = next(s["session_id"] for s in d["sessions"] if s["session_id"].startswith("aaaa"))
    det = client.get(f"/api/session/{sid}").json()
    assert len(det["messages"]) == 4
    assert "claude --resume" in det["resume_cmd"]


def test_favorite_endpoint(client):
    d = client.get("/api/sessions").json()
    sid = d["sessions"][0]["session_id"]
    r = client.post(f"/api/session/{sid}/favorite").json()
    assert r["favorite"] is True


def test_trash_and_restore_endpoint(client):
    d = client.get("/api/sessions").json()
    sid = next(s["session_id"] for s in d["sessions"] if s["session_id"].startswith("aaaa"))
    assert client.post(f"/api/session/{sid}/trash").json()["ok"]
    assert client.get("/api/sessions").json()["count"] == 2
    assert client.post(f"/api/session/{sid}/restore").json()["ok"]
    assert client.get("/api/sessions").json()["count"] == 3


def test_daily_endpoint(client):
    d = client.get("/api/daily").json()
    assert "daily" in d


def test_export_endpoint(client):
    d = client.get("/api/sessions").json()
    sid = next(s["session_id"] for s in d["sessions"] if s["session_id"].startswith("aaaa"))
    r = client.get(f"/api/session/{sid}/export")
    assert r.status_code == 200
    assert "快速排序" in r.text


def test_cleanup_endpoint(client):
    before = client.get("/api/sessions").json()["count"]
    r = client.post("/api/cleanup").json()
    assert r["cleaned"] >= 2   # bbbb 空 + cccc 孤儿
    after = client.get("/api/sessions").json()["count"]
    assert after == before - r["cleaned"]
