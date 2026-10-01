from app.sentiment import analyze_sentiment
from app.sentiment_samples import LABELED_SAMPLES


def test_labeled_sample_accuracy():
    assert len(LABELED_SAMPLES) >= 30
    wrong = []
    for text, expected in LABELED_SAMPLES:
        pred = analyze_sentiment(text)
        assert 0.0 <= pred["score"] <= 1.0
        if pred["label"] != expected:
            wrong.append((text, expected, pred))
    accuracy = (len(LABELED_SAMPLES) - len(wrong)) / len(LABELED_SAMPLES)
    assert accuracy >= 0.75, {"accuracy": accuracy, "wrong": wrong}
    neutral = analyze_sentiment("今天的视频讲了三个部分")
    assert abs(neutral["score"] - 0.5) < 0.12
