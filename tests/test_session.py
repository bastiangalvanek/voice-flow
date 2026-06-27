from PIL import Image

from voice_flow.session import new_session


def test_session_dir_and_bundle(tmp_path):
    s = new_session(tmp_path, "2026-06-27_14-03-22")
    assert s.dir == tmp_path / "2026-06-27_14-03-22"
    assert s.dir.exists()
    p1 = s.add_screenshot(Image.new("RGB", (10, 10), "red"))
    p2 = s.add_screenshot(Image.new("RGB", (10, 10), "blue"))
    assert p1.name == "shot_01.png" and p2.name == "shot_02.png"
    s.set_transcript("Das hier ist der Bug.")
    bundle = s.build_bundle()
    text = bundle.read_text(encoding="utf-8")
    assert "Das hier ist der Bug." in text
    assert "shot_01.png" in text and "shot_02.png" in text
    assert "—" not in text and "–" not in text  # keine KI-Striche
