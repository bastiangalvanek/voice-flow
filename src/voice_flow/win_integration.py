"""Windows-Taskleisten-Integration: AppUserModelID-Identitaet.

Warum dieses Modul existiert (28.06 Bastian: "Pin zeigt kein Logo"):
Eine PyQt-App, die via pythonw.exe laeuft, hat ohne eigene AppUserModelID
KEINE eigene Taskleisten-Identitaet -> Windows gruppiert sie unter pythonw.exe
und zeigt das Python-Icon. Heftet man die *laufende* App an, baut Windows einen
kaputten Pin (Python-Icon, die "-m voice_flow"-Args gehen verloren).

Der Fix hat ZWEI Haelften, die dieselbe ID teilen muessen:
  1. Prozess  -> set_process_aumid()  (VOR der ersten Fenster-Erzeugung)
  2. Shortcut -> set_shortcut_aumid()  (System.AppUserModel.ID in die .lnk)
Stimmen beide ueberein, gruppiert die laufende App sauber unter dem
angehefteten Shortcut: ein Button, scharfe Flocke, korrekter Start.

Alles reines ctypes/COM -> keine zusaetzliche Dependency (kein pywin32).
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── SSoT ────────────────────────────────────────────────────────────────
# DIESE eine Konstante ist die Identitaet. Prozess UND Shortcut beziehen sie
# von hier; nie als Magic-String duplizieren.
APP_USER_MODEL_ID = "Galvanek.VoiceFlow"


def set_process_aumid(aumid: str = APP_USER_MODEL_ID) -> bool:
    """Gibt dem laufenden Prozess eine eigene Taskleisten-Identitaet.

    Muss VOR der ersten Fenster-Erzeugung laufen. Branding-Detail -> nie hart
    fehlschlagen: No-op ausserhalb Windows / bei Fehler. Gibt Erfolg zurueck.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(aumid)
        return True
    except Exception:
        return False


def set_shortcut_aumid(lnk_path: str | Path, aumid: str = APP_USER_MODEL_ID) -> None:
    """Stempelt System.AppUserModel.ID in eine .lnk via IPropertyStore.

    WScript.Shell (PowerShell) kann nur Basis-Properties (Target/Icon) — die
    AUMID braucht das Windows Property System. Reines ctypes/COM. Raises bei
    Fehler (Setup soll LAUT scheitern, nicht still ein kaputtes Pin-Icon lassen).
    """
    if sys.platform != "win32":
        raise RuntimeError("set_shortcut_aumid laeuft nur auf Windows")

    import ctypes
    from ctypes import POINTER, byref, c_void_p, c_wchar_p, wintypes

    path = str(Path(lnk_path).resolve())
    if not Path(path).exists():
        raise FileNotFoundError(path)

    # ── COM-Strukturen ──────────────────────────────────────────────────
    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def _guid(d1: int, d2: int, d3: int, tail: tuple[int, ...]) -> GUID:
        g = GUID()
        g.Data1, g.Data2, g.Data3 = d1, d2, d3
        for i, b in enumerate(tail):
            g.Data4[i] = b
        return g

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    class PROPVARIANT(ctypes.Structure):
        # 8-Byte-Header + Union. Fuer VT_LPWSTR ist die Union ein Pointer
        # (pwszVal); zweiter Pointer fuellt die Union auf 16 Byte (x64-sicher).
        # PropVariantClear gibt den CoTaskMem-String anhand vt selbst frei.
        _fields_ = [
            ("vt", wintypes.WORD),
            ("r1", wintypes.WORD),
            ("r2", wintypes.WORD),
            ("r3", wintypes.WORD),
            ("p", c_void_p),
            ("_pad", c_void_p),
        ]

    VT_LPWSTR = 31

    # IID_IPropertyStore  {886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}
    iid_store = _guid(
        0x886D8EEB, 0x8CF2, 0x4446,
        (0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99),
    )
    # PKEY_AppUserModel_ID  {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}, pid 5
    pkey = PROPERTYKEY()
    pkey.fmtid = _guid(
        0x9F4C2855, 0x9F79, 0x4B39,
        (0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3),
    )
    pkey.pid = 5

    GPS_READWRITE = 0x00000002
    S_OK = 0

    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    # Pointer-Rueckgaben MUESSEN c_void_p sein, sonst trunkiert ctypes sie auf
    # x64 auf 32 Bit -> Crash.
    ole32.CoTaskMemAlloc.restype = c_void_p
    ole32.CoTaskMemAlloc.argtypes = [ctypes.c_size_t]

    def _check(hr: int, what: str) -> None:
        if hr != S_OK:
            raise OSError(f"{what} failed (HRESULT 0x{hr & 0xFFFFFFFF:08X})")

    ole32.CoInitialize(None)
    try:
        store = c_void_p()
        _check(
            shell32.SHGetPropertyStoreFromParsingName(
                c_wchar_p(path), None, GPS_READWRITE, byref(iid_store), byref(store)
            ),
            "SHGetPropertyStoreFromParsingName",
        )
        if not store.value:
            raise OSError("SHGetPropertyStoreFromParsingName: NULL store")

        # IPropertyStore-Vtable: [QI, AddRef, Release, GetCount, GetAt,
        #                         GetValue, SetValue(6), Commit(7)]
        obj = ctypes.cast(store.value, POINTER(c_void_p))
        vtbl = ctypes.cast(obj[0], POINTER(c_void_p))
        SetValue = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, c_void_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT)
        )(vtbl[6])
        Commit = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p)(vtbl[7])
        Release = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p)(vtbl[2])

        # PROPVARIANT(VT_LPWSTR) von Hand: CoTaskMem-Kopie des Strings, damit
        # PropVariantClear ihn sauber freigeben kann (kein manuelles Free).
        nbytes = (len(aumid) + 1) * 2  # UTF-16 inkl. NUL
        mem = ole32.CoTaskMemAlloc(nbytes)
        if not mem:
            Release(store)
            raise MemoryError("CoTaskMemAlloc fuer AUMID-String fehlgeschlagen")
        ctypes.memmove(mem, c_wchar_p(aumid), nbytes)
        pv = PROPVARIANT()
        pv.vt = VT_LPWSTR
        pv.p = mem
        try:
            _check(SetValue(store, byref(pkey), byref(pv)), "IPropertyStore::SetValue")
            _check(Commit(store), "IPropertyStore::Commit")
        finally:
            ole32.PropVariantClear(byref(pv))  # gibt mem anhand vt frei
            Release(store)
    finally:
        ole32.CoUninitialize()


def _main(argv: list[str] | None = None) -> int:
    """CLI: python -m voice_flow.win_integration set-aumid <lnk> [<lnk> ...]"""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2 or args[0] != "set-aumid":
        print("usage: python -m voice_flow.win_integration set-aumid <lnk> [<lnk> ...]")
        return 2
    rc = 0
    for lnk in args[1:]:
        try:
            set_shortcut_aumid(lnk)
            print(f"  AUMID gesetzt: {lnk} -> {APP_USER_MODEL_ID}")
        except Exception as ex:  # noqa: BLE001 - Setup-Tool, jeder Pfad einzeln melden
            print(f"  FEHLER {lnk}: {ex}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(_main())
