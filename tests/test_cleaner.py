from app.cleaner import NEAR_DUP_THRESHOLD, hamming_hex, prepare_comments, simhash_hex


def test_cleaner_drops_ads_emoji_short_and_near_duplicates():
    rows = [
        {"rpid": 1, "mid": 1, "text": "加微信领取优惠券，日入过千", "like": 0},
        {"rpid": 2, "mid": 1, "text": "😂😂😂👍", "like": 0},
        {"rpid": 3, "mid": 1, "text": "哈哈", "like": 0},
        {"rpid": 4, "mid": 1, "text": "。。。", "like": 0},
        {"rpid": 5, "mid": 2, "text": "这个视频剪辑很认真值得再看一遍", "like": 4},
        {"rpid": 6, "mid": 2, "text": "这个视频剪辑很认真值得再看一遍", "like": 1},
        {"rpid": 7, "mid": 3, "text": "这个视频的剪辑真的很差而且节奏非常拖沓", "like": 9},
        {"rpid": 8, "mid": 4, "text": "这个视频的剪辑真的很差而且节奏非常拖沓啊", "like": 1},
        {"rpid": 9, "mid": 5, "text": "今天去公园散步看到了海棠花开得很整齐", "like": 2},
    ]
    out = {r["rpid"]: r for r in prepare_comments(rows)}
    assert out[1]["filter_reason"] == "ad"
    assert out[2]["filter_reason"] == "emoji_or_symbol"
    assert out[3]["filter_reason"] == "too_short"
    assert out[4]["filter_reason"] == "emoji_or_symbol"
    assert out[6]["filter_reason"] == "duplicate_user"
    assert out[5]["is_filtered"] is False
    left = simhash_hex(out[7]["text_clean"])
    right = simhash_hex(out[8]["text_clean"])
    assert hamming_hex(left, left) == 0
    assert hamming_hex(left, right) <= NEAR_DUP_THRESHOLD
    assert out[8]["filter_reason"] == "near_duplicate"
    assert out[7]["is_filtered"] is False
    assert out[9]["is_filtered"] is False
    assert hamming_hex(left, simhash_hex(out[9]["text_clean"])) > NEAR_DUP_THRESHOLD
