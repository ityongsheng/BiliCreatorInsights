"""Dictionary sentiment with a small rule / semantic boost.

Score is in [0, 1]. 0.5 is neutral (no evidence). Labels:
positive >= 0.62, negative <= 0.38, otherwise neutral.

The engine does not look up whole sentences. It scans a bundled lexicon,
applies negation and degree windows, then a few semantic boosts (取关、学到了、笑声).
"""

from __future__ import annotations

import math
import re

# Signed weights: positive > 0, negative < 0. Longer words are matched first.
_POS = {
    "好看": 1.1,
    "很好": 1.2,
    "不错": 1.1,
    "精彩": 1.1,
    "有用": 1.0,
    "清楚": 1.0,
    "喜欢": 1.0,
    "支持": 1.0,
    "感谢": 1.0,
    "舒服": 1.0,
    "干货": 1.1,
    "安利": 1.1,
    "用心": 1.0,
    "专业": 0.9,
    "好听": 1.0,
    "绝了": 1.2,
    "推荐": 1.0,
    "值得": 0.9,
    "爱了": 1.2,
    "三连": 1.0,
    "笑死": 1.0,
    "有才": 1.1,
    "清晰": 0.9,
    "流畅": 0.8,
    "优秀": 1.0,
    "厉害": 1.0,
    "快乐": 0.8,
    "治愈": 1.0,
    "感动": 1.0,
    "期待": 0.8,
    "好评": 1.0,
    "满意": 1.0,
    "实用": 1.0,
    "细致": 0.8,
    "神作": 1.3,
    "宝藏": 0.9,
    "学到": 0.8,
    "涨知识": 1.0,
    "好用": 1.0,
    "稳定": 0.6,
    "认真": 0.8,
    "真诚": 0.8,
    "漂亮": 0.9,
    "可爱": 0.8,
    "搞笑": 1.0,
    "有趣": 1.0,
    "靠谱": 1.0,
    "良心": 1.0,
    "优质": 1.0,
    "点赞": 0.8,
    "完美": 1.2,
    "出色": 1.0,
    "惊艳": 1.2,
    "真香": 1.1,
    "温暖": 0.8,
    "友好": 0.7,
    "耐心": 0.8,
    "详细": 0.8,
    "易懂": 1.0,
    "加油": 0.7,
    "强推": 1.2,
    "必看": 1.0,
    "很棒": 1.3,
    "太棒": 1.4,
    "棒": 1.0,
    "赞": 0.6,
}
_NEG = {
    "不好看": 1.3,
    "不喜欢": 1.2,
    "太差": 1.4,
    "很差": 1.3,
    "不好": 1.1,
    "拖沓": 1.2,
    "标题党": 1.3,
    "模糊": 1.0,
    "广告": 1.1,
    "恰饭": 1.2,
    "断更": 1.2,
    "乱七八糟": 1.3,
    "水文": 1.1,
    "骗人": 1.3,
    "无聊": 1.1,
    "浪费": 1.0,
    "不符": 1.0,
    "无语": 1.0,
    "垃圾": 1.4,
    "恶心": 1.4,
    "讨厌": 1.2,
    "退钱": 1.2,
    "卡顿": 1.0,
    "失望": 1.1,
    "墨迹": 1.0,
    "注水": 1.1,
    "冗长": 1.1,
    "抄袭": 1.3,
    "虚假": 1.2,
    "摆拍": 1.1,
    "误导": 1.1,
    "辣鸡": 1.3,
    "翻车": 1.0,
    "劝退": 1.2,
    "尴尬": 0.8,
    "敷衍": 1.1,
    "粗制滥造": 1.4,
    "听不清": 1.3,
    "看不下去": 1.4,
    "糟糕": 1.2,
    "差评": 1.1,
    "智商税": 1.3,
    "硬广": 1.1,
    "反感": 1.0,
    "劣质": 1.2,
    "糊弄": 1.1,
    "废话": 1.0,
    "难看": 1.2,
    "不行": 1.0,
    "鸽了": 1.2,
    "太慢": 1.1,
    "太贵": 1.2,
    "夸张": 0.8,
    "慢": 1.0,
    "贵": 1.1,
    "差": 1.0,
    "烂": 1.1,
    "难": 1.0,
}

