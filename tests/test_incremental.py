from app.db import Comment, open_session
from app.service import existing_rpids, filter_new_comments, insert_comments, upsert_video


def test_incremental_comment_ids_skip_existing():
    db = open_session()
    try:
        upsert_video(
            db,
            {
                "bvid": "BV1test0001",
                "aid": 1,
                "title": "t",
                "author": "a",
                "author_mid": 1,
                "category": "生活",
                "tid": 21,
                "cover_url": "",
                "description": "",
                "view_count": 100,
                "like_count": 10,
                "comment_count": 2,
                "share_count": 1,
                "coin_count": 1,
                "favorite_count": 1,
                "pubdate": 1,
            },
            is_demo=True,
        )
        first = [
            {"rpid": 101, "text": "第一条评论内容", "ctime": 10, "like": 1, "rcount": 0, "mid": 7, "uname": "u"},
            {"rpid": 102, "text": "第二条评论内容", "ctime": 11, "like": 2, "rcount": 0, "mid": 8, "uname": "v"},
        ]
        assert insert_comments(db, "BV1test0001", first) == 2
        db.commit()
        existing = existing_rpids(db, "BV1test0001")
        incoming = [
            {"rpid": 102, "text": "第二条评论内容", "ctime": 11, "like": 2, "rcount": 0, "mid": 8, "uname": "v"},
            {"rpid": 103, "text": "第三条新增评论", "ctime": 12, "like": 0, "rcount": 1, "mid": 9, "uname": "w"},
        ]
        fresh = filter_new_comments(existing, incoming)
        assert [c["rpid"] for c in fresh] == [103]
        assert insert_comments(db, "BV1test0001", incoming) == 1
        db.commit()
        stored = sorted(r[0] for r in db.query(Comment.rpid).all())
        assert stored == [101, 102, 103]
    finally:
        db.close()


def test_wbi_sign_is_deterministic():
    from app.bili_client import mixin_key, sign_wbi

    mixin = mixin_key("a" * 32, "b" * 32)
    assert len(mixin) == 32
    first = sign_wbi({"oid": 99, "type": 1}, mixin, now=1700000000)
    second = sign_wbi({"type": 1, "oid": 99}, mixin, now=1700000000)
    assert first == second
    assert len(first["w_rid"]) == 32
