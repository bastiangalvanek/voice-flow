#!/bin/bash
# Baut aus dist/Voice Flow.app ein DMG mit dem ueblichen Installations-Fenster
# (App links, Applications-Ordner rechts, zum Hineinziehen).
#
# Aufruf:  bash build/make_dmg.sh [Version]
set -euo pipefail

VERSION="${1:-0.3.0}"
WURZEL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$WURZEL/dist/Voice Flow.app"
STAGING="$WURZEL/build_tmp/dmg"
DMG="$WURZEL/dist/VoiceFlow-$VERSION-macOS.dmg"

[ -d "$APP" ] || { echo "FEHLER: $APP fehlt — erst 'pyinstaller voice-flow.spec' laufen lassen." >&2; exit 1; }

rm -rf "$STAGING" "$DMG"
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

# Kurze Anleitung mit ins Fenster: die App ist nicht bei Apple registriert,
# der erste Start braucht deshalb Rechtsklick > Oeffnen.
cat > "$STAGING/BITTE-LESEN.txt" <<'TXT'
Voice Flow installieren
=======================
1. "Voice Flow" nach rechts in den Ordner "Applications" ziehen.
2. Im Programme-Ordner RECHTSKLICK auf Voice Flow > Oeffnen > Oeffnen.
   (Nur beim ersten Mal noetig: die App ist nicht bei Apple registriert.)
3. macOS fragt nach Mikrofon und Bedienungshilfen — beides erlauben,
   danach die App einmal neu starten. Ohne Bedienungshilfen reagieren
   die Tasten F5/F3/F6 nicht.
4. OpenAI-Schluessel hinterlegen: Datei ~/.voice-flow/.env anlegen mit
   der Zeile   OPENAI_API_KEY=sk-...

Tasten:  F5 = Aufnahme starten/stoppen · F3 = Screenshot · F6 = markieren
TXT

hdiutil create -volname "Voice Flow $VERSION" -srcfolder "$STAGING" \
  -ov -format UDZO "$DMG" >/dev/null

rm -rf "$STAGING"
echo "DMG gebaut: $DMG"
ls -lh "$DMG"
