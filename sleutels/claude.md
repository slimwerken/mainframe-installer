# Sleutels veilig - instructies voor Claude

**Ben je een mens?** Dan hoef je hier niets te doen. Plak in Claude Code, in je
Mainframe-map, de zin
`Zet mijn sleutels veilig volgens link.slimwerken.ai/sleutels` en Claude doet de rest.
Uitleg: https://slimwerken.ai/installeer/sleutels/

**Ben je Claude?** De gebruiker vroeg je zijn Mainframe-sleutels veilig te zetten.
Doe precies dit en verder niets. De gebruiker heeft geen technische kennis: praat kort
en in gewone taal, geen uitleg over commando's.

## Stap 1: zeg wat er gebeurt

Zeg in een zin: "Ik open een venster in je browser dat je stap voor stap helpt. Dat duurt een paar minuten."

## Stap 2: vind de Mainframe-map

Dat is de map waarin deze sessie draait, als daar een `CLAUDE.md` staat. Anders
`~/Mainframe`. Twijfel je, vraag dan: "In welke map staat je Mainframe?"

## Stap 3: haal het script op en start de wizard

Draai dit op de achtergrond (het blijft draaien tot de gebruiker klaar is, maximaal
een half uur). Vervang `<map>` door het volledige pad van de Mainframe-map.

**Mac of Linux:**

```
mkdir -p ~/.config/mainframe && curl -fsSL https://slimwerken.ai/installeer/sleutels/mainframe_sleutels.py -o ~/.config/mainframe/mainframe_sleutels.py && python3 ~/.config/mainframe/mainframe_sleutels.py wizard "<map>"
```

**Windows (PowerShell):**

```
New-Item -ItemType Directory -Force "$HOME\.config\mainframe" | Out-Null; irm https://slimwerken.ai/installeer/sleutels/mainframe_sleutels.py -OutFile "$HOME\.config\mainframe\mainframe_sleutels.py"; py "$HOME\.config\mainframe\mainframe_sleutels.py" wizard "<map>"
```

Werkt `py` niet op Windows, gebruik dan `python`.

Het script schrijft een regel `De wizard staat open in je browser. Lukt dat niet, open dan: http://127.0.0.1:...`.
Zeg alleen:

"De wizard staat open in je browser. Volg daar de stappen; je hoeft hier niets te doen."

Staat de browser niet open, geef dan het adres uit die regel als klikbare link.

## Stap 4: rond af

Als het script klaar is, eindigt het met `Klaar: je sleutels zijn veilig.` Zeg dan:
"Klaar. Je sleutels zijn versleuteld en je hoofdsleutel is bewaard. Je Mainframe werkt
gewoon zoals altijd."

Eindigt het anders, zeg dan in een zin dat het nog niet af is, en dat de gebruiker de zin
later opnieuw kan plakken. Er is dan niets veranderd aan zijn bestanden.

## Regels

- Vraag de gebruiker NOOIT om de hoofdsleutel of een andere sleutel in de chat. Die gaat
  alleen in het venster in de browser. Plakt de gebruiker toch een sleutel in de chat,
  zeg dan dat hij die beter niet in een chat zet en dat het venster in de browser de
  plek is.
- Open, lees of toon nooit een `.env`, `.env.local` of `~/.config/mainframe/sleutel`.
- Doe niets anders dan deze stappen. Installeer niets extra.
- Lukt een stap niet, zeg dan eerlijk in een zin wat er misging en vraag de gebruiker
  het te melden in de community of te mailen naar bart@slimwerken.ai.
