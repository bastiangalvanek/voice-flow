import shutil
import sys
from pathlib import Path

import pytest

from voice_flow import win_integration as wi


def test_aumid_is_stable_ssot():
    # Diese ID steht auch auf dem angehefteten Shortcut. Aendert sie sich, bricht
    # die Taskleisten-Gruppierung (Prozess <-> Pin matcht nicht mehr).
    assert wi.APP_USER_MODEL_ID == "Galvanek.VoiceFlow"


def test_set_process_aumid_returns_bool():
    # Branding-Detail -> nie raisen, immer True/False.
    assert isinstance(wi.set_process_aumid(), bool)


def test_cli_usage_on_bad_args(capsys):
    assert wi._main([]) == 2
    assert wi._main(["nope", "x"]) == 2
    assert "set-aumid" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32", reason="COM/Shell nur auf Windows")
def test_set_shortcut_aumid_missing_file():
    with pytest.raises(FileNotFoundError):
        wi.set_shortcut_aumid("does-not-exist.lnk")


def test_cli_reports_failure_loudly(capsys):
    # Stempel-Fehler darf nicht still durchrutschen: rc=1 + "FEHLER" sichtbar,
    # damit install.ps1 ($LASTEXITCODE) abbrechen statt "repariert" melden kann.
    rc = wi._main(["set-aumid", "does-not-exist.lnk"])
    assert rc == 1
    assert "FEHLER" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "win32", reason="COM/Shell nur auf Windows")
def test_set_shortcut_aumid_roundtrip(tmp_path):
    # Echte .lnk stempeln und via Shell.Application zuruecklesen.
    src = Path.home() / "Desktop" / "Voice Flow.lnk"
    if not src.exists():
        pytest.skip("kein Voice-Flow-Shortcut zum Testen vorhanden")
    # Zuruecklesen braucht pywin32 (nicht im Tool-venv) -> sauber skippen.
    win32com = pytest.importorskip("win32com.client")
    lnk = tmp_path / "rt.lnk"
    shutil.copy(src, lnk)

    wi.set_shortcut_aumid(lnk)

    shell = win32com.Dispatch("Shell.Application")
    item = shell.Namespace(str(lnk.parent)).ParseName(lnk.name)
    assert item.ExtendedProperty("System.AppUserModel.ID") == wi.APP_USER_MODEL_ID
