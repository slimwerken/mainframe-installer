# Check mijn Mainframe - instructies voor Claude

**Ben je een mens?** Dan hoef je hier niets te doen. Plak in Claude Code, in je
Mainframe-map, de zin
`Check mijn Mainframe volgens link.slimwerken.ai/check` en Claude doet de rest.
Heb je de skill al, dan is `/check` typen genoeg.

**Ben je Claude?** De gebruiker vroeg je na te lopen of zijn Mainframe goed
geinstalleerd is. De gebruiker heeft geen technische kennis: praat kort en in gewone
taal, geen uitleg over commando's.

## Stap 1: vind de Mainframe-map

Dat is de map waarin deze sessie draait, als daar een `CLAUDE.md` en een map `.mainframe`
staan. Anders `~/Mainframe`. Twijfel je, vraag dan: "In welke map staat je Mainframe?"

## Stap 2: staat de skill er al?

Bestaat `.claude/skills/check/SKILL.md` in de Mainframe-map, volg dan die skill en stop
hier.

## Stap 3: haal het script op

Draai in de Mainframe-map:

**Mac of Linux:**

```
curl -fsSL https://raw.githubusercontent.com/slimwerken/mainframe-installer/main/check/mainframe_check.py -o overig/scripts/mainframe_check.py && python3 overig/scripts/mainframe_check.py --herstel
```

**Windows (PowerShell):**

```
irm https://raw.githubusercontent.com/slimwerken/mainframe-installer/main/check/mainframe_check.py -OutFile overig\scripts\mainframe_check.py; py overig\scripts\mainframe_check.py --herstel
```

Werkt `py` niet op Windows, gebruik dan `python`. Timeout 15 minuten.

## Stap 4: los op wat niet goed is

De uitvoer heeft per controle `GOED`, `NIET GOED` of `NIET GEMETEN`. Onder elke
`NIET GOED` staat `WIE` en `WAT NU`. Doe wat er bij `WAT NU` staat: zelf als er staat dat
Claude het oplost, samen met de gebruiker als hij zelf iets moet doen. Draai het script
daarna opnieuw, hooguit drie rondes.

## Stap 5: zeg hoe het ervoor staat

Alles goed: "Je Mainframe staat goed. Alles wat je voor de cursus nodig hebt werkt."
Nog iets open: per punt een zin wat er niet goed is en wat hij kan doen, en: "Bart ziet
dit ook, je hoeft het hem niet apart te melden."

## Regels

- Vraag of toon NOOIT een hoofdsleutel of andere sleutel in de chat. Die gaat alleen in
  het venster in de browser.
- Open, lees of toon nooit een `.env`, `.env.local` of `~/.config/mainframe/sleutel`.
- Gooi nooit iets van de gebruiker weg en overschrijf zijn eigen teksten niet.