WORDS: dict[str, float] = {}
for _w, _v in _POS.items():
    WORDS[_w] = abs(_v)
for _w, _v in _NEG.items():
    WORDS[_w] = -abs(_v)
_SORTED_WORDS = sorted(WORDS, key=len, reverse=True)

_IDIOMS = sorted(["差不多", "差点", "差别", "差距", "慢慢", "难得", "灿烂"], key=len, reverse=True)
_NEGATIONS = sorted(
    ["一点都不", "一点也不", "根本不", "并不", "不是", "不要", "没有", "不太", "从没", "别", "未", "没", "不"],
    key=len,
    reverse=True,
)
_DEGREES = sorted(
    [
        ("非常", 1.8),
        ("特别", 1.6),
        ("超级", 1.8),
        ("极其", 1.8),
        ("真的", 1.15),
        ("根本", 1.5),
        ("有点", 0.55),
        ("稍微", 0.5),
        ("略微", 0.5),
        ("太", 1.5),
        ("最", 1.6),
        ("很", 1.4),
        ("挺", 1.2),
        ("超", 1.6),
        ("贼", 1.5),
        ("略", 0.5),
        ("好", 1.25),
    ],
    key=lambda x: len(x[0]),
    reverse=True,
)
_CONTRAST = re.compile(r"但是|不过|然而|可是")
_EMO_POS = set("👍❤️💖😍😂🤣😊😁🎉🔥💯🥰")
_EMO_NEG = set("😡👎💩😤😒🤮😭")
_BOOST_BAD = re.compile(r"再也不|取关|拉黑|退订|举报")
_BOOST_GOOD = re.compile(r"学到了|学到很多|涨知识")
_BOOST_LAUGH = re.compile(r"哈{3,}|笑死")


def _starts(text: str, i: int, word: str) -> bool:
    return text.startswith(word, i)


def _score_piece(text: str) -> float:
    raw = 0.0
    pending_neg = False
    pending_deg = 1.0
    skipped = 0
    i = 0
    n = len(text)
    while i < n:
        idiom = next((w for w in _IDIOMS if _starts(text, i, w)), None)
        if idiom:
            i += len(idiom)
            pending_neg = False
            pending_deg = 1.0
            skipped = 0
            continue
        word = next((w for w in _SORTED_WORDS if _starts(text, i, w)), None)
        if word:
            weight = WORDS[word] * pending_deg
            if pending_neg:
                weight = -weight
            raw += weight
            pending_neg = False
            pending_deg = 1.0
            skipped = 0
            i += len(word)
            continue
        neg = next((w for w in _NEGATIONS if _starts(text, i, w)), None)
        if neg:
            pending_neg = True
            skipped = 0
            i += len(neg)
            continue
        deg = next((pair for pair in _DEGREES if _starts(text, i, pair[0])), None)
        if deg:
            pending_deg = deg[1]
            skipped = 0
            i += len(deg[0])
            continue
        ch = text[i]
        if ch in _EMO_POS:
            raw += 0.7
        elif ch in _EMO_NEG:
            raw -= 0.7
        i += 1
        skipped += 1
        if skipped > 8:
            pending_neg = False
            pending_deg = 1.0
            skipped = 0
    return raw


def _semantic(text: str, raw: float) -> float:
    boost = 0.0
    if _BOOST_BAD.search(text):
        boost -= 1.3
    if _BOOST_GOOD.search(text):
        boost += 0.9
    if _BOOST_LAUGH.search(text):
        boost += 0.4
    return raw + boost


def analyze_sentiment(text: str) -> dict:
    text = text or ""
    parts = _CONTRAST.split(text)
    if len(parts) > 1:
        left = _score_piece(parts[0])
        right = _score_piece("".join(parts[1:]))
        raw = 0.35 * left + 0.65 * right
    else:
        raw = _score_piece(text)
    raw = _semantic(text, raw)
    score = 1.0 / (1.0 + math.exp(-raw))
    score = round(max(0.0, min(1.0, score)), 4)
    if score >= 0.62:
        label = "positive"
    elif score <= 0.38:
        label = "negative"
    else:
        label = "neutral"
    return {"label": label, "score": score, "raw": round(raw, 4)}


def analyze_many(texts: list[str]) -> list[dict]:
    return [analyze_sentiment(t) for t in texts]
