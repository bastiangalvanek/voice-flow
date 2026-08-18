# Voice Flow auf dem Mac — Einrichten in 5 Minuten

Diktieren mit einer Taste. Der Text landet dort, wo der Cursor steht.

---

## 1. Programm installieren

1. Auf der Seite **Releases** die Datei **`VoiceFlow-vX.Y.Z-macOS.dmg`** laden:
   https://github.com/bastiangalvanek/voice-flow/releases/latest
2. Doppelklick auf die DMG.
3. **Voice Flow** auf **Programme** ziehen.
4. DMG auswerfen (Rechtsklick → Auswerfen).

### Beim ersten Start: "Apple konnte nicht überprüfen …"

Das kommt, weil das Programm selbst gebaut und nicht bei Apple registriert ist.
Es ist kein Fehler.

**Rechtsklick auf Voice Flow → Öffnen → im Dialog nochmal Öffnen.**
Nur beim allerersten Mal nötig.

---

## 2. OpenAI-Schlüssel hinterlegen

Ohne Schlüssel gibt es keine Verschriftung. Der Schlüssel bleibt auf dem Rechner
und liegt **nicht** im Programm — deshalb ist er auch in keinem Download drin.

Terminal öffnen und diese Zeile einfügen (den Schlüssel ersetzen):

```bash
mkdir -p ~/.voice-flow && echo "OPENAI_API_KEY=sk-DEIN-SCHLUESSEL" > ~/.voice-flow/.env
```

---

## 3. Die drei Freigaben

macOS fragt bei jeder für sich. Alle drei stehen später im Voice-Flow-Fenster
unter **Freigaben & Transkripte** mit grünem oder rotem Punkt — dort siehst du
jederzeit, was fehlt.

| Freigabe | Wozu | Wo |
|---|---|---|
| **Mikrofon** | Aufnahme | Dialog beim ersten Start |
| **Bedienungshilfen** | F5/F3/F6 erkennen und Text einfügen | Systemeinstellungen → Datenschutz & Sicherheit → Bedienungshilfen |
| **Bildschirmaufnahme** | Screenshots (F3/F6) | Systemeinstellungen → Datenschutz & Sicherheit → Bildschirmaufnahme |

Nach dem Setzen einer Freigabe: **Voice Flow einmal beenden und neu starten.**

### Wenn die Bildschirmaufnahme trotz Haken nicht geht

Das passiert, wenn der Eintrag noch von einer älteren Programmfassung stammt:
der Haken steht, wirkt aber nicht. Im Voice-Flow-Fenster auf
**„Bildschirm-Freigabe reparieren"** drücken — das räumt den toten Eintrag weg
und fragt neu. Danach die App einmal neu starten.

---

## 4. Bedienung

| Taste | Was passiert |
|---|---|
| **F5** | Aufnahme starten / stoppen. Beim Stoppen wird der Text eingefügt. |
| **F3** | Screenshot vom Bildschirm unter der Maus |
| **F6** | Markieren: zeichnen, dann fotografieren |
| **ESC** | Zeichnen abbrechen |
| **Strg + Shift + Alt + Q** | Voice Flow beenden |

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

## 5. Wenn etwas fehlt

Im Voice-Flow-Fenster steht alles Wichtige:

- **Transkripte: „N ohne Text"** — Aufnahmen, deren Verschriftung nicht
  durchlief (Netz weg, Programm abgestürzt). Der Knopf **„Fehlende Transkripte
  nachholen"** holt sie nach. **Aufnahmen werden nie gelöscht**, sie liegen ein
  Jahr lang unter `~/.voice-flow/recordings/`.
- Protokoll bei Problemen: `~/.voice-flow/logs/voice-flow.log`

---

developed with ❤️ by Bastian Galvanek
