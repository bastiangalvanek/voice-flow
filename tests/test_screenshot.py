from voice_flow.screenshot import pick_monitor

# mss-Format: monitors[0] = virtual all-screen, ab [1] echte Monitore.
MONS = [
    {"left": 0, "top": 0, "width": 3840, "height": 1080},    # [0] virtuell
    {"left": 0, "top": 0, "width": 1920, "height": 1080},     # [1] links
    {"left": 1920, "top": 0, "width": 1920, "height": 1080},  # [2] rechts
]


def test_cursor_on_right_monitor():
    assert pick_monitor((2500, 400), MONS) == MONS[2]


def test_cursor_on_left_monitor():
    assert pick_monitor((100, 400), MONS) == MONS[1]


def test_cursor_outside_falls_back_to_first_real():
    assert pick_monitor((99999, 99999), MONS) == MONS[1]
