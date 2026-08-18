#!/bin/bash
# Signiert die App so, dass macOS sie ueber Updates hinweg WIEDERERKENNT.
#
# Problem (gemessen 18.08.2026): PyInstaller signiert ad-hoc, und die
# "Designated Requirement" ist dann der cdhash — also die Pruefsumme des
# Programms. Die aendert sich bei jedem Bau. Folge: die einmal erteilte
# Bedienungshilfen-Freigabe passt nach dem naechsten Update nicht mehr, der
# Haken in den Systemeinstellungen "haelt nicht".
#
# Kur: dieselbe Ad-hoc-Signatur, aber mit einer festen Anforderung — nur die
# Bundle-ID zaehlt. Damit bleibt die Identitaet ueber alle Builds gleich.
set -euo pipefail

APP="${1:-dist/Voice Flow.app}"
ID="de.galvanek.voiceflow"

[ -d "$APP" ] || { echo "FEHLER: $APP fehlt" >&2; exit 1; }

codesign --force --deep --sign - --identifier "$ID" \
  --requirements "=designated => identifier \"$ID\"" "$APP"

echo "--- Ergebnis ---"
codesign -d -r- "$APP" 2>&1 | grep designated
codesign --verify --strict "$APP" && echo "Signatur gueltig"
