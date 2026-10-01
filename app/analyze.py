"""Assemble a full per-video analysis payload from kept comments."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.keywords import extract_keywords
from app.pain_points import analyze_pain_points
from app.profiles import analyze_profiles
from app.suggestions import build_suggestions

TZ = timezone(timedelta(hours=8))


def _distribution(comments: list[dict]) -> dict:
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    score_sum = 0.0
    buckets: dict[str, dict] = defaultdict(lambda: {"positive": 0, "neutral": 0, "negative": 0, "score_sum": 0.0, "n": 0})
    for c in comments:
        label = c.get("label") or "neutral"
        if label not in counts:
            label = "neutral"
        counts[label] += 1
        score = float(c.get("score") or 0.5)
        score_sum += score
        ctime = int(c.get("ctime") or 0)
        if ctime > 0:
            day = datetime.fromtimestamp(ctime, TZ).strftime("%Y-%m-%d")
        else:
            day = "unknown"
        b = buckets[day]
        b[label] += 1
        b["score_sum"] += score
        b["n"] += 1
    total = len(comments)
    def pct(n):
        return round(100.0 * n / total, 2) if total else 0.0
    trend = []
    for day in sorted(buckets):
        b = buckets[day]
        trend.append(
            {
                "date": day,
                "positive": b["positive"],
                "neutral": b["neutral"],
                "negative": b["negative"],
                "avg_score": round(b["score_sum"] / b["n"], 4) if b["n"] else 0.5,
            }
        )
    return {
        "total": total,
        "positive": counts["positive"],
        "neutral": counts["neutral"],
        "negative": counts["negative"],
        "positive_pct": pct(counts["positive"]),
        "neutral_pct": pct(counts["neutral"]),
        "negative_pct": pct(counts["negative"]),
        "avg_score": round(score_sum / total, 4) if total else 0.5,
        "trend": trend,
    }


def _summary(video: dict, sentiment: dict, keywords: list[dict], pains: list[dict]) -> str:
    kw = "、".join(k["word"] for k in keywords[:5]) or "（无明显关键词）"
    pain = "、".join(p["theme"] for p in pains[:3]) or "（暂无集中痛点）"
    return (
        f"《{video.get('title') or video.get('bvid')}》热度分 {float(video.get('heat_score') or 0):.2f}，"
        f"趋势分 {float(video.get('trend_score') or 0):.2f}。"
        f"有效评论 {sentiment['total']} 条，正面 {sentiment['positive_pct']:.1f}%，"
        f"中性 {sentiment['neutral_pct']:.1f}%，负面 {sentiment['negative_pct']:.1f}%，"
        f"平均情感分 {sentiment['avg_score']:.2f}。高频词：{kw}。主要痛点：{pain}。"
    )


def empty_analysis(video: dict, fetched: int = 0) -> dict:
    sentiment = _distribution([])
    return {
        "bvid": video.get("bvid"),
        "title": video.get("title") or "",
        "author": video.get("author") or "",
        "category": video.get("category") or "",
        "is_demo": bool(video.get("is_demo")),
        "stats": {
            "view_count": int(video.get("view_count") or 0),
            "like_count": int(video.get("like_count") or 0),
            "comment_count": int(video.get("comment_count") or 0),
            "share_count": int(video.get("share_count") or 0),
            "coin_count": int(video.get("coin_count") or 0),
            "favorite_count": int(video.get("favorite_count") or 0),
            "heat_score": float(video.get("heat_score") or 0),
            "trend_score": float(video.get("trend_score") or 0),
        },
        "summary": "暂无有效评论，还不能做情绪、画像和痛点分析。",
        "fetched_comments": fetched,
        "kept_comments": 0,
        "sentiment": sentiment,
        "keywords": {"keywords": [], "cooccurrence": [], "phrases": []},
        "profiles": {"user_count": 0, "users": [], "groups": [], "clusters": []},
        "pain_points": [],
        "suggestions": [],
        "generated_at": 0,
    }


def build_analysis(video: dict, kept: list[dict], fetched: int, generated_at: int) -> dict:
    if not kept:
        payload = empty_analysis(video, fetched)
        payload["generated_at"] = generated_at
        return payload
    sentiment = _distribution(kept)
    kw = extract_keywords([c.get("text") or "" for c in kept], top_k=20)
    profiles = analyze_profiles(kept)
    pains = analyze_pain_points(kept)
    suggestions = build_suggestions(sentiment, pains, kw["keywords"])
    summary = _summary(video, sentiment, kw["keywords"], pains)
    return {
        "bvid": video.get("bvid"),
        "title": video.get("title") or "",
        "author": video.get("author") or "",
        "category": video.get("category") or "",
        "is_demo": bool(video.get("is_demo")),
        "stats": {
            "view_count": int(video.get("view_count") or 0),
            "like_count": int(video.get("like_count") or 0),
            "comment_count": int(video.get("comment_count") or 0),
            "share_count": int(video.get("share_count") or 0),
            "coin_count": int(video.get("coin_count") or 0),
            "favorite_count": int(video.get("favorite_count") or 0),
            "heat_score": float(video.get("heat_score") or 0),
            "trend_score": float(video.get("trend_score") or 0),
        },
        "summary": summary,
        "fetched_comments": fetched,
        "kept_comments": len(kept),
        "sentiment": sentiment,
        "keywords": kw,
        "profiles": profiles,
        "pain_points": pains,
        "suggestions": suggestions,
        "generated_at": generated_at,
    }
