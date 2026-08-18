# Voice Flow unter Windows — Einrichten in 5 Minuten

Diktieren mit einer Taste. Der Text landet dort, wo der Cursor steht.

---

## 1. Programm installieren

1. Auf der Seite **Releases** die Datei **`VoiceFlow-X.Y.Z-Setup.exe`** laden:
   https://github.com/bastiangalvanek/voice-flow/releases/latest
2. Doppelklick. Es öffnet sich ein normales Installationsfenster auf Deutsch.
3. Durchklicken. Zwei Häkchen stehen zur Wahl:
   - **Verknüpfung auf dem Desktop** (empfohlen)
   - **Beim Anmelden starten** (praktisch, wenn du täglich diktierst)
4. Fertig. Voice Flow steht im Startmenü.

Es sind **keine Administrator-Rechte** nötig — die Installation läuft in deinem
Benutzerordner.

### „Windows hat einen unbekannten Herausgeber blockiert"

Das kommt, weil das Programm selbst gebaut und nicht bei Microsoft registriert
ist. Kein Fehler.

**Weitere Informationen → Trotzdem ausführen.**

---

## 2. OpenAI-Schlüssel hinterlegen

Ohne Schlüssel gibt es keine Verschriftung. Der Schlüssel bleibt auf dem Rechner
und liegt **nicht** im Programm — deshalb ist er auch in keinem Download drin.

Am einfachsten: **Windows-Taste + R**, das hier einfügen, Enter:

```
notepad %USERPROFILE%\.voice-flow\.env
```

Sagt Notepad, die Datei gebe es nicht: mit **Ja** anlegen. Falls auch der Ordner
fehlt, vorher einmal (Windows-Taste + R):

```
cmd /c mkdir %USERPROFILE%\.voice-flow
```

In die Datei kommt genau eine Zeile:

```
OPENAI_API_KEY=sk-DEIN-SCHLUESSEL
```

Speichern, Voice Flow starten.

---

## 3. Bedienung

| Taste | Was passiert |
|---|---|
| **F8** | Aufnahme starten / stoppen. Beim Stoppen wird der Text eingefügt. |
| **F7** | Screenshot vom Bildschirm unter der Maus |
| **F6** | Markieren: zeichnen, dann fotografieren |
| **ESC** | Zeichnen abbrechen |
| **Strg + Shift + Alt + Q** | Voice Flow beenden |

> Auf dem Mac sind es F5 und F3 — Windows hat dort andere Systemtasten.

### Der Schalter links an der Aufnahme-Pille

Er entscheidet, **wie** Screenshots beim Einfügen mitgehen:

- **Claude Code** — der Text enthält die Dateipfade der Bilder.
- **AI-Web** — die Bilder werden zusätzlich als echte Bilder eingefügt
  (ChatGPT, Claude im Browser, Lovable). Dort gibt es keine Dateipfade.

Klick auf den Schalter wechselt. Voreinstellung ist **Claude Code**.

### Der Stift rechts an der Pille

Öffnet dieselbe Zeichenleiste wie F6: Stift, Zurück, Vor, Löschen, Foto.
Gezeichnete Formen werden automatisch sauber (Kreis, Rechteck, Pfeil).
Nichts verschwindet von selbst — gelöscht wird nur über **Clear**.

---

## 4. Wenn etwas fehlt

Im Voice-Flow-Fenster steht alles Wichtige unter **Freigaben & Transkripte**:

- **Transkripte: „N ohne Text"** — Aufnahmen, deren Verschriftung nicht
  durchlief (Netz weg, Programm abgestürzt). Der Knopf **„Fehlende Transkripte
  nachholen"** holt sie nach. **Aufnahmen werden nie gelöscht**, sie liegen ein
  Jahr lang unter `%USERPROFILE%\.voice-flow\recordings\`.
- Protokoll bei Problemen: `%USERPROFILE%\.voice-flow\logs\voice-flow.log`

Die Freigabe-Zeilen (Mikrofon, Bedienungshilfen, Bildschirmaufnahme) betreffen
nur macOS und stehen unter Windows dauerhaft auf grün — Windows verlangt diese
Erlaubnisse nicht.

### Mikrofon wird nicht gefunden

Windows-Einstellungen → Datenschutz und Sicherheit → Mikrofon →
**„Apps den Zugriff auf Ihr Mikrofon erlauben"** und darunter
**„Desktop-Apps den Zugriff erlauben"** einschalten.

---

## 5. Deinstallieren

Windows-Einstellungen → Apps → **Voice Flow** → Deinstallieren.
Aufnahmen und Schlüssel unter `%USERPROFILE%\.voice-flow\` bleiben erhalten;
wer auch die weg will, löscht den Ordner von Hand.

---

developed with ❤️ by Bastian Galvanek
