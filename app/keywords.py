"""TF-IDF + TextRank keywords, POS-filtered with jieba.posseg."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

import jieba.posseg as pseg

# Nouns / verbs / adjectives (jieba flags start with n, v, a).
_STOP = {
    "一个", "这个", "那个", "什么", "怎么", "为什么", "如果", "因为", "所以", "但是",
    "然后", "就是", "还是", "觉得", "感觉", "真的", "视频", "这期", "一期", "我们",
    "你们", "他们", "自己", "这样", "那样", "已经", "可以", "不是", "没有", "不会",
    "不能", "以及", "还有", "比较", "非常", "特别", "知道", "看到", "出来", "开始",
    "最后", "其实", "可能", "应该", "一下", "一点", "一些", "一种", "这种", "那种",
    "这里", "那里", "这么", "那么", "多少", "几个", "东西", "时候", "评论", "大家",
    "现在", "今天", "明天", "昨天", "一个", "没有", "不是", "还是", "就是", "这个",
    "真的", "感觉", "觉得", "知道", "需要", "进行", "通过", "以及", "或者", "还是",
    "他们", "她们", "它们", "咱们", "一下", "一点", "不是", "不会", "不要", "一下",
    "上来", "下去", "起来", "出来", "进去", "过来", "过去", "就是", "还是", "只是",
    "但是", "不过", "然后", "因为", "所以", "如果", "虽然", "而且", "或者", "以及",
    "这个", "那个", "这些", "那些", "这里", "那里", "这样", "那样", "怎么", "什么",
    "哪里", "哪个", "多少", "几个", "有点", "一些", "一下", "一种", "一样", "一直",
    "已经", "还是", "还有", "没有", "不是", "不会", "不能", "不要", "别的", "其他",
    "自己", "什么", "怎么", "视频", "这期", "一期", "b站", "B站", "up", "UP",
}

_KEEP_PREFIX = ("n", "v", "a")


def _keep(flag: str) -> bool:
    return bool(flag) and flag[0] in _KEEP_PREFIX


def tokenize(text: str) -> list[str]:
    words: list[str] = []
    flags: list[str] = []
    for pair in pseg.cut(text or ""):
        word = pair.word.strip()
        if len(word) < 2:
            continue
        if word in _STOP:
            continue
        if not _keep(pair.flag):
            continue
        if not re.search(r"[\u4e00-\u9fff]", word):
            continue
        words.append(word)
        flags.append(pair.flag)
    return words


def tokenize_with_pos(text: str) -> list[tuple[str, str]]:
    out = []
    for pair in pseg.cut(text or ""):
        word = pair.word.strip()
        if len(word) < 2 or word in _STOP or not _keep(pair.flag):
            continue
        if not re.search(r"[\u4e00-\u9fff]", word):
            continue
        out.append((word, pair.flag))
    return out


def _tfidf(docs: list[list[str]]) -> Counter:
    df: Counter = Counter()
    tfs: list[Counter] = []
    for tokens in docs:
        c = Counter(tokens)
        tfs.append(c)
        df.update(c.keys())
    n = max(len(docs), 1)
    scores: Counter = Counter()
    for c in tfs:
        total = sum(c.values()) or 1
        for word, cnt in c.items():
            tf = cnt / total
            idf = math.log((n + 1) / (df[word] + 1)) + 1.0
            scores[word] += tf * idf
    return scores


def _textrank(docs: list[list[str]], window: int = 4, iters: int = 20, damping: float = 0.85) -> dict[str, float]:
    graph: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for tokens in docs:
        for i, word in enumerate(tokens):
            for j in range(i + 1, min(len(tokens), i + window)):
                other = tokens[j]
                if other == word:
                    continue
                graph[word][other] += 1.0
                graph[other][word] += 1.0
    nodes = list(graph)
    if not nodes:
        return {}
    score = {n: 1.0 for n in nodes}
    for _ in range(iters):
        nxt = {}
        for node in nodes:
            incoming = 0.0
            for src, weight in graph[node].items():
                total = sum(graph[src].values()) or 1.0
                incoming += (weight / total) * score[src]
            nxt[node] = (1 - damping) + damping * incoming
        score = nxt
    return score


def _norm(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    peak = max(scores.values()) or 1.0
    return {k: v / peak for k, v in scores.items()}


def extract_keywords(texts: list[str], top_k: int = 20) -> dict:
    docs: list[list[str]] = []
    pos_of: dict[str, str] = {}
    counts: Counter = Counter()
    for text in texts:
        pairs = tokenize_with_pos(text)
        tokens = [w for w, _f in pairs]
        docs.append(tokens)
        counts.update(tokens)
        for w, f in pairs:
            pos_of.setdefault(w, f)
    tfidf = _tfidf(docs)
    rank = _textrank(docs)
    nt = _norm(tfidf)
    nr = _norm(rank)
    vocab = set(nt) | set(nr)
    combined = []
    for word in vocab:
        combined.append(
            {
                "word": word,
                "score": round(0.5 * nt.get(word, 0.0) + 0.5 * nr.get(word, 0.0), 4),
                "tfidf": round(float(tfidf.get(word, 0.0)), 4),
                "textrank": round(float(rank.get(word, 0.0)), 4),
                "pos": pos_of.get(word, ""),
                "count": int(counts.get(word, 0)),
            }
        )
    combined.sort(key=lambda x: (-x["score"], -x["count"], x["word"]))
    keywords = combined[:top_k]
    top_words = {k["word"] for k in keywords}
    pair_counts: Counter = Counter()
    for tokens in docs:
        for i, word in enumerate(tokens):
            if word not in top_words:
                continue
            for j in range(i + 1, min(len(tokens), i + 5)):
                other = tokens[j]
                if other not in top_words or other == word:
                    continue
                pair = tuple(sorted((word, other)))
                pair_counts[pair] += 1
    cooccurrence = [
        {"a": a, "b": b, "count": int(c)}
        for (a, b), c in pair_counts.most_common(20)
    ]
    phrases: Counter = Counter()
    for tokens in docs:
        for i in range(len(tokens) - 1):
            if tokens[i] in top_words and tokens[i + 1] in top_words:
                phrases[tokens[i] + tokens[i + 1]] += 1
    phrase_list = [{"phrase": p, "count": int(c)} for p, c in phrases.most_common(10) if c >= 2]
    return {"keywords": keywords, "cooccurrence": cooccurrence, "phrases": phrase_list}
