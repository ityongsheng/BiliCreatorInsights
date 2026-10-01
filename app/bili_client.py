"""Polite client for Bilibili's public web APIs.

Stops on HTTP errors and non-zero business codes. A short delay is inserted
between calls. No login cookie is used.

`/x/v2/reply` is requested first, as specified. On this network it often
returns an empty shell, so the client then calls the public WBI endpoint
`/x/v2/reply/wbi/main` (hot and time order) and `/x/v2/reply/reply` for
replies. WBI signing uses the img/sub keys from `/x/web-interface/nav`.
A buvid3/buvid4 pair comes from `/x/frontend/finger/spi`; it is a device id
the site itself issues, not an account session.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
}
# Public mixin table from the bilibili web client.
_MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]


class BiliClientError(Exception):
    pass


def mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in _MIXIN_TAB)[:32]


def sign_wbi(params: dict, mixin: str, now: int | None = None) -> dict:
    signed = {k: v for k, v in params.items() if v is not None}
    signed["wts"] = str(int(now if now is not None else time.time()))

    def enc(value: object) -> str:
        return "".join(ch for ch in str(value) if ch not in "!'()*")

    items = sorted((key, enc(value)) for key, value in signed.items())
    query = urllib.parse.urlencode(items)
    digest = hashlib.md5((query + mixin).encode()).hexdigest()
    return dict(items + [("w_rid", digest)])


def parse_video(item: dict) -> dict:
    stat = item.get("stat") or {}
    owner = item.get("owner") or {}
    reply = stat.get("reply")
    if reply is None:
        reply = stat.get("comment") or 0
    return {
        "bvid": item.get("bvid") or "",
        "aid": int(item.get("aid") or 0),
        "title": item.get("title") or "",
        "author": owner.get("name") or "",
        "author_mid": int(owner.get("mid") or 0),
        "category": item.get("tname") or "",
        "tid": int(item.get("tid") or 0),
        "cover_url": item.get("pic") or "",
        "description": (item.get("desc") or "")[:2000],
        "view_count": int(stat.get("view") or 0),
        "like_count": int(stat.get("like") or 0),
        "comment_count": int(reply or 0),
        "share_count": int(stat.get("share") or 0),
        "coin_count": int(stat.get("coin") or 0),
        "favorite_count": int(stat.get("favorite") or 0),
        "pubdate": int(item.get("pubdate") or 0),
    }


def parse_reply_node(node: dict, root_rpid: int | None = None) -> list[dict]:
    if not node or not node.get("rpid"):
        return []
    rpid = int(node["rpid"])
    root = int(root_rpid or rpid)
    member = node.get("member") or {}
    content = node.get("content") or {}
    parent = int(node.get("parent") or 0)
    item = {
        "rpid": rpid,
        "root_rpid": root,
        "parent_rpid": parent,
        "text": content.get("message") or "",
        "ctime": int(node.get("ctime") or 0),
        "like": int(node.get("like") or 0),
        "rcount": int(node.get("rcount") or 0),
        "mid": int(member.get("mid") or node.get("mid") or 0),
        "uname": member.get("uname") or "",
    }
    out = [item]
    for child in node.get("replies") or []:
        out.extend(parse_reply_node(child, root))
    return out


class BiliClient:
    def __init__(self, delay: float = 0.35, timeout: float = 12.0):
        self.delay = delay
        self.timeout = timeout
        self._last = 0.0
        self._cookie = ""
        self._mixin = ""
        self._mixin_at = 0.0

    def _request(self, url: str, ok_codes: tuple[int, ...] = (0,)) -> dict:
        wait = self.delay - (time.time() - self._last)
        if self._last and wait > 0:
            time.sleep(wait)
        headers = dict(HEADERS)
        if self._cookie:
            headers["Cookie"] = self._cookie
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            self._last = time.time()
            raise BiliClientError(f"HTTP {exc.code} for {url.split('?', 1)[0]}") from exc
        except Exception as exc:
            self._last = time.time()
            raise BiliClientError(f"request failed: {exc}") from exc
        self._last = time.time()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BiliClientError("response was not JSON") from exc
        code = payload.get("code")
        if code not in ok_codes:
            raise BiliClientError(f"bilibili code {code}: {payload.get('message')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BiliClientError("bilibili response missing data")
        return data

    def _ensure_cookie(self) -> None:
        if self._cookie:
            return
        try:
            data = self._request("https://api.bilibili.com/x/frontend/finger/spi")
        except BiliClientError:
            return
        b3 = data.get("b_3") or ""
        b4 = data.get("b_4") or ""
        if b3:
            self._cookie = f"buvid3={b3}; buvid4={b4}"

    def _ensure_mixin(self) -> str:
        if self._mixin and time.time() - self._mixin_at < 1800:
            return self._mixin
        self._ensure_cookie()
        # code -101 means "not logged in" but still includes wbi_img.
        data = self._request("https://api.bilibili.com/x/web-interface/nav", ok_codes=(0, -101))
        wbi = data.get("wbi_img") or {}
        img = str(wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
        sub = str(wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
        if len(img) < 32 or len(sub) < 32:
            raise BiliClientError("wbi keys missing")
        self._mixin = mixin_key(img, sub)
        self._mixin_at = time.time()
        return self._mixin

    def _signed_url(self, base: str, params: dict) -> str:
        signed = sign_wbi(params, self._ensure_mixin())
        return base + "?" + urllib.parse.urlencode(signed)

    def fetch_popular_page(self, pn: int, ps: int = 20) -> list[dict]:
        self._ensure_cookie()
        data = self._request(f"https://api.bilibili.com/x/web-interface/popular?ps={ps}&pn={pn}")
        return [parse_video(item) for item in (data.get("list") or []) if item.get("bvid")]

    def fetch_ranking(self) -> list[dict]:
        self._ensure_cookie()
        data = self._request("https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all")
        return [parse_video(item) for item in (data.get("list") or []) if item.get("bvid")]

    def fetch_hot(self, min_count: int = 50) -> list[dict]:
        found: list[dict] = []
        seen: set[str] = set()

        def add(items: list[dict]) -> None:
            for item in items:
                bvid = item.get("bvid") or ""
                if not bvid or bvid in seen:
                    continue
                seen.add(bvid)
                found.append(item)

        for pn in range(1, 5):
            try:
                page = self.fetch_popular_page(pn)
            except BiliClientError:
                if pn == 1 and not found:
                    raise
                break
            if not page:
                break
            add(page)
            if len(found) >= min_count:
                return found
        if len(found) < min_count:
            try:
                add(self.fetch_ranking())
            except BiliClientError:
                if not found:
                    raise
        return found

    def fetch_view(self, bvid: str) -> dict:
        self._ensure_cookie()
        data = self._request(f"https://api.bilibili.com/x/web-interface/view?bvid={urllib.parse.quote(bvid)}")
        video = parse_video(data)
        if not video["bvid"]:
            video["bvid"] = bvid
        return video

    def fetch_comments(
        self,
        aid: int,
        existing_rpids: set[int],
        max_pages: int = 8,
        ps: int = 20,
        target: int = 140,
    ) -> list[dict]:
        """New comments only. Stops when a call errors after the first success."""
        self._ensure_cookie()
        collected: list[dict] = []
        seen = set(int(x) for x in existing_rpids)

        def add_nodes(nodes, root_rpid: int | None = None) -> None:
            for node in nodes or []:
                for item in parse_reply_node(node, root_rpid):
                    if item["rpid"] in seen:
                        continue
                    seen.add(item["rpid"])
                    collected.append(item)

        # Specified legacy endpoint. Often empty without being an HTTP error.
        try:
            for pn in range(1, max_pages + 1):
                data = self._request(f"https://api.bilibili.com/x/v2/reply?type=1&oid={aid}&pn={pn}&ps={ps}")
                replies = data.get("replies") or []
                if not replies:
                    break
                add_nodes(replies)
                page = data.get("page") or {}
                count = int(page.get("count") or 0)
                if count and pn * ps >= count:
                    break
                if len(collected) >= target:
                    return collected
        except BiliClientError:
            if not collected:
                pass
            else:
                return collected

        roots: list[dict] = []
        if len(collected) < target:
            for mode in (3, 2):
                try:
                    url = self._signed_url(
                        "https://api.bilibili.com/x/v2/reply/wbi/main",
                        {"oid": aid, "type": 1, "mode": mode, "ps": ps, "plat": 1, "web_location": 1315875},
                    )
                    data = self._request(url)
                except BiliClientError:
                    if not collected and mode == 3:
                        raise
                    break
                replies = data.get("replies") or []
                tops = data.get("top_replies") or []
                if not isinstance(tops, list):
                    tops = []
                add_nodes(replies)
                add_nodes(tops)
                roots.extend(replies)
                roots.extend(tops)
                if len(collected) >= target:
                    break

        seen_roots: set[int] = set()
        sub_calls = 0
        for node in roots:
            if len(collected) >= target or sub_calls >= 8:
                break
            if not node.get("rpid"):
                continue
            root_rpid = int(node["rpid"])
            if root_rpid in seen_roots or int(node.get("rcount") or 0) <= 0:
                continue
            seen_roots.add(root_rpid)
            try:
                data = self._request(
                    f"https://api.bilibili.com/x/v2/reply/reply?type=1&oid={aid}&root={root_rpid}&ps={ps}&pn=1"
                )
            except BiliClientError:
                break
            sub_calls += 1
            add_nodes(data.get("replies"), root_rpid)
        return collected
