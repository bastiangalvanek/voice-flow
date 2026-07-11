from voice_flow.transcript_quality import is_suspect_transcription


def test_real_hallucination_flagged():
    # Realfall 07.07: 12 Worte auf 266s Audio -> muss als verdaechtig gelten.
    suspect, reason = is_suspect_transcription(
        "This will be the first time. It will be the first time.", 266.0
    )
    assert suspect is True
    assert "266s" in reason


def test_normal_dictation_not_flagged():
    # ~2 Woerter/Sekunde ueber 60s = klar normal -> nicht verdaechtig.
    text = " ".join(["wort"] * 120)
    suspect, _ = is_suspect_transcription(text, 60.0)
    assert suspect is False


def test_short_clip_never_flagged():
    # Unter 8s wird nicht bewertet (zu wenig Signal) — "ja genau" auf 3s ist ok.
    suspect, _ = is_suspect_transcription("ja", 3.0)
    assert suspect is False


def test_empty_text_on_long_audio_flagged():
    suspect, _ = is_suspect_transcription("", 120.0)
    assert suspect is True


def test_slow_but_legit_speech_survives():
    # 0.6 W/s (langsam, pausenreich) liegt ueber der 0.5-Schwelle -> nicht geflaggt.
    text = " ".join(["wort"] * 60)  # 60 Worte / 100s = 0.6 W/s
    suspect, _ = is_suspect_transcription(text, 100.0)
    assert suspect is False
