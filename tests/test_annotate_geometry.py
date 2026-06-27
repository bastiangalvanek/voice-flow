from PIL import Image

from voice_flow.annotate import composite_strokes, map_point


def test_map_point_applies_origin_and_scale():
    # Widget-Punkt (10,20) auf Monitor mit Ursprung (1920,0), DPI-Scale 1.5
    assert map_point((10, 20), (1920, 0), (1.5, 1.5)) == (1920 + 15, 0 + 30)


def test_map_point_rounds_half_up_via_python_round():
    # round() ist banker's-rounding-neutral hier: 2.5*1 -> 2 ist egal,
    # wir pruefen nur dass int(round(...)) angewandt wird und origin addiert.
    assert map_point((4, 4), (0, 0), (1.0, 1.0)) == (4, 4)
    assert map_point((4, 4), (100, 200), (2.0, 2.0)) == (108, 208)


def test_map_point_non_uniform_scale_per_axis():
    # x und y muessen UNTERSCHIEDLICH skaliert werden (nicht-1:1-DPI).
    assert map_point((10, 20), (0, 0), (2.0, 3.0)) == (20, 60)
    # mit Origin obendrauf
    assert map_point((10, 20), (100, 5), (2.0, 3.0)) == (120, 65)


def test_composite_draws_without_error_and_keeps_size():
    img = Image.new("RGB", (200, 100), "white")
    strokes = [{"type": "pen", "color": (255, 0, 0), "width": 3,
                "points": [(5, 5), (50, 50), (80, 20)]}]
    out = composite_strokes(img, strokes, scale=(1.0, 1.0), origin=(0, 0))
    assert out.size == (200, 100)
    # Mind. ein roter Pixel auf der Linie
    assert any(px[0] > 200 and px[1] < 80 for px in out.getdata())


def test_composite_does_not_mutate_input():
    img = Image.new("RGB", (60, 60), "white")
    before = list(img.getdata())
    strokes = [{"type": "rect", "color": (0, 0, 255), "width": 4,
                "points": [(5, 5), (55, 55)]}]
    composite_strokes(img, strokes, scale=(1.0, 1.0), origin=(0, 0))
    assert list(img.getdata()) == before  # Original unveraendert


def test_composite_arrow_draws_head_and_keeps_size():
    img = Image.new("RGB", (120, 120), "white")
    strokes = [{"type": "arrow", "color": (0, 200, 0), "width": 4,
                "points": [(10, 10), (100, 100)]}]
    out = composite_strokes(img, strokes, scale=(1.0, 1.0), origin=(0, 0))
    assert out.size == (120, 120)
    # Gruene Pixel existieren (Linie + Spitze)
    assert any(px[1] > 150 and px[0] < 80 and px[2] < 80 for px in out.getdata())


def test_composite_scale_maps_widget_to_pixel():
    # Scale 2.0: Widget-Linie (0,0)->(50,0) trifft Pixelzeile y~=0 bis x~=100.
    img = Image.new("RGB", (200, 40), "white")
    strokes = [{"type": "pen", "color": (255, 0, 0), "width": 3,
                "points": [(10, 5), (50, 5)]}]
    out = composite_strokes(img, strokes, scale=(2.0, 2.0), origin=(0, 0))
    px = out.load()
    # Bei scale 2.0 liegt der Strich um Pixel-x 20..100, Pixel-y ~10.
    assert px[60, 10][0] > 200 and px[60, 10][1] < 80


def test_composite_non_uniform_scale_maps_axes_independently():
    # sx=2, sy=3: Widget-Punkt (20,10) -> Pixel (40,30). Roter Pixel dort,
    # NICHT bei (40,20) (was uniform-sy=2 erzeugen wuerde).
    img = Image.new("RGB", (120, 80), "white")
    strokes = [{"type": "pen", "color": (255, 0, 0), "width": 6,
                "points": [(20, 10)]}]
    out = composite_strokes(img, strokes, scale=(2.0, 3.0), origin=(0, 0))
    px = out.load()
    assert px[40, 30][0] > 200 and px[40, 30][1] < 80  # y bei sy=3 -> 30
    assert px[40, 20] == (255, 255, 255)               # bei sy=2 waere hier rot


def test_composite_empty_strokes_returns_copy_unchanged():
    img = Image.new("RGB", (30, 30), "white")
    out = composite_strokes(img, [], scale=(1.0, 1.0), origin=(0, 0))
    assert out.size == (30, 30)
    assert list(out.getdata()) == [(255, 255, 255)] * 900
