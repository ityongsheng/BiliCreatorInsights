"""Ingest, clean, analyze, and task orchestration."""

from __future__ import annotations

import json
import logging
import threading
import uuid

from sqlalchemy import select

from app.analyze import build_analysis, empty_analysis
from app.bili_client import BiliClient, BiliClientError
from app.cleaner import prepare_comments
from app.db import Analysis, Comment, StatSnapshot, Task, Video, now_ts, open_session
from app.demo_data import demo_comments, demo_videos
from app.partitions import partition_match
from app.scoring import heat_score, trend_score
from app.sentiment import analyze_sentiment

log = logging.getLogger("bili")
LOCK = threading.RLock()
_CLIENT: BiliClient | None = None


def client() -> BiliClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = BiliClient()
    return _CLIENT


def filter_new_comments(existing: set[int], incoming: list[dict]) -> list[dict]:
    seen = set(existing)
    fresh = []
    for item in incoming:
        rpid = int(item["rpid"])
        if rpid in seen:
            continue
        seen.add(rpid)
        fresh.append(item)
    return fresh


def video_dict(v: Video) -> dict:
    return {
        "bvid": v.bvid,
        "aid": v.aid,
        "title": v.title,
        "author": v.author,
        "author_mid": v.author_mid,
        "category": v.category,
        "tid": v.tid,
        "cover_url": v.cover_url,
        "description": v.description,
        "view_count": v.view_count,
        "like_count": v.like_count,
        "comment_count": v.comment_count,
        "share_count": v.share_count,
        "coin_count": v.coin_count,
        "favorite_count": v.favorite_count,
        "heat_score": v.heat_score,
        "trend_score": v.trend_score,
        "pubdate": v.pubdate,
        "is_demo": bool(v.is_demo),
        "updated_at": v.updated_at,
    }


def comment_dict(c: Comment) -> dict:
    return {
        "rpid": c.rpid,
        "bvid": c.bvid,
        "root_rpid": c.root_rpid,
        "parent_rpid": c.parent_rpid,
        "text": c.text,
        "text_clean": c.text_clean,
        "ctime": c.ctime,
        "like": c.like_count,
        "rcount": c.rcount,
        "mid": c.mid,
        "uname": c.uname,
        "is_filtered": bool(c.is_filtered),
        "filter_reason": c.filter_reason or "",
        "sentiment_label": c.sentiment_label or "",
        "sentiment_score": c.sentiment_score or 0,
        "cluster_id": c.cluster_id or "",
    }


def _purge_demo(db) -> None:
    bvids = [row[0] for row in db.execute(select(Video.bvid).where(Video.is_demo.is_(True))).all()]
    if not bvids:
        return
    db.query(Comment).filter(Comment.bvid.in_(bvids)).delete(synchronize_session=False)
    db.query(Analysis).filter(Analysis.bvid.in_(bvids)).delete(synchronize_session=False)
    db.query(StatSnapshot).filter(StatSnapshot.bvid.in_(bvids)).delete(synchronize_session=False)
    db.query(Task).filter(Task.bvid.in_(bvids)).delete(synchronize_session=False)
    db.query(Video).filter(Video.is_demo.is_(True)).delete(synchronize_session=False)


def upsert_video(db, data: dict, is_demo: bool = False) -> Video:
    now = now_ts()
    bvid = data["bvid"]
    video = db.query(Video).filter_by(bvid=bvid).one_or_none()
    prev = (
        db.query(StatSnapshot)
        .filter_by(bvid=bvid)
        .order_by(StatSnapshot.captured_at.desc())
        .first()
    )
    prev_view = prev.view_count if prev else None
    prev_ts = prev.captured_at if prev else None
    heat = heat_score(
        data.get("view_count") or 0,
        data.get("like_count") or 0,
        data.get("coin_count") or 0,
        data.get("favorite_count") or 0,
        data.get("comment_count") or 0,
        data.get("share_count") or 0,
    )
    trend = trend_score(
        data.get("view_count") or 0,
        data.get("like_count") or 0,
        data.get("pubdate") or 0,
        now,
        prev_view,
        prev_ts,
    )
    if video is None:
        video = Video(bvid=bvid, created_at=now)
        db.add(video)
    video.aid = int(data.get("aid") or 0)
    video.title = data.get("title") or ""
    video.author = data.get("author") or ""
    video.author_mid = int(data.get("author_mid") or 0)
    video.category = data.get("category") or ""
    video.tid = int(data.get("tid") or 0)
    video.cover_url = data.get("cover_url") or ""
    video.description = data.get("description") or ""
    video.view_count = int(data.get("view_count") or 0)
    video.like_count = int(data.get("like_count") or 0)
    video.comment_count = int(data.get("comment_count") or 0)
    video.share_count = int(data.get("share_count") or 0)
    video.coin_count = int(data.get("coin_count") or 0)
    video.favorite_count = int(data.get("favorite_count") or 0)
    video.pubdate = int(data.get("pubdate") or 0)
    video.heat_score = heat
    video.trend_score = trend
    video.is_demo = bool(is_demo)
    video.updated_at = now
    if prev is None or prev.view_count != video.view_count or now - prev.captured_at >= 60:
        db.add(
            StatSnapshot(
                bvid=bvid,
                view_count=video.view_count,
                like_count=video.like_count,
                heat_score=heat,
                captured_at=now,
            )
        )
    return video


