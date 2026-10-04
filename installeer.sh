#!/bin/sh
# Mainframe installeren op een Mac of Linux-computer.
#
#   curl -fsSL https://slimwerken.ai/installeer/installeer.sh | sh
#   curl -fsSL https://slimwerken.ai/installeer/installeer.sh | sh -s -- --achtergrond
#
# Met --achtergrond (zo start Claude hem) draait de installer los verder en is
# dit script meteen klaar; de installatie zelf staat dan open in de browser.
#
# Wat dit doet: zorgt dat er een Python is (op de Mac via Apple's eigen
# ontwikkelgereedschap), haalt de installer op en opent hem in je browser.
# Verder niets: alle echte stappen doe je in de wizard, met uitleg erbij.
set -eu

BRONNEN="https://raw.githubusercontent.com/slimwerken/mainframe-installer/main https://slimwerken.ai/installeer"
WIZARD_ZIP="wizard-c2ed162e43.zip"
MAP="$HOME/.mainframe-installer"
ACHTERGROND=0
for arg in "$@"; do
  [ "$arg" = "--achtergrond" ] && ACHTERGROND=1
done
[ "${MF_ACHTERGROND:-0}" = "1" ] && ACHTERGROND=1

echo ""
echo "  Mainframe"
echo "  Ik zet de installer voor je klaar. Dat duurt even."
echo ""

systeem="$(uname -s)"

if [ "$systeem" = "Darwin" ]; then
  if ! xcode-select -p >/dev/null 2>&1; then
    echo "  Je Mac heeft eerst het ontwikkelgereedschap van Apple nodig."
    echo "  Er verschijnt een venster: klik op Installeer en wacht tot het klaar is."
    xcode-select --install >/dev/null 2>&1 || true
    tot=0
    until xcode-select -p >/dev/null 2>&1 && /usr/bin/python3 -c "print()" >/dev/null 2>&1; do
      sleep 10
      tot=$((tot + 10))
      if [ $tot -ge 3600 ]; then
        echo "  Het gereedschap staat er na een uur nog niet. Start deze regel opnieuw als het venster klaar is."
        exit 1
      fi
    done
    echo "  Gereedschap van Apple staat erop."
  fi
fi

PY=""
for kandidaat in python3 /usr/bin/python3 python; do
  if command -v "$kandidaat" >/dev/null 2>&1 && "$kandidaat" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then
    PY="$(command -v "$kandidaat")"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "  Er staat geen Python op deze computer."
  echo "  Linux: typ  sudo apt install -y python3 git curl unzip  en start deze regel opnieuw."
  exit 1
fi

mkdir -p "$MAP"
tijdelijk="$MAP/wizard-download.zip"
gelukt=0
for BASIS in $BRONNEN; do
  if curl -fsSL --retry 2 "$BASIS/$WIZARD_ZIP" -o "$tijdelijk"; then gelukt=1; break; fi
done
if [ "$gelukt" != "1" ]; then
  echo "  Ik kan de installer niet downloaden. Kijk of de wifi aan staat en probeer het opnieuw."
  exit 1
fi
rm -rf "$MAP/wizard.nieuw"
"$PY" -m zipfile -e "$tijdelijk" "$MAP/wizard.nieuw"
rm -rf "$MAP/wizard"
mv "$MAP/wizard.nieuw" "$MAP/wizard"
rm -f "$tijdelijk"

if [ "$ACHTERGROND" = "1" ]; then
  "$PY" "$MAP/wizard/server.py" --los
  tot=0
  until [ -s "$MAP/adres.txt" ] && [ "$MAP/adres.txt" -nt "$MAP/wizard/server.py" ]; do
    sleep 1
    tot=$((tot + 1))
    [ $tot -ge 30 ] && break
  done
  echo ""
  echo "  De installatie staat open in je browser."
  echo "  MAINFRAME_INSTALLER=$(cat "$MAP/adres.txt" 2>/dev/null)"
  exit 0
fi

echo "  De installer opent nu in je browser."
echo "  Laat dit venster open tot je klaar bent."
exec "$PY" "$MAP/wizard/server.py"
