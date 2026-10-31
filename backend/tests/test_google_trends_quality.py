from app.pipeline.collectors.google_trends import is_low_quality_trend


def test_google_trends_rejects_obvious_stream_spam():
    assert is_low_quality_trend(
        "LIVE NBA stream Lakers vs Clippers free stream watch online TV channel"
    )


def test_google_trends_rejects_unicode_and_repeated_character_spam():
    assert is_low_quality_trend("((((((LIVE)))))) Lakers vs Clippers")
    assert is_low_quality_trend("𝙇𝙄𝙑𝙀 free stream Lakers basketball")


def test_google_trends_keeps_legitimate_short_topics():
    assert not is_low_quality_trend("Lakers vs Clippers")
    assert not is_low_quality_trend("Callum Turner James Bond")
    assert not is_low_quality_trend("OpenAI launches new video model")