def existing_rpids(db, bvid: str) -> set[int]:
    rows = db.query(Comment.rpid).filter_by(bvid=bvid).all()
    return {int(r[0]) for r in rows}


def insert_comments(db, bvid: str, incoming: list[dict]) -> int:
    existing = existing_rpids(db, bvid)
    fresh = filter_new_comments(existing, incoming)
    for item in fresh:
        db.add(
            Comment(
                rpid=int(item["rpid"]),
                bvid=bvid,
                root_rpid=int(item.get("root_rpid") or item["rpid"]),
                parent_rpid=int(item.get("parent_rpid") or 0),
                text=item.get("text") or "",
                ctime=int(item.get("ctime") or 0),
                like_count=int(item.get("like") or 0),
                rcount=int(item.get("rcount") or 0),
                mid=int(item.get("mid") or 0),
                uname=item.get("uname") or "",
            )
        )
    return len(fresh)


def reprocess(db, bvid: str) -> dict:
    video = db.query(Video).filter_by(bvid=bvid).one()
    rows = db.query(Comment).filter_by(bvid=bvid).all()
    records = [
        {
            "rpid": c.rpid,
            "mid": c.mid,
            "text": c.text,
            "like": c.like_count,
            "_row": c,
        }
        for c in rows
    ]
    prepare_comments(records)
    kept_inputs = []
    for rec in records:
        row = rec["_row"]
        row.text_clean = rec["text_clean"]
        row.simhash = rec["simhash"]
        row.cluster_id = rec["cluster_id"]
        row.is_filtered = bool(rec["is_filtered"])
        row.filter_reason = rec["filter_reason"] or ""
        if row.is_filtered:
            row.sentiment_label = ""
            row.sentiment_score = 0
            continue
        sent = analyze_sentiment(row.text_clean)
        row.sentiment_label = sent["label"]
        row.sentiment_score = sent["score"]
        kept_inputs.append(
            {
                "rpid": row.rpid,
                "mid": row.mid,
                "uname": row.uname,
                "text": row.text_clean,
                "like": row.like_count,
                "rcount": row.rcount,
                "ctime": row.ctime,
                "label": sent["label"],
                "score": sent["score"],
            }
        )
    payload = build_analysis(video_dict(video), kept_inputs, fetched=len(rows), generated_at=now_ts())
    blob = json.dumps(payload, ensure_ascii=False)
    saved = db.query(Analysis).filter_by(bvid=bvid).one_or_none()
    if saved is None:
        saved = Analysis(bvid=bvid, payload=blob, updated_at=now_ts())
        db.add(saved)
    else:
        saved.payload = blob
        saved.updated_at = now_ts()
    return payload


def seed_demo(db) -> int:
    if db.query(Video).filter_by(is_demo=True).count() > 0:
        return 0
    videos = demo_videos()
    for item in videos:
        upsert_video(db, item, is_demo=True)
    primary = videos[0]["bvid"]
    insert_comments(db, primary, demo_comments(primary))
    reprocess(db, primary)
    return len(videos)


def ingest_popular(db) -> int:
    videos = client().fetch_hot(min_count=50)
    if not videos:
        raise BiliClientError("empty popular list")
    with LOCK:
        _purge_demo(db)
        for item in videos:
            upsert_video(db, item, is_demo=False)
        db.commit()
    return len({v["bvid"] for v in videos})


