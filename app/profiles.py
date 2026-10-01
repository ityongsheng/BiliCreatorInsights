"""Audience profiles from comment behavior."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from app.keywords import tokenize

_SUGGEST = ("建议", "希望", "应该", "不如", "改进", "最好", "下次", "可以试试", "麻烦")
_HATE = ("垃圾", "恶心", "讨厌", "滚", "辣鸡", "无语", "废物", "退钱", "难看", "烂")
_DOUBT = ("为什么", "难道", "是不是", "真的吗", "凭什么", "怎么会", "？", "?")
_RATIONAL = re.compile(r"因为|所以|其实|数据|逻辑|对比|分析")
_RANT = re.compile(r"哈哈|笑死|离谱|无语|绝了|蚌|乐死|吐槽")
_PRO = re.compile(r"参数|教程|原理|帧率|剪辑|构图|调色|代码|画质|音质|字幕")
_SPREAD = re.compile(r"安利|推荐|转发|三连|必看|神作")


def _emotion(text: str, pos_r: float, neg_r: float) -> str:
    hate = sum(text.count(k) for k in _HATE)
    sug = any(k in text for k in _SUGGEST)
    doubt = any(k in text for k in _DOUBT)
    if hate >= 1 and neg_r >= 0.5:
        return "讨厌型"
    if sug and neg_r < 0.7:
        return "建议型"
    if doubt and pos_r < 0.6:
        return "质疑型"
    if pos_r >= 0.55 and neg_r < 0.3:
        return "支持型"
    return "讨论型"


def _styles(text: str) -> list[str]:
    tags = []
    if _RATIONAL.search(text):
        tags.append("理性")
    if _RANT.search(text):
        tags.append("吐槽")
    if _PRO.search(text):
        tags.append("专业")
    if _SPREAD.search(text):
        tags.append("传播型")
    return tags or ["普通"]


def _kmeans(features: list[list[float]], k: int, rounds: int = 12) -> list[int]:
    n = len(features)
    if n == 0:
        return []
    k = max(1, min(k, n))
    if k == 1:
        return [0] * n
    idxs = []
    for i in range(k):
        idxs.append(round(i * (n - 1) / (k - 1)))
    # unique, stable
    seeds = []
    for i in idxs:
        if i not in seeds:
            seeds.append(i)
    centroids = [features[i][:] for i in seeds]
    k = len(centroids)
    dim = len(features[0])
    assign = [0] * n

    def dist(a, b):
        return sum((a[d] - b[d]) ** 2 for d in range(dim))

    for _ in range(rounds):
        for i, feat in enumerate(features):
            assign[i] = min(range(k), key=lambda c: dist(feat, centroids[c]))
        for c in range(k):
            members = [features[i] for i in range(n) if assign[i] == c]
            if not members:
                continue
            centroids[c] = [sum(m[d] for m in members) / len(members) for d in range(dim)]
    return assign


def analyze_profiles(comments: list[dict]) -> dict:
    by_user: dict[int, list[dict]] = defaultdict(list)
    for c in comments:
        by_user[int(c.get("mid") or 0)].append(c)
    users = []
    for mid, rows in by_user.items():
        n = len(rows)
        pos = sum(1 for r in rows if r.get("label") == "positive")
        neg = sum(1 for r in rows if r.get("label") == "negative")
        pos_r = pos / n
        neg_r = neg / n
        text = "\n".join(r.get("text") or "" for r in rows)
        likes = sum(int(r.get("like") or 0) for r in rows)
        rcount = sum(int(r.get("rcount") or 0) for r in rows)
        eng_score = n * 3 + math.log1p(likes) + rcount
        if eng_score >= 10:
            level = "高"
        elif eng_score >= 4:
            level = "中"
        else:
            level = "低"
        words = tokenize(text)
        top = [w for w, _c in Counter(words).most_common(5)]
        sug = any(k in text for k in _SUGGEST)
        doubt = any(k in text for k in _DOUBT)
        users.append(
            {
                "mid": mid,
                "uname": rows[0].get("uname") or "",
                "emotion_type": _emotion(text, pos_r, neg_r),
                "engagement_level": level,
                "engagement_score": round(eng_score, 3),
                "positive_ratio": round(pos_r, 4),
                "negative_ratio": round(neg_r, 4),
                "comment_count": n,
                "top_keywords": top,
                "style_tags": _styles(text),
                "_feat": [
                    pos_r,
                    neg_r,
                    min(eng_score / 15.0, 1.0),
                    1.0 if sug else 0.0,
                    1.0 if doubt else 0.0,
                ],
            }
        )
    users.sort(key=lambda u: (-u["engagement_score"], u["mid"]))
    groups_map: dict[str, list[dict]] = defaultdict(list)
    for u in users:
        groups_map[u["emotion_type"]].append(u)
    groups = []
    for name, members in groups_map.items():
        kw = Counter()
        styles = Counter()
        for m in members:
            kw.update(m["top_keywords"])
            styles.update(m["style_tags"])
        groups.append(
            {
                "emotion_type": name,
                "count": len(members),
                "avg_positive_ratio": round(sum(m["positive_ratio"] for m in members) / len(members), 4),
                "avg_negative_ratio": round(sum(m["negative_ratio"] for m in members) / len(members), 4),
                "top_keywords": [w for w, _c in kw.most_common(5)],
                "style_tags": [w for w, _c in styles.most_common(3)],
            }
        )
    groups.sort(key=lambda g: -g["count"])
    feats = [u["_feat"] for u in users]
    assign = _kmeans(feats, k=5)
    clusters_map: dict[int, list[dict]] = defaultdict(list)
    for u, cid in zip(users, assign):
        clusters_map[cid].append(u)
    clusters = []
    for cid, members in sorted(clusters_map.items()):
        labels = Counter(m["emotion_type"] for m in members)
        majority = labels.most_common(1)[0][0]
        clusters.append(
            {
                "cluster_id": cid,
                "size": len(members),
                "label": majority,
                "emotion_mix": dict(labels),
                "avg_positive_ratio": round(sum(m["positive_ratio"] for m in members) / len(members), 4),
                "avg_negative_ratio": round(sum(m["negative_ratio"] for m in members) / len(members), 4),
                "sample_users": [m["uname"] or str(m["mid"]) for m in members[:5]],
            }
        )
    public_users = []
    for u in users[:80]:
        item = dict(u)
        item.pop("_feat", None)
        public_users.append(item)
    return {
        "user_count": len(users),
        "users": public_users,
        "groups": groups,
        "clusters": clusters,
    }
