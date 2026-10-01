"""FastAPI entrypoint for BiliCreatorInsights."""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from app.db import init_db, open_session
from app.reports import render_markdown, render_pdf
from app.service import (
    get_task,
    get_video,
    list_comments,
    list_hot,
    load_analysis,
    start_analyze,
    task_dict,
    video_dict,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
BVID_RE = re.compile(r"^BV[0-9A-Za-z]+$")
STATIC = Path(__file__).resolve().parent / "static" / "index.html"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="BiliCreatorInsights", lifespan=lifespan)


class AnalyzeBody(BaseModel):
    bvid: str = Field(min_length=3, max_length=32)


def ok(data):
    return {"ok": True, "data": data}


def _bvid(bvid: str) -> str:
    if not BVID_RE.match(bvid):
        raise HTTPException(status_code=400, detail="invalid bvid")
    return bvid


@app.exception_handler(HTTPException)
async def http_error(_request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "request failed"
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": detail})


@app.exception_handler(RequestValidationError)
async def validation_error(_request, _exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"ok": False, "error": "invalid request"})


@app.exception_handler(Exception)
async def unexpected(_request, exc: Exception):
    logging.getLogger("bili").exception("unhandled error")
    return JSONResponse(status_code=500, content={"ok": False, "error": "internal error"})


@app.get("/")
def dashboard():
    return FileResponse(STATIC, media_type="text/html; charset=utf-8")


@app.get("/api/videos/hot")
def videos_hot(
    partition: str | None = None,
    rid: int | None = None,
    refresh: bool = False,
    limit: int = Query(60, ge=1, le=100),
):
    db = open_session()
    try:
        data = list_hot(db, partition.strip() if partition else None, rid, refresh, limit)
        return ok(data)
    finally:
        db.close()


@app.get("/api/videos/{bvid}")
def video_detail(bvid: str):
    bvid = _bvid(bvid)
    db = open_session()
    try:
        video = get_video(db, bvid)
        if video is None:
            raise HTTPException(status_code=404, detail="video not found")
        return ok(video_dict(video))
    finally:
        db.close()


@app.get("/api/videos/{bvid}/comments")
def video_comments(
    bvid: str,
    include_filtered: bool = True,
    since: int | None = None,
    until: int | None = None,
    limit: int = Query(200, ge=1, le=500),
):
    bvid = _bvid(bvid)
    db = open_session()
    try:
        if get_video(db, bvid) is None:
            raise HTTPException(status_code=404, detail="video not found")
        rows = list_comments(db, bvid, include_filtered, since, until, limit)
        return ok({"bvid": bvid, "count": len(rows), "comments": rows})
    finally:
        db.close()


def _analysis_or_404(bvid: str) -> dict:
    db = open_session()
    try:
        payload = load_analysis(db, bvid, compute=True)
        if payload is None:
            raise HTTPException(status_code=404, detail="video not found")
        return payload
    finally:
        db.close()


@app.get("/api/videos/{bvid}/analysis")
def video_analysis(bvid: str):
    return ok(_analysis_or_404(_bvid(bvid)))


@app.get("/api/videos/{bvid}/sentiment")
def video_sentiment(bvid: str):
    payload = _analysis_or_404(_bvid(bvid))
    return ok({"bvid": payload["bvid"], "sentiment": payload["sentiment"]})


@app.get("/api/videos/{bvid}/keywords")
def video_keywords(bvid: str):
    payload = _analysis_or_404(_bvid(bvid))
    return ok({"bvid": payload["bvid"], "keywords": payload["keywords"]})


@app.get("/api/videos/{bvid}/profile")
def video_profile(bvid: str):
    payload = _analysis_or_404(_bvid(bvid))
    return ok({"bvid": payload["bvid"], "profiles": payload["profiles"]})


@app.get("/api/videos/{bvid}/pain-points")
def video_pain(bvid: str):
    payload = _analysis_or_404(_bvid(bvid))
    return ok({"bvid": payload["bvid"], "pain_points": payload["pain_points"]})


@app.get("/api/videos/{bvid}/report.json")
def report_json(bvid: str):
    payload = _analysis_or_404(_bvid(bvid))
    body = __import__("json").dumps({"ok": True, "data": payload}, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{bvid}.json"'},
    )


@app.get("/api/videos/{bvid}/report.md")
def report_md(bvid: str):
    payload = _analysis_or_404(_bvid(bvid))
    text = render_markdown(payload)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{bvid}.md"'},
    )


@app.get("/api/videos/{bvid}/report.pdf")
def report_pdf(bvid: str):
    payload = _analysis_or_404(_bvid(bvid))
    blob = render_pdf(payload)
    return Response(
        content=blob,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{bvid}.pdf"'},
    )


@app.post("/api/tasks/analyze")
def create_task(body: AnalyzeBody):
    bvid = _bvid(body.bvid)
    db = open_session()
    try:
        try:
            task = start_analyze(db, bvid)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="video not found") from exc
        return ok(task_dict(task))
    finally:
        db.close()


@app.get("/api/tasks/{task_id}")
def task_status(task_id: str):
    if not re.fullmatch(r"[0-9a-fA-F]{8,64}", task_id):
        raise HTTPException(status_code=400, detail="invalid task id")
    db = open_session()
    try:
        task = get_task(db, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return ok(task_dict(task))
    finally:
        db.close()
