"""Heat and trend scores.

热度分 heat（约 0~8，播放量再大也会被对数压住）：

    heat = 0.40 * log10(1+view) + 0.22 * log10(1+like) + 0.12 * log10(1+coin)
         + 0.12 * log10(1+favorite) + 0.08 * log10(1+reply) + 0.06 * log10(1+share)

权重偏向播放和点赞；投币、收藏代表认可，评论和分享代表讨论与传播。
对数是为了避免百万播放把互动项完全淹没。

趋势分 trend：

    若存在上一次快照（view_prev, t_prev）：
        hours = max((now - t_prev) / 3600, 0.05)
        velocity = max(view - view_prev, 0) / hours
    否则用发布后的平均增速近似（没有历史时的首次抓取）：
        hours = max((now - pubdate) / 3600, 0.5)
        velocity = view / hours
    trend = log10(1 + velocity) * (1 + 5 * like / max(view, 1))

velocity 是每小时播放增量（或首次的平均每小时播放）。
后面的点赞率放大“涨得快而且被认可”的视频。再次对数压缩，避免头部数值过大。
"""

from __future__ import annotations

import math


def heat_score(
    view: int,
    like: int,
    coin: int = 0,
    favorite: int = 0,
    reply: int = 0,
    share: int = 0,
) -> float:
    view = max(int(view or 0), 0)
    like = max(int(like or 0), 0)
    coin = max(int(coin or 0), 0)
    favorite = max(int(favorite or 0), 0)
    reply = max(int(reply or 0), 0)
    share = max(int(share or 0), 0)
    score = (
        0.40 * math.log10(1 + view)
        + 0.22 * math.log10(1 + like)
        + 0.12 * math.log10(1 + coin)
        + 0.12 * math.log10(1 + favorite)
        + 0.08 * math.log10(1 + reply)
        + 0.06 * math.log10(1 + share)
    )
    return round(score, 4)


def trend_score(
    view: int,
    like: int,
    pubdate: int,
    now: int,
    prev_view: int | None = None,
    prev_ts: int | None = None,
) -> float:
    view = max(int(view or 0), 0)
    like = max(int(like or 0), 0)
    now = int(now)
    if prev_view is not None and prev_ts is not None and now > int(prev_ts):
        hours = max((now - int(prev_ts)) / 3600.0, 0.05)
        velocity = max(view - int(prev_view), 0) / hours
    else:
        pub = int(pubdate or 0)
        if pub <= 0 or pub >= now:
            hours = 0.5
        else:
            hours = max((now - pub) / 3600.0, 0.5)
        velocity = view / hours
    like_rate = like / max(view, 1)
    score = math.log10(1 + velocity) * (1 + 5 * like_rate)
    return round(score, 4)
