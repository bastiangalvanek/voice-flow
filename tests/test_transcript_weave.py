from voice_flow.transcript_weave import weave_screenshot_markers

S = "Das ist Satz eins. Das ist Satz zwei."
M1 = "(siehe shot_01 im Bucket: C:\\x\\shot_01.png)"
M2 = "(siehe shot_02 im Bucket: C:\\x\\shot_02.png)"


def test_capture_mittig_zwischen_zwei_saetzen():
    # offset=5 / duration=10 -> ratio 0.5, 2 Saetze -> idx=1 -> nach Satz 1.
    out = weave_screenshot_markers(S, [(5.0, M1)], 10.0)
    assert out == f"Das ist Satz eins. {M1} Das ist Satz zwei."


def test_capture_am_anfang():
    out = weave_screenshot_markers(S, [(0.0, M1)], 10.0)
    assert out == f"{M1} Das ist Satz eins. Das ist Satz zwei."
    # Marker steht vor jedem Satztext.
    assert out.index(M1) < out.index("Das ist Satz eins.")


def test_capture_am_ende():
    out = weave_screenshot_markers(S, [(10.0, M1)], 10.0)
    assert out == f"Das ist Satz eins. Das ist Satz zwei. {M1}"


def test_capture_jenseits_ende_wird_geclamped():
    out = weave_screenshot_markers(S, [(99.0, M1)], 10.0)
    assert out.endswith(M1)
    assert out == f"Das ist Satz eins. Das ist Satz zwei. {M1}"


def test_zwei_captures_richtige_reihenfolge():
    # M2 frueh (anfang), M1 spaet (ende) -> Reihenfolge nach Position im Text.
    out = weave_screenshot_markers(S, [(9.0, M1), (0.0, M2)], 10.0)
    assert out == f"{M2} Das ist Satz eins. Das ist Satz zwei. {M1}"
    assert out.index(M2) < out.index(M1)


def test_zwei_captures_selbe_grenze_offset_reihenfolge():
    # Beide mittig (ratio 0.5) -> selber Slot, in offset-Reihenfolge: erst 4.0 dann 5.0.
    a = "(A)"
    b = "(B)"
    out = weave_screenshot_markers(S, [(5.0, b), (4.0, a)], 10.0)
    assert out == f"Das ist Satz eins. {a} {b} Das ist Satz zwei."


def test_duration_null_keine_division_marker_am_ende():
    out = weave_screenshot_markers(S, [(3.0, M1)], 0.0)
    assert out == f"Das ist Satz eins. Das ist Satz zwei. {M1}"


def test_leerer_text_nur_marker():
    out = weave_screenshot_markers("   ", [(2.0, M1)], 10.0)
    assert out == M1


def test_keine_captures_text_unveraendert():
    assert weave_screenshot_markers(S, [], 10.0) == S
    assert weave_screenshot_markers(S, [], 0.0) == S


def test_single_satz_ohne_satzende():
    out = weave_screenshot_markers("nur ein fragment ohne punkt", [(5.0, M1)], 10.0)
    # 1 Satz, ratio 0.5 -> idx=round(0.5)=0 (banker's rounding 0.5->0) -> Marker vorne.
    assert M1 in out
    assert "nur ein fragment ohne punkt" in out


def test_kein_ki_gedankenstrich_eingefuegt():
    out = weave_screenshot_markers(S, [(5.0, M1)], 10.0)
    assert "—" not in out  # em-dash
    assert "–" not in out  # en-dash


def test_keine_doppelten_leerzeichen():
    out = weave_screenshot_markers(S, [(5.0, M1)], 10.0)
    assert "  " not in out
