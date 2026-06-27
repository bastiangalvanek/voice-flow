from voice_flow.notifications import ToastKind, stack_positions, style_for, truncate


def test_style_for_known_kinds():
    s = style_for(ToastKind.SCREENSHOT)
    assert s["icon"] == "cam"
    assert s["accent"].startswith("#") and len(s["accent"]) == 7


def test_style_for_unknown_falls_back_to_info():
    # Enum erzwingt gueltige Werte; Fallback-Pfad trotzdem deterministisch.
    assert style_for(ToastKind.INFO)["icon"] == "info"


def test_truncate_long_title():
    assert truncate("x" * 100, 40) == "x" * 40 + "…"
    assert truncate("kurz", 40) == "kurz"
    assert truncate("zeile1\nzeile2", 40) == "zeile1 zeile2"


def test_stack_positions_top_right_newest_on_top():
    screen = (0, 0, 1920, 1080)
    pos = stack_positions([84, 84], screen, margin=20, gap=12, width=360)
    assert pos[0][0] == 1540 and pos[1][0] == 1540   # 1920-360-20
    assert pos[0][1] == 20                            # neuester oben
    assert pos[1][1] == 20 + 84 + 12


def test_stack_positions_variable_heights():
    # Erster Toast 120px (mit Actions), zweiter 64px -> zweiter startet nach 120+gap.
    screen = (0, 0, 1920, 1080)
    pos = stack_positions([120, 64], screen, margin=20, gap=12, width=360)
    assert pos[0][1] == 20
    assert pos[1][1] == 20 + 120 + 12


def test_stack_positions_second_monitor_origin():
    screen = (1920, 0, 1920, 1080)
    pos = stack_positions([84], screen, margin=20, gap=12, width=360)
    assert pos[0][0] == 1920 + 1920 - 360 - 20       # rechtsbuendig Monitor 2


def test_stack_positions_empty():
    assert stack_positions([], (0, 0, 1920, 1080), 20, 12, 360) == []
