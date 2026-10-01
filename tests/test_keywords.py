from app.keywords import extract_keywords


def test_keyword_extraction_keeps_topic_words():
    texts = [
        "这期剪辑节奏拖沓，字幕也不清晰",
        "剪辑还是拖沓，节奏让人想快进",
        "希望剪辑更紧凑，节奏太慢",
        "字幕和剪辑都影响节奏",
        "大家嫌弃的是剪辑和节奏",
        "剪辑师把节奏拉得太长",
        "节奏问题比封面更明显，剪辑重复",
        "快进是因为节奏和剪辑",
    ]
    result = extract_keywords(texts, top_k=20)
    words = [item["word"] for item in result["keywords"]]
    assert len(words) <= 20
    assert "剪辑" in words[:10]
    assert "节奏" in words[:10]
    assert result["cooccurrence"]
    assert all(item["pos"][:1] in {"n", "v", "a"} for item in result["keywords"])
