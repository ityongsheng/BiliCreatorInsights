from app.pain_points import analyze_pain_points
from app.profiles import analyze_profiles


def test_pain_points_group_negative_themes():
    comments = [
        {"text": "节奏太拖沓了，看到一半就退出", "score": 0.2, "label": "negative", "like": 10, "ctime": 100},
        {"text": "太长了，注水严重，快进到后面", "score": 0.18, "label": "negative", "like": 4, "ctime": 4600},
        {"text": "广告太多，恰饭恰得没边", "score": 0.15, "label": "negative", "like": 8, "ctime": 200},
        {"text": "这价格也太贵了", "score": 0.2, "label": "negative", "like": 3, "ctime": 300},
        {"text": "画质模糊，音质也差", "score": 0.18, "label": "negative", "like": 6, "ctime": 400},
        {"text": "内容还行，今天看完了", "score": 0.55, "label": "neutral", "like": 1, "ctime": 500},
    ]
    pains = analyze_pain_points(comments)
    themes = [p["theme"] for p in pains]
    assert "节奏" in themes
    assert "价格" in themes
    assert "质量" in themes
    assert themes == sorted(themes, key=lambda name: -next(p["priority"] for p in pains if p["theme"] == name))
    for pain in pains:
        assert pain["frequency"] >= 1
        assert 0 <= pain["negative_ratio"] <= 1
        assert 1 <= len(pain["sample_comments"]) <= 3
        assert pain["sample_comments"]


def test_profiles_cover_five_emotion_types():
    comments = [
        {"mid": 1, "uname": "甲", "text": "太好看了，支持，三连安利", "label": "positive", "score": 0.8, "like": 3, "rcount": 0},
        {"mid": 1, "uname": "甲", "text": "期待下一期，好看", "label": "positive", "score": 0.82, "like": 1, "rcount": 0},
        {"mid": 2, "uname": "乙", "text": "垃圾恶心，讨厌这种内容", "label": "negative", "score": 0.1, "like": 2, "rcount": 1},
        {"mid": 3, "uname": "丙", "text": "为什么数据这么高？难道是标题党吗", "label": "negative", "score": 0.3, "like": 1, "rcount": 0},
        {"mid": 4, "uname": "丁", "text": "建议把字幕开大，希望下次改进", "label": "neutral", "score": 0.48, "like": 1, "rcount": 0},
        {"mid": 5, "uname": "戊", "text": "今天的视频讲了三个部分", "label": "neutral", "score": 0.5, "like": 0, "rcount": 0},
    ]
    profiles = analyze_profiles(comments)
    types = {u["mid"]: u for u in profiles["users"]}
    assert types[1]["emotion_type"] == "支持型"
    assert types[2]["emotion_type"] == "讨厌型"
    assert types[3]["emotion_type"] == "质疑型"
    assert types[4]["emotion_type"] == "建议型"
    assert types[5]["emotion_type"] == "讨论型"
    for user in types.values():
        assert user["engagement_level"] in {"高", "中", "低"}
        assert "positive_ratio" in user and "negative_ratio" in user
        assert "top_keywords" in user and "style_tags" in user
    assert len(profiles["groups"]) >= 5
    assert profiles["clusters"]
