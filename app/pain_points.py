"""Group negative comments into pain-point themes."""

from __future__ import annotations

THEMES: dict[str, tuple[str, ...]] = {
    "内容": ("内容", "剧情", "选题", "水文", "无聊", "干货", "废话", "信息量", "抄袭", "标题党"),
    "节奏": ("节奏", "拖沓", "太长", "太短", "注水", "快进", "冗长", "铺垫", "太快", "墨迹"),
    "互动": ("互动", "回复", "评论区", "抽奖", "弹幕", "置顶", "不回"),
    "质量": ("画质", "音质", "剪辑", "字幕", "模糊", "制作", "收音", "清晰", "卡顿", "封面"),
    "价格": ("价格", "贵", "便宜", "广告", "恰饭", "推广", "会员", "收费", "软广", "智商税"),
    "真实性": ("骗人", "虚假", "摆拍", "不实", "夸张", "标题党"),
    "更新": ("更新", "鸽", "断更", "催更"),
}

ROOT_CAUSE = {
    "内容": "选题或信息密度和标题承诺不一致，观众觉得没拿到预期内容。",
    "节奏": "信息点之间拖沓，或者跳得太快，观看时要快进或跟不上。",
    "互动": "评论和反馈没有被接住，观众缺少参与感。",
    "质量": "画质、收音、字幕或剪辑完成度影响理解。",
    "价格": "口播广告或价格信息偏硬，观众对恰饭和性价比敏感。",
    "真实性": "案例、数据或标题被怀疑夸张、摆拍或不实。",
    "更新": "更新不稳定，追更的预期被打断。",
    "其他": "负面意见比较散，需要直接看原句。",
}


def _themes_for(text: str) -> list[str]:
    hits = []
    for name, words in THEMES.items():
        if any(w in text for w in words):
            hits.append(name)
    return hits


def analyze_pain_points(comments: list[dict]) -> list[dict]:
    """comments: text, score, label, like, ctime."""
    buckets: dict[str, list[dict]] = {name: [] for name in list(THEMES) + ["其他"]}
    for c in comments:
        text = c.get("text") or ""
        hits = _themes_for(text)
        if not hits:
            if c.get("label") == "negative":
                buckets["其他"].append(c)
            continue
        for name in hits:
            buckets[name].append(c)
    pains = []
    for name, rows in buckets.items():
        if not rows:
            continue
        negatives = [r for r in rows if r.get("label") == "negative" or float(r.get("score") or 0.5) <= 0.38]
        if not negatives:
            continue
        freq = len(negatives)
        neg_ratio = freq / len(rows)
        scores = [float(r.get("score") or 0.0) for r in negatives]
        avg = sum(scores) / len(scores)
        samples = sorted(negatives, key=lambda r: -int(r.get("like") or 0))[:3]
        ctimes = [int(r.get("ctime") or 0) for r in negatives if int(r.get("ctime") or 0) > 0]
        if len(ctimes) >= 2:
            duration = round((max(ctimes) - min(ctimes)) / 3600.0, 2)
        else:
            duration = 0.0
        priority = round(freq * (1 + (0.5 - min(avg, 0.5))), 4)
        pains.append(
            {
                "theme": name,
                "frequency": freq,
                "mention_count": len(rows),
                "negative_ratio": round(neg_ratio, 4),
                "avg_score": round(avg, 4),
                "sample_comments": [r.get("text") or "" for r in samples],
                "duration_hours": duration,
                "priority": priority,
                "root_cause": ROOT_CAUSE.get(name, ROOT_CAUSE["其他"]),
            }
        )
    pains.sort(key=lambda p: (-p["priority"], -p["frequency"], p["theme"]))
    return pains
