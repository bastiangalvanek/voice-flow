from voice_flow import logo_loader


def test_resolve_returns_existing_logo():
    p = logo_loader.resolve_logo_path()
    assert p is not None
    assert p.exists()
    assert p.name == "logo.png"


def test_candidates_order_prefers_logo_png():
    # logo.png muss vor der Original-Flocke kommen (generiert + getrimmt).
    assert logo_loader.LOGO_CANDIDATES[0].name == "logo.png"
