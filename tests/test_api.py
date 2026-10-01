import time

from fastapi.testclient import TestClient

from app.db import open_session
from app.main import app
from app.service import seed_demo


def test_api_demo_endpoints_are_offline_200():
    db = open_session()
    try:
        assert seed_demo(db) >= 50
        db.commit()
    finally:
        db.close()
    client = TestClient(app)
    hot = client.get("/api/videos/hot")
    assert hot.status_code == 200
    body = hot.json()
    assert body["ok"] is True
    assert body["data"]["count"] >= 50
    assert body["data"]["source"] == "demo"
    assert all(v["is_demo"] and "演示" in v["title"] for v in body["data"]["videos"])
    game = client.get("/api/videos/hot", params={"partition": "游戏"})
    assert game.status_code == 200
    assert game.json()["data"]["videos"]
    assert all(v["category"] == "游戏" or v["tid"] == 4 for v in game.json()["data"]["videos"])
    bvid = "BV1demo0000"
    for path in (
        f"/api/videos/{bvid}",
        f"/api/videos/{bvid}/comments",
        f"/api/videos/{bvid}/analysis",
        f"/api/videos/{bvid}/sentiment",
        f"/api/videos/{bvid}/keywords",
        f"/api/videos/{bvid}/profile",
        f"/api/videos/{bvid}/pain-points",
        f"/api/videos/{bvid}/report.md",
        f"/api/videos/{bvid}/report.pdf",
        "/",
    ):
        res = client.get(path)
        assert res.status_code == 200, path
    pdf = client.get(f"/api/videos/{bvid}/report.pdf")
    assert pdf.content.startswith(b"%PDF")
    analysis = client.get(f"/api/videos/{bvid}/analysis").json()["data"]
    assert analysis["kept_comments"] > 0
    assert len(analysis["pain_points"]) >= 3
    missing = client.get("/api/videos/BVnotexist999")
    assert missing.status_code == 404
    assert missing.json()["ok"] is False
    bad = client.post("/api/tasks/analyze", json={})
    assert bad.status_code == 422
    assert bad.json()["ok"] is False
    unknown = client.post("/api/tasks/analyze", json={"bvid": "BV1demo9999"})
    assert unknown.status_code == 404
    created = client.post("/api/tasks/analyze", json={"bvid": bvid})
    assert created.status_code == 200
    task_id = created.json()["data"]["task_id"]
    status = "pending"
    for _ in range(50):
        polled = client.get(f"/api/tasks/{task_id}")
        assert polled.status_code == 200
        status = polled.json()["data"]["status"]
        if status in {"done", "failed"}:
            break
        time.sleep(0.1)
    assert status == "done"
    assert client.get("/api/tasks/deadbeef").status_code == 404
