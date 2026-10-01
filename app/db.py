"""SQLite persistence. The database file survives process restarts."""

from __future__ import annotations

import time

from sqlalchemy import BigInteger, Boolean, Float, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import db_path

_engine = None
_Session = None


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bvid: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    aid: Mapped[int] = mapped_column(BigInteger, default=0)
    title: Mapped[str] = mapped_column(String(512), default="")
    author: Mapped[str] = mapped_column(String(255), default="")
    author_mid: Mapped[int] = mapped_column(BigInteger, default=0)
    category: Mapped[str] = mapped_column(String(64), default="")
    tid: Mapped[int] = mapped_column(Integer, default=0)
    cover_url: Mapped[str] = mapped_column(String(1024), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    coin_count: Mapped[int] = mapped_column(Integer, default=0)
    favorite_count: Mapped[int] = mapped_column(Integer, default=0)
    heat_score: Mapped[float] = mapped_column(Float, default=0)
    trend_score: Mapped[float] = mapped_column(Float, default=0)
    pubdate: Mapped[int] = mapped_column(Integer, default=0)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class StatSnapshot(Base):
    __tablename__ = "stat_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bvid: Mapped[str] = mapped_column(String(32), index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    heat_score: Mapped[float] = mapped_column(Float, default=0)
    captured_at: Mapped[int] = mapped_column(Integer, default=0)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rpid: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    bvid: Mapped[str] = mapped_column(String(32), index=True)
    root_rpid: Mapped[int] = mapped_column(BigInteger, default=0)
    parent_rpid: Mapped[int] = mapped_column(BigInteger, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    text_clean: Mapped[str] = mapped_column(Text, default="")
    ctime: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    rcount: Mapped[int] = mapped_column(Integer, default=0)
    mid: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
    uname: Mapped[str] = mapped_column(String(255), default="")
    is_filtered: Mapped[bool] = mapped_column(Boolean, default=False)
    filter_reason: Mapped[str] = mapped_column(String(64), default="")
    simhash: Mapped[str] = mapped_column(String(32), default="")
    cluster_id: Mapped[str] = mapped_column(String(32), default="")
    sentiment_label: Mapped[str] = mapped_column(String(16), default="")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bvid: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    payload: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bvid: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[int] = mapped_column(Integer, default=0)


def _connect(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def get_engine():
    global _engine
    if _engine is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
        event.listen(_engine, "connect", _connect)
    return _engine


def open_session():
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=get_engine(), autoflush=True, autocommit=False, expire_on_commit=False)
    return _Session()


def reset_engine() -> None:
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


def init_db() -> None:
    Base.metadata.create_all(get_engine())


def now_ts() -> int:
    return int(time.time())
