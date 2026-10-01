"""Comment cleaning: normalize, drop ads / emoji / short text, exact user dups, SimHash near-dups."""

from __future__ import annotations

import hashlib
import re

# Hamming distance on 64-bit SimHash. A one-character tail measured distance 8;
# unrelated sentences measured about 24-30, so 8 keeps near-copies only.
NEAR_DUP_THRESHOLD = 8

_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F000-\U0001F9FF"
    "\u200d\ufe0f"
    "]+",
    flags=re.UNICODE,
)
_AD = re.compile(
    r"(加\s*微|加\s*[vV]|微\s*信\s*号|v信|薇信|优惠券|兼职|日入|免费领|点击链接|进群|扫码|返利|代购|私信我|推广链接|https?://|www\.)",
    re.IGNORECASE,
)
_SPACE = re.compile(r"\s+")
_CORE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
_PUNCT = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]+")


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.replace("\r", " ").replace("\n", " ")
    text = _SPACE.sub(" ", text).strip()
    return text


def simhash_value(text: str) -> int:
    """64-bit SimHash over Chinese character bigrams. No external dependency."""
    compact = _PUNCT.sub("", normalize_text(text))
    if len(compact) < 2:
        tokens = [compact] if compact else [" "]
    else:
        tokens = [compact[i : i + 2] for i in range(len(compact) - 1)]
    bits = 64
    acc = [0] * bits
    for tok in tokens:
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "big")
        for i in range(bits):
            if h & (1 << i):
                acc[i] += 1
            else:
                acc[i] -= 1
    out = 0
    for i, v in enumerate(acc):
        if v > 0:
            out |= 1 << i
    return out


def simhash_hex(text: str) -> str:
    return f"{simhash_value(text):016x}"


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def hamming_hex(a: str, b: str) -> int:
    return hamming(int(a, 16), int(b, 16))


def _classify(text: str) -> tuple[bool, str]:
    if not text:
        return False, "empty"
    if _AD.search(text):
        return False, "ad"
    stripped = _EMOJI.sub("", text)
    if not _CORE.search(stripped):
        return False, "emoji_or_symbol"
    if len(_CORE.findall(text)) < 3:
        return False, "too_short"
    return True, ""


def prepare_comments(records: list[dict]) -> list[dict]:
    """Annotate comment dicts in place and return them.

    Each record needs rpid, mid, text, like. Adds text_clean, is_filtered,
    filter_reason, simhash, cluster_id.
    """
    prepared: list[dict] = []
    seen_user: set[tuple[int, str]] = set()
    for rec in records:
        text = normalize_text(str(rec.get("text") or ""))
        keep, reason = _classify(text)
        rec["text_clean"] = text
        rec["simhash"] = simhash_hex(text) if text else "0" * 16
        rec["cluster_id"] = ""
        rec["is_filtered"] = not keep
        rec["filter_reason"] = reason
        if not keep:
            prepared.append(rec)
            continue
        key = (int(rec.get("mid") or 0), text)
        if key in seen_user:
            rec["is_filtered"] = True
            rec["filter_reason"] = "duplicate_user"
            prepared.append(rec)
            continue
        seen_user.add(key)
        prepared.append(rec)

    candidates = [r for r in prepared if not r["is_filtered"]]
    candidates.sort(key=lambda r: (-(int(r.get("like") or 0)), int(r.get("rpid") or 0)))
    clusters: list[tuple[int, list[dict]]] = []
    for rec in candidates:
        value = int(rec["simhash"], 16)
        placed = False
        for seed, group in clusters:
            if hamming(value, seed) <= NEAR_DUP_THRESHOLD:
                group.append(rec)
                placed = True
                break
        if not placed:
            clusters.append((value, [rec]))
    for seed, group in clusters:
        cid = f"{seed:016x}"[:16]
        group[0]["cluster_id"] = cid
        group[0]["is_filtered"] = False
        group[0]["filter_reason"] = ""
        for other in group[1:]:
            other["cluster_id"] = cid
            other["is_filtered"] = True
            other["filter_reason"] = "near_duplicate"
    return prepared
