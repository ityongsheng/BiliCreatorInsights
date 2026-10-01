"""Common Bilibili partition ids used by the hot-list filter.

Names map to a parent tid plus frequently seen child tids. Filtering by the
parent rid (the first id) includes children; filtering by a child rid matches
that tid only. Filtering by category name matches tname or any mapped tid.
"""

from __future__ import annotations

# parent tid is the first element
PARTITIONS: dict[str, list[int]] = {
    "动画": [1, 24, 25, 47, 86, 210, 27],
    "番剧": [13, 33, 32, 51, 152],
    "国创": [167, 153, 168, 169, 195],
    "音乐": [3, 28, 29, 30, 31, 59, 130, 193, 243, 244],
    "舞蹈": [129, 20, 154, 156, 198],
    "游戏": [4, 17, 171, 172, 65, 173, 121, 136, 19],
    "知识": [36, 201, 124, 228, 207, 208, 209, 229, 122],
    "科技": [188, 95, 230, 231, 232, 233],
    "运动": [234, 235, 164, 236, 237, 238],
    "汽车": [223, 245, 246, 247, 240, 248],
    "生活": [160, 138, 21, 76, 75, 161, 162, 163, 174, 239],
    "美食": [211, 76],
    "动物圈": [217, 218, 219, 220, 221, 222],
    "鬼畜": [119, 22, 26, 126, 127, 216],
    "时尚": [155, 157, 158, 159, 192],
    "资讯": [202, 203, 204, 205, 206],
    "娱乐": [5, 71, 137, 241, 242],
    "影视": [181, 182, 183, 85],
    "纪录片": [177, 37, 178, 179, 180],
}

PARENT_TIDS = {tids[0] for tids in PARTITIONS.values()}


def expand_rid(rid: int) -> set[int]:
    for tids in PARTITIONS.values():
        if rid == tids[0]:
            return set(tids)
    return {rid}


def partition_match(tid: int | None, category: str | None, partition: str | None, rid: int | None) -> bool:
    if partition is None and rid is None:
        return True
    tid = int(tid) if tid is not None else None
    name = (category or "").strip()
    ok_rid = True
    ok_name = True
    if rid is not None:
        ok_rid = tid is not None and tid in expand_rid(int(rid))
    if partition:
        wanted = partition.strip()
        tids = PARTITIONS.get(wanted)
        ok_name = name == wanted or (tids is not None and tid in tids)
    if partition and rid is not None:
        return ok_rid and ok_name
    if rid is not None:
        return ok_rid
    return ok_name
