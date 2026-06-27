from voice_flow.control_window import status_display


def test_status_idle():
    assert status_display("idle") == ("Bereit", "#34D399")


def test_status_recording():
    label, color = status_display("recording")
    assert label == "Aufnahme laeuft"
    assert color == "#FF453A"


def test_status_processing():
    assert status_display("processing")[0] == "Transkribiere"


def test_status_unknown_falls_back_to_idle():
    assert status_display("voellig-unbekannt") == status_display("idle")


def test_status_no_ki_dashes():
    # Keine em-/en-dashes in User-sichtbaren Labels.
    for state in ("idle", "recording", "processing", "error"):
        label, _ = status_display(state)
        assert "—" not in label and "–" not in label
