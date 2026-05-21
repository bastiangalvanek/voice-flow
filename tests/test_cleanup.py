from voice_flow.cleanup import Cleaner


def test_cleanup_no_api_key_returns_input_unchanged():
    c = Cleaner(api_key=None)
    text, meta = c.cleanup("hello world")
    assert text == "hello world"
    assert meta == {}
    assert c.available is False


def test_cleanup_empty_text_returns_empty():
    c = Cleaner(api_key=None)
    text, meta = c.cleanup("")
    assert text == ""
    assert meta == {}


def test_cleanup_whitespace_only_text_returns_unchanged():
    c = Cleaner(api_key=None)
    text, _ = c.cleanup("   \n  ")
    assert text == "   \n  "
