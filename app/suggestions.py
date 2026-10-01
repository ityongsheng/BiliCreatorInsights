"""Concrete creator suggestions from measured sentiment and pain points."""

from __future__ import annotations


def build_suggestions(sentiment: dict, pains: list[dict], keywords: list[dict]) -> list[str]:
    themes = [p["theme"] for p in pains]
    out: list[str] = []
    if "节奏" in themes:
        out.append("开头 15 秒内给出本期结论或最有用的一步；中段每 30 到 40 秒放一个新信息点，把重复解释剪掉。")
    if "质量" in themes:
        out.append("发布前戴耳机听一遍底噪，给关键句补上字幕，封面文字和标题用同一句承诺。")
    if "内容" in themes:
        out.append("把标题里的承诺写进简介前两行，并在成片里用同样的词兑现；删掉和承诺无关的闲聊。")
    if "价格" in themes:
        out.append("广告口播单独成段并口头说明这是广告，控制在 20 秒内，前后各留一句和主题相关的信息。")
    if "互动" in themes:
        out.append("中段提一个只能用本期内容回答的问题；发布后 30 分钟内回复前 10 条高赞评论，并置顶一条汇总。")
    if "真实性" in themes:
        out.append("用一句字幕写清数据来源和拍摄条件，少用「最」「第一」「一定」这种绝对说法。")
    if "更新" in themes:
        out.append("结尾明确下次更新的星期和时间；如果要延迟，用置顶评论说明原因和新时间。")
    neg = float(sentiment.get("negative_pct") or 0)
    pos = float(sentiment.get("positive_pct") or 0)
    if neg >= 40 and themes:
        out.append(f"负面评论约占 {neg:.0f}%。下期先回应出现最多的痛点「{themes[0]}」，用一个能看出来的改动证明听进去了。")
    elif pos >= 50:
        out.append("正面反馈已经过半。下期保持同样的结构和语气，并把高赞好评里反复出现的词写进标题后半句。")
    if keywords:
        word = keywords[0]["word"]
        out.append(f"有效评论里「{word}」权重最高。下期标题或封面可以继续用这个词，但要配一个更具体的结果。")
    if not out:
        out.append("评论还没有形成集中痛点。下期维持现有结构，在结尾加一个观众可以跟着做的具体动作。")
    # de-dup while keeping order
    seen = set()
    unique = []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique[:6]
