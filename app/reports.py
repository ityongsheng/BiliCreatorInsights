"""JSON, Markdown and PDF reports."""

from __future__ import annotations

import io
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_FONT_READY = False
FONT_PATH = Path(__file__).resolve().parent / "fonts" / "wqy-microhei.ttc"


def _ensure_font() -> str:
    global _FONT_READY
    if not _FONT_READY:
        pdfmetrics.registerFont(TTFont("WQY", str(FONT_PATH), subfontIndex=0))
        _FONT_READY = True
    return "WQY"


def _pct(sentiment: dict, key: str) -> str:
    return f"{float(sentiment.get(key) or 0):.1f}%"


def render_markdown(analysis: dict) -> str:
    s = analysis.get("sentiment") or {}
    lines = [
        f"# 《{analysis.get('title') or analysis.get('bvid')}》评论洞察",
        "",
        f"- bvid: `{analysis.get('bvid')}`",
        f"- 作者: {analysis.get('author') or '-'}",
        f"- 分区: {analysis.get('category') or '-'}",
        f"- 数据: {'演示数据' if analysis.get('is_demo') else 'B 站采集'}",
        "",
        "## 摘要",
        "",
        analysis.get("summary") or "",
        "",
        "## 情绪分布",
        "",
        f"- 正面 {_pct(s, 'positive_pct')}（{s.get('positive', 0)}）",
        f"- 中性 {_pct(s, 'neutral_pct')}（{s.get('neutral', 0)}）",
        f"- 负面 {_pct(s, 'negative_pct')}（{s.get('negative', 0)}）",
        f"- 平均分 {s.get('avg_score', 0)}",
        "",
        "## 热词",
        "",
    ]
    kws = (analysis.get("keywords") or {}).get("keywords") or []
    if not kws:
        lines.append("（无）")
    else:
        for k in kws:
            lines.append(f"- {k['word']}（{k['count']}，分 {k['score']}）")
    lines += ["", "## 用户画像", ""]
    groups = (analysis.get("profiles") or {}).get("groups") or []
    if not groups:
        lines.append("（无）")
    else:
        for g in groups:
            lines.append(
                f"- {g['emotion_type']} {g['count']} 人，正面占比 {g['avg_positive_ratio']}，"
                f"负面占比 {g['avg_negative_ratio']}，词：{'、'.join(g.get('top_keywords') or []) or '无'}"
            )
    lines += ["", "## 痛点", ""]
    pains = analysis.get("pain_points") or []
    if not pains:
        lines.append("（无集中痛点）")
    else:
        for p in pains:
            lines.append(
                f"### {p['theme']}（优先度 {p['priority']}，{p['frequency']} 条，负面占比 {p['negative_ratio']}）"
            )
            lines.append("")
            lines.append(p.get("root_cause") or "")
            lines.append("")
            for sample in p.get("sample_comments") or []:
                lines.append(f"> {sample}")
                lines.append("")
    lines += ["## 创作建议", ""]
    for tip in analysis.get("suggestions") or []:
        lines.append(f"- {tip}")
    if not analysis.get("suggestions"):
        lines.append("（无）")
    lines.append("")
    return "\n".join(lines)


def render_pdf(analysis: dict) -> bytes:
    font = _ensure_font()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=str(analysis.get("title") or "report"),
    )
    h1 = ParagraphStyle("h1", fontName=font, fontSize=16, leading=22, spaceAfter=8)
    h2 = ParagraphStyle("h2", fontName=font, fontSize=13, leading=18, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("body", fontName=font, fontSize=10.5, leading=16, wordWrap="CJK")
    story = []

    def add(text: str, style=body):
        story.append(Paragraph(escape(text), style))

    add(f"《{analysis.get('title') or analysis.get('bvid')}》评论洞察", h1)
    add(f"作者 {analysis.get('author') or '-'}  |  分区 {analysis.get('category') or '-'}  |  {'演示数据' if analysis.get('is_demo') else 'B 站采集'}")
    add("摘要", h2)
    add(analysis.get("summary") or "")
    s = analysis.get("sentiment") or {}
    add("情绪分布", h2)
    add(
        f"正面 {_pct(s, 'positive_pct')}，中性 {_pct(s, 'neutral_pct')}，"
        f"负面 {_pct(s, 'negative_pct')}，平均分 {s.get('avg_score', 0)}。"
    )
    add("热词", h2)
    kws = (analysis.get("keywords") or {}).get("keywords") or []
    add("、".join(k["word"] for k in kws) or "（无）")
    add("用户画像", h2)
    groups = (analysis.get("profiles") or {}).get("groups") or []
    if not groups:
        add("（无）")
    for g in groups:
        add(
            f"{g['emotion_type']} {g['count']} 人，正面 {g['avg_positive_ratio']}，"
            f"负面 {g['avg_negative_ratio']}，关键词 {'、'.join(g.get('top_keywords') or []) or '无'}"
        )
    add("痛点", h2)
    pains = analysis.get("pain_points") or []
    if not pains:
        add("（无集中痛点）")
    for p in pains:
        add(f"{p['theme']} · 优先度 {p['priority']} · {p['frequency']} 条 · 负面占比 {p['negative_ratio']}", h2)
        add(p.get("root_cause") or "")
        for sample in p.get("sample_comments") or []:
            add("例：" + sample)
    add("创作建议", h2)
    for tip in analysis.get("suggestions") or ["（无）"]:
        add("· " + tip)
    doc.build(story)
    return buf.getvalue()