def list_hot(db, partition: str | None, rid: int | None, refresh: bool, limit: int) -> dict:
    note = None
    tried_live = False
    if refresh or db.query(Video).count() == 0:
        tried_live = True
        try:
            n = ingest_popular(db)
            note = f"已从 B 站热门写入 {n} 条视频"
        except BiliClientError as exc:
            log.warning("live ingest failed: %s", exc)
            if db.query(Video).count() == 0:
                with LOCK:
                    seed_demo(db)
                    db.commit()
                note = "B 站接口不可用或返回空列表，已加载标题带【演示】的本地样本，统计数字不是实时数据。"
            else:
                note = f"刷新失败，仍返回库里已有的数据：{exc}"
    rows = db.query(Video).order_by(Video.heat_score.desc(), Video.view_count.desc()).all()
    selected = []
    for video in rows:
        if partition_match(video.tid, video.category, partition, rid):
            selected.append(video_dict(video))
        if len(selected) >= limit:
            break
    if not selected:
        source = "empty"
    elif all(v["is_demo"] for v in selected):
        source = "demo"
    elif any(v["is_demo"] for v in selected):
        source = "mixed"
    else:
        source = "live"
    if source == "demo" and note is None:
        note = "当前是演示数据，不是 B 站实时统计。"
    return {
        "videos": selected,
        "count": len(selected),
        "stored": db.query(Video).count(),
        "source": source,
        "note": note,
        "refreshed": tried_live,
    }


def get_video(db, bvid: str) -> Video | None:
    return db.query(Video).filter_by(bvid=bvid).one_or_none()


def list_comments(db, bvid: str, include_filtered: bool, since: int | None, until: int | None, limit: int) -> list[dict]:
    q = db.query(Comment).filter_by(bvid=bvid)
    if not include_filtered:
        q = q.filter(Comment.is_filtered.is_(False))
    if since is not None:
        q = q.filter(Comment.ctime >= since)
    if until is not None:
        q = q.filter(Comment.ctime <= until)
    rows = q.order_by(Comment.ctime.desc()).limit(limit).all()
    return [comment_dict(c) for c in rows]


def load_analysis(db, bvid: str, compute: bool = True) -> dict | None:
    video = get_video(db, bvid)
    if video is None:
        return None
    saved = db.query(Analysis).filter_by(bvid=bvid).one_or_none()
    if saved and saved.payload:
        return json.loads(saved.payload)
    fetched = db.query(Comment).filter_by(bvid=bvid).count()
    if fetched == 0 or not compute:
        return empty_analysis(video_dict(video), fetched)
    with LOCK:
        payload = reprocess(db, bvid)
        db.commit()
    return payload


def _run_task(task_id: str, bvid: str) -> None:
    db = open_session()
    try:
        with LOCK:
            task = db.get(Task, task_id)
            video = db.query(Video).filter_by(bvid=bvid).one_or_none()
            if task is None or video is None:
                return
            task.status = "running"
            task.updated_at = now_ts()
            aid = video.aid
            is_demo = bool(video.is_demo)
            existing = existing_rpids(db, bvid)
            db.commit()
        view = None
        fresh: list[dict] = []
        error = ""
        if not is_demo:
            try:
                view = client().fetch_view(bvid)
            except BiliClientError as exc:
                # 热门列表里已经有统计。view 被 412 拦住时继续拉评论。
                error = f"view: {exc}"
            try:
                fresh = client().fetch_comments(aid, existing)
            except BiliClientError as exc:
                error = (error + "; " if error else "") + f"comments: {exc}"
        with LOCK:
            task = db.get(Task, task_id)
            if view:
                upsert_video(db, view, is_demo=False)
            if fresh:
                insert_comments(db, bvid, fresh)
            stored = db.query(Comment).filter_by(bvid=bvid).count()
            if error and stored == 0:
                task.status = "failed"
                task.error = error[:500]
                task.updated_at = now_ts()
                db.commit()
                return
            reprocess(db, bvid)
            task.status = "done"
            task.error = error[:500] if error else ""
            task.updated_at = now_ts()
            db.commit()
    except Exception as exc:
        log.exception("task %s failed", task_id)
        db.rollback()
        task = db.get(Task, task_id)
        if task is not None:
            task.status = "failed"
            task.error = str(exc)[:500]
            task.updated_at = now_ts()
            db.commit()
    finally:
        db.close()


def start_analyze(db, bvid: str) -> Task:
    video = get_video(db, bvid)
    if video is None:
        if bvid.startswith("BV1demo"):
            raise KeyError(bvid)
        try:
            data = client().fetch_view(bvid)
        except BiliClientError as exc:
            raise KeyError(str(exc)) from exc
        with LOCK:
            upsert_video(db, data, is_demo=False)
            db.commit()
    task = Task(id=uuid.uuid4().hex, bvid=bvid, status="pending", error="", created_at=now_ts(), updated_at=now_ts())
    with LOCK:
        db.add(task)
        db.commit()
    threading.Thread(target=_run_task, args=(task.id, bvid), daemon=True).start()
    return task


def get_task(db, task_id: str) -> Task | None:
    return db.get(Task, task_id)


def task_dict(task: Task) -> dict:
    return {
        "task_id": task.id,
        "bvid": task.bvid,
        "status": task.status,
        "error": task.error or "",
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
