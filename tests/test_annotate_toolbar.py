from voice_flow.annotate_toolbar import (
    PALETTE,
    TOOLBAR_W,
    ToolbarItem,
    build_toolbar,
    hit_test,
)


def _layout(h=1080):
    return build_toolbar(viewport_h=h)


def test_toolbar_has_all_actions():
    items = _layout()
    kinds = {it.kind for it in items}
    # Tools + Farben + Aktionen
    assert {"tool", "color", "action"} <= kinds
    tools = {it.value for it in items if it.kind == "tool"}
    assert tools == {"pen", "arrow", "rect"}
    actions = {it.value for it in items if it.kind == "action"}
    assert {"undo", "clear", "shoot", "cancel"} <= actions


def test_toolbar_color_count_matches_palette():
    items = _layout()
    colors = [it for it in items if it.kind == "color"]
    assert len(colors) == len(PALETTE)


def test_items_are_vertically_stacked_non_overlapping():
    items = _layout()
    ys = [(it.y, it.y + it.size) for it in items]
    ys.sort()
    for (top, bottom), (ntop, _nb) in zip(ys, ys[1:]):
        assert bottom <= ntop  # keine Ueberlappung


def test_toolbar_is_vertically_centered_region():
    items = _layout(h=1000)
    top = min(it.y for it in items)
    bottom = max(it.y + it.size for it in items)
    center = (top + bottom) / 2
    # grob in der Bildschirmmitte (Toleranz 1px Rundung)
    assert abs(center - 500) <= 2


def test_hit_test_finds_item_inside_button():
    items = _layout()
    target = items[3]
    cx = target.x + target.size // 2
    cy = target.y + target.size // 2
    hit = hit_test((cx, cy), items)
    assert hit is target


def test_hit_test_outside_toolbar_returns_none():
    items = _layout()
    assert hit_test((TOOLBAR_W + 500, 500), items) is None


def test_toolbar_item_is_immutable_dataclass_like():
    it = ToolbarItem(kind="tool", value="pen", x=1, y=2, size=40)
    assert it.kind == "tool" and it.value == "pen"
    assert it.x == 1 and it.y == 2 and it.size == 40
