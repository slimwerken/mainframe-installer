#!/usr/bin/env python3
"""Staat je Mainframe goed? Meet alles na, repareert wat zonder jou kan, en zegt wat er nog moet.

WAAROM (Bart, 12 november 2026). In week 1 van de novembergroep liepen leden op negen
verschillende plekken vast in de installatie, en Bart hoorde het pas als iemand het hem
vertelde. Soms sloeg de installer een stap stil over (Sleutels veilig) en merkte het lid dat
pas lessen later. Dit script is de controle aan het eind van week 1, en daarna zo vaak als
je wilt: het meet op je eigen computer of alles er staat en werkt.

    python3 overig/scripts/mainframe_check.py              # meten, rapport, doorgeven aan Slim Werken
    python3 overig/scripts/mainframe_check.py --herstel    # eerst repareren wat een script veilig kan
    python3 overig/scripts/mainframe_check.py --json       # het rapport als JSON
    python3 overig/scripts/mainframe_check.py --niet-melden

Wat hij doorgeeft aan Slim Werken (zodat Bart ziet wie vastzit voor je hoeft te mailen): je
licentiecode, Mac/Windows/Linux, de versie van je app, en per controle goed of niet goed met
een regel uitleg. Nooit bestanden, nooit sleutels, nooit de inhoud van je Mainframe.

De skill /check draait dit script en laat Claude oplossen wat het script niet kan. Bij elke
controle die niet goed is staat daarom een regel WAT NU, geschreven voor Claude.

Alleen de standaardbibliotheek, Python 3.9+, Mac, Windows en Linux. Een controle die zelf
omvalt telt als "kon ik niet meten" en houdt de rest nooit tegen.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

THUIS = Path.home()
SERVER = os.environ.get("MAINFRAME_SERVER") or "https://api.slimwerken.ai"
USER_AGENT = "Mainframe-check/1.0 (+https://slimwerken.ai/installeer)"
CREATE_NO_WINDOW = 0x08000000  # Windows: geen zwart venster bij een hulpprogramma
VSCODE_BYPASS = {"claudeCode.allowDangerouslySkipPermissions": True,
                 "claudeCode.initialPermissionMode": "bypassPermissions"}
SYNC_NAMEN = ("onedrive", "icloud", "clouddocs", "dropbox", "google drive", "googledrive", "my drive",
              "mijn drive", "box sync", "pcloud", "sync.com", "nextcloud", "owncloud", "mega")
KERNSKILLS = ("update", "einde", "app", "vragen")

GOED, FOUT, ONBEKEND = "goed", "fout", "onbekend"


# ---------- klein gereedschap ----------

def systeem() -> str:
    naam = platform.system().lower()
    return "mac" if naam == "darwin" else "windows" if naam.startswith("win") else "linux"


def _vlaggen() -> dict:
    return {"creationflags": CREATE_NO_WINDOW} if systeem() == "windows" else {}


def draai(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> tuple[int, str]:
    """Een opdracht draaien zonder venster. Geeft (exitcode, uitvoer); 127 als hij niet start."""
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace", **_vlaggen())
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "duurde te lang"
    except (OSError, subprocess.SubprocessError) as fout:
        return 127, type(fout).__name__


def vind(naam: str) -> str | None:
    """Een programma zoeken, ook op de plekken waar de installer het neerzet."""
    gevonden = shutil.which(naam)
    if gevonden:
        return gevonden
    exe = ".exe" if systeem() == "windows" else ""
    for plek in (THUIS / ".local" / "bin", THUIS / ".bun" / "bin", THUIS / ".cargo" / "bin",
                 Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        for kandidaat in (plek / (naam + exe), plek / naam):
            if kandidaat.is_file():
                return str(kandidaat)
    return None


def http_json(url: str, data: dict, timeout: int = 20) -> dict:
    """POST met JSON. Eerst curl (gebruikt de certificaten van de computer zelf), dan urllib:
    bij een lid op Windows viel een kale urllib-download om terwijl curl wel werkte (12 nov 2026)."""
    body = json.dumps(data).encode("utf-8")
    curl = shutil.which("curl")
    if curl:
        with tempfile.TemporaryDirectory() as td:
            invoer = Path(td) / "in.json"
            invoer.write_bytes(body)
            code, uit = draai([curl, "-sS", "-L", "--max-time", str(timeout), "-A", USER_AGENT,
                               "-H", "Content-Type: application/json", "--data-binary", f"@{invoer}", url],
                              timeout=timeout + 5)
            if code == 0 and uit.strip().startswith("{"):
                return json.loads(uit[uit.index("{"):uit.rindex("}") + 1])
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def mainframe_map(arg: str | None = None) -> Path:
    """De Mainframe-map: wat je meegeeft, anders twee mappen boven dit script, anders waar je nu staat."""
    if arg:
        return Path(arg).expanduser().resolve()
    hier = Path(__file__).resolve()
    if hier.parent.name == "scripts" and hier.parent.parent.name == "overig":
        return hier.parents[2]
    for kandidaat in (Path.cwd(), THUIS / "Mainframe", THUIS / "Mainframe-2"):
        if (kandidaat / "CLAUDE.md").exists() and (kandidaat / ".mainframe").exists():
            return kandidaat
    return Path.cwd()


def licentie(m: Path) -> dict:
    try:
        lic = json.loads((m / ".mainframe" / "licentie.json").read_text(encoding="utf-8"))
        return lic if isinstance(lic, dict) else {}
    except (OSError, ValueError):
        return {}


def python() -> list[str]:
    return [sys.executable]


# ---------- de uitkomst van een controle ----------

def uitkomst(id_: str, naam: str, status: str, uitleg: str = "", ernst: str = "kern",
             door: str = "", wat_nu: str = "") -> dict:
    """door: wie het oplost als het niet goed is: 'script' (--herstel), 'claude' of 'lid'."""
    return {"id": id_, "naam": naam, "status": status, "uitleg": uitleg, "ernst": ernst,
            "door": door if status == FOUT else "", "wat_nu": wat_nu if status == FOUT else ""}


# ---------- de controles ----------

def check_map(m: Path) -> dict:
    naam = "Je Mainframe-map is compleet"
    mist = [p for p in ("CLAUDE.md", "VERSIES.md", ".claude/settings.json", "kennis", "overig/scripts",
                        ".mainframe/licentie.json") if not (m / p).exists()]
    if not mist:
        return uitkomst("map", naam, GOED, str(m))
    return uitkomst("map", naam, FOUT, "Dit ontbreekt in " + str(m) + ": " + ", ".join(mist), door="claude",
                    wat_nu="Draai `python3 overig/scripts/mainframe_update.py` (Windows: py) om aan te vullen wat "
                           "ontbreekt. Ontbreekt .mainframe/licentie.json of het updatescript zelf, zeg dan dat het lid "
                           "de installatie opnieuw start via slimwerken.ai/installeer en dezelfde map kiest: die vult "
                           "alleen aan wat ontbreekt en overschrijft niets.")


def gedeelde_map(m: Path) -> str | None:
    tekst = str(m).lower().replace("\\", "/")
    if str(m).startswith("\\\\") or tekst.startswith("//"):
        return "een netwerkschijf"
    for naam in SYNC_NAMEN:
        if naam in tekst:
            return {"clouddocs": "iCloud Drive", "icloud": "iCloud Drive", "onedrive": "OneDrive",
                    "googledrive": "Google Drive", "google drive": "Google Drive", "my drive": "Google Drive",
                    "mijn drive": "Google Drive"}.get(naam, naam.title())
    if "/library/cloudstorage/" in tekst or "/library/mobile documents/" in tekst:
        return "een cloudmap"
    if systeem() == "mac":
        # Bureaublad en Documenten in iCloud: alleen een echte koppeling telt, niet de kopie die
        # macOS laat staan nadat je het uitzet (melding Leendert, 11 nov 2026).
        for naam in ("Desktop", "Documents"):
            p = THUIS / naam
            try:
                if p.is_symlink() and "mobile documents" in str(p.resolve()).lower():
                    m.relative_to(p)
                    return "iCloud Drive (Bureaublad en Documenten staan in iCloud)"
            except (ValueError, OSError):
                pass
    return None


def check_plek(m: Path) -> dict:
    naam = "Je Mainframe staat op deze computer zelf"
    waarom = gedeelde_map(m)
    if not waarom:
        return uitkomst("plek", naam, GOED)
    return uitkomst("plek", naam, FOUT, f"Je Mainframe staat in {waarom}. Dat geeft dubbele en kapotte bestanden.",
                    door="claude",
                    wat_nu="Leg uit dat een Mainframe nooit in een gedeelde of gesynchroniseerde map hoort, en verhuis "
                           "hem samen met het lid naar een map op de computer zelf (bijvoorbeeld ~/Mainframe): sluit de "
                           "app (/app stop), kopieer de hele map, controleer dat alles er staat, en open daarna de "
                           "nieuwe map in VS Code. Gooi de oude map niet weg; dat doet het lid zelf als alles werkt.")


def check_licentie(m: Path) -> tuple[dict, dict | None]:
    """Geeft de uitkomst plus het antwoord van de server (welke onderdelen open staan), of None."""
    naam = "Je licentie klopt"
    lic = licentie(m)
    if not lic.get("code") or not lic.get("email"):
        return uitkomst("licentie", naam, FOUT, "Er staat geen licentiecode in deze map.", door="lid",
                        wat_nu="Zeg dat het lid de installatie opnieuw start via slimwerken.ai/installeer met zijn "
                               "licentiecode en dezelfde map. Zijn code vindt hij op slimwerken.ai/mainframecode."), None
    try:
        antwoord = http_json(f"{SERVER}/licentie/v-sloten", {"code": lic["code"], "email": lic["email"]})
    except Exception as fout:  # geen internet is geen fout van het lid
        return uitkomst("licentie", naam, ONBEKEND, f"Kon de server niet bereiken ({type(fout).__name__})."), None
    if antwoord.get("ok"):
        return uitkomst("licentie", naam, GOED), antwoord
    reden = str(antwoord.get("reden") or "onbekend")
    if reden == "email_mismatch":
        return uitkomst("licentie", naam, FOUT, "Het e-mailadres in deze map hoort niet bij je code.", door="claude",
                        wat_nu="Draai `python3 overig/scripts/mainframe_update.py --ander-adres` (Windows: py); dat "
                               "koppelt het adres van het lid aan zijn code."), None
    return uitkomst("licentie", naam, FOUT, f"De server herkent deze code niet ({reden}).", door="lid",
                    wat_nu="Zeg dat het lid zijn code controleert op slimwerken.ai/mainframecode en het meldt in de "
                           "community als de code daar wel klopt."), None


def check_gereedschap() -> dict:
    naam = "De basisprogramma's staan erop"
    mist = [n for n in ("git", "bun") if not vind(n)]
    if not mist:
        return uitkomst("gereedschap", naam, GOED)
    return uitkomst("gereedschap", naam, FOUT, "Niet gevonden: " + ", ".join(mist), door="claude",
                    wat_nu="Installeer wat ontbreekt. Bun: `python3 overig/scripts/mainframe_app.py start "
                           "--installeer-bun` (Windows: py). Git: op de Mac `xcode-select --install`, op Windows "
                           "`winget install --id Git.Git -e --source winget`, op Linux via het pakketbeheer.")


def claude_pad() -> str | None:
    return vind("claude")


def check_claude() -> dict:
    naam = "Claude Code is ingelogd"
    c = claude_pad()
    if not c:
        return uitkomst("claude", naam, FOUT, "Claude Code staat niet op deze computer.", door="lid",
                        wat_nu="Zeg dat het lid de installatie opnieuw start via slimwerken.ai/installeer; de stap "
                               "Claude zet Claude Code neer.")
    code, uit = draai([c, "auth", "status", "--json"], timeout=30)
    if code in (124, 127):
        return uitkomst("claude", naam, ONBEKEND, "Claude Code gaf geen antwoord.")
    try:
        ingelogd = bool(json.loads(uit[uit.index("{"):uit.rindex("}") + 1]).get("loggedIn"))
    except ValueError:
        return uitkomst("claude", naam, ONBEKEND, "Claude Code gaf geen leesbaar antwoord.")
    if ingelogd:
        return uitkomst("claude", naam, GOED)
    return uitkomst("claude", naam, FOUT, "Claude Code is niet ingelogd.", door="lid",
                    wat_nu="Zeg dat het lid in VS Code links op het oranje Claude-icoon klikt, Log in kiest en inlogt "
                           "met zijn Claude-account.")


def vscode_pad() -> Path | None:
    s = systeem()
    if s == "mac":
        plekken = [Path("/Applications/Visual Studio Code.app"), THUIS / "Applications" / "Visual Studio Code.app"]
    elif s == "windows":
        lokaal = Path(os.environ.get("LOCALAPPDATA") or THUIS / "AppData" / "Local")
        plekken = [lokaal / "Programs" / "Microsoft VS Code" / "Code.exe",
                   Path(os.environ.get("ProgramFiles") or "C:/Program Files") / "Microsoft VS Code" / "Code.exe"]
    else:
        plekken = [THUIS / ".local" / "share" / "vscode" / "bin" / "code", Path("/usr/bin/code"),
                   Path("/snap/bin/code"), Path("/usr/share/code/code")]
    for p in plekken:
        if p.exists():
            return p
    gevonden = shutil.which("code")
    return Path(gevonden) if gevonden else None


def vscode_instellingen_pad() -> Path:
    s = systeem()
    if s == "mac":
        return THUIS / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    if s == "windows":
        return Path(os.environ.get("APPDATA") or THUIS / "AppData" / "Roaming") / "Code" / "User" / "settings.json"
    return Path(os.environ.get("XDG_CONFIG_HOME") or THUIS / ".config") / "Code" / "User" / "settings.json"


def _zonder_jsonc(tekst: str) -> str:
    """VS Code-instellingen mogen commentaar en een komma te veel hebben; haal die weg."""
    uit: list[str] = []
    i, n = 0, len(tekst)
    while i < n:
        c = tekst[i]
        if c == '"':
            j = i + 1
            while j < n and tekst[j] != '"':
                j += 2 if tekst[j] == "\\" else 1
            uit.append(tekst[i:j + 1])
            i = j + 1
        elif tekst.startswith("//", i):
            j = tekst.find("\n", i)
            i = n if j < 0 else j
        elif tekst.startswith("/*", i):
            j = tekst.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            uit.append(c)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(uit))


def lees_vscode_instellingen(pad: Path | None = None) -> dict | None:
    """{} als het bestand er niet is, None als het onleesbaar is."""
    pad = pad or vscode_instellingen_pad()
    try:
        tekst = pad.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    except OSError:
        return None
    if not tekst.strip():
        return {}
    try:
        data = json.loads(_zonder_jsonc(tekst))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def zet_vscode_bypass(pad: Path | None = None) -> bool:
    """Zet de twee instellingen erbij. Alleen als het bestand gewone JSON is (of leeg); staat er
    commentaar in, dan blijft het onaangeroerd en lost Claude het op."""
    pad = pad or vscode_instellingen_pad()
    try:
        tekst = pad.read_text(encoding="utf-8-sig") if pad.exists() else ""
        data = json.loads(tekst) if tekst.strip() else {}
        if not isinstance(data, dict):
            return False
        data.update(VSCODE_BYPASS)
        pad.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=pad.parent, delete=False, suffix=".tmp") as t:
            t.write(json.dumps(data, indent=4, ensure_ascii=False) + "\n")
        Path(t.name).replace(pad)
        return True
    except (OSError, ValueError):
        return False


def check_vscode(herstel: bool) -> dict:
    naam = "VS Code met Claude staat goed"
    if not vscode_pad():
        return uitkomst("vscode", naam, FOUT, "VS Code staat niet op deze computer.", door="lid",
                        wat_nu="Zeg dat het lid de installatie opnieuw start via slimwerken.ai/installeer; de stap "
                               "VS Code zet het neer. Of hij downloadt het zelf op code.visualstudio.com.")
    extensies = THUIS / ".vscode" / "extensions"
    try:
        heeft_claude = any(p.name.lower().startswith("anthropic.claude-code") for p in extensies.iterdir())
    except OSError:
        heeft_claude = False
    if not heeft_claude:
        return uitkomst("vscode", naam, FOUT, "De Claude-extensie staat niet in VS Code.", door="claude",
                        wat_nu="Installeer de extensie: `code --install-extension anthropic.claude-code`. Werkt `code` "
                               "niet, zeg dan: open VS Code, klik links op het blokjes-icoon (Extensions), zoek op "
                               "Claude Code en klik op Install.")
    data = lees_vscode_instellingen()
    if data is not None and all(data.get(k) == v for k, v in VSCODE_BYPASS.items()):
        return uitkomst("vscode", naam, GOED)
    if herstel and zet_vscode_bypass():
        return uitkomst("vscode", naam, GOED, "Bypass permissions stond uit; ik heb het aangezet.")
    return uitkomst("vscode", naam, FOUT, "Claude in VS Code vraagt bij elke stap om toestemming (Bypass permissions "
                    "staat niet aan).", door="script" if not herstel else "claude",
                    wat_nu=f"Zet in {vscode_instellingen_pad()} deze twee instellingen erbij en laat de rest precies "
                           "staan: \"claudeCode.allowDangerouslySkipPermissions\": true en "
                           "\"claudeCode.initialPermissionMode\": \"bypassPermissions\". Zeg daarna dat het lid een "
                           "nieuw gesprek begint.")


def app_adres(m: Path) -> str | None:
    script = m / "overig" / "scripts" / "mainframe_app.py"
    if not script.exists():
        return None
    code, uit = draai(python() + [str(script), "url"], cwd=m, timeout=30)
    gevonden = re.findall(r"MAINFRAME_URL=(\S+)", uit) or re.findall(r"(http://127\.0\.0\.1:\d+)", uit)
    return gevonden[-1].rstrip("/") if code == 0 and gevonden else None


def check_app(m: Path, herstel: bool) -> dict:
    naam = "Mainframe OS (de app) draait"
    script = m / "overig" / "scripts" / "mainframe_app.py"
    if not script.exists():
        return uitkomst("app", naam, FOUT, "Het startscript van de app ontbreekt.", door="claude",
                        wat_nu="Draai `python3 overig/scripts/mainframe_update.py` (Windows: py); dat zet het "
                               "startscript en de app neer.")
    adres = app_adres(m)
    if adres:
        return uitkomst("app", naam, GOED, adres)
    if herstel:
        draai(python() + [str(script), "start", "--geen-browser", "--installeer-bun"], cwd=m, timeout=900)
        adres = app_adres(m)
        if adres:
            return uitkomst("app", naam, GOED, f"De app stond uit; ik heb hem gestart ({adres}).")
    return uitkomst("app", naam, FOUT, "De app staat uit of start niet.", door="script" if not herstel else "claude",
                    wat_nu="Draai `python3 overig/scripts/mainframe_app.py start --installeer-bun` (Windows: py) met een "
                           "timeout van 10 minuten, lees de foutregels en los op wat in de weg zit. Volg bij twijfel de "
                           "skill /app.")


_GEZIEN: dict[str, str] = {}  # wat een controle onderweg leerde en het rapport ook nodig heeft


def check_versie(m: Path) -> dict:
    naam = "Je hebt de nieuwste versie"
    script = m / "overig" / "scripts" / "mainframe_update.py"
    if not script.exists():
        return uitkomst("versie", naam, ONBEKEND, "Het updatescript ontbreekt.", ernst="advies")
    code, uit = draai(python() + [str(script), "--status"], cwd=m, timeout=60)
    try:
        st = json.loads(uit[uit.index("{"):uit.rindex("}") + 1])
    except ValueError:
        return uitkomst("versie", naam, ONBEKEND, "Kon de versie niet opvragen.", ernst="advies")
    _GEZIEN["app_versie"] = str(st.get("app_nu") or st.get("nu") or "")
    if not st.get("ok"):
        return uitkomst("versie", naam, ONBEKEND, f"Kon de versie niet opvragen ({st.get('reden')}).", ernst="advies")
    if not st.get("nieuwer"):
        return uitkomst("versie", naam, GOED, str(st.get("app_nu") or st.get("nu") or ""), ernst="advies")
    return uitkomst("versie", naam, FOUT, f"Er staat een nieuwere versie klaar ({st.get('app_nieuwste') or st.get('nieuwste')}).",
                    ernst="advies", door="claude", wat_nu="Volg de skill /update.")


def sleutelmodule(m: Path):
    import importlib
    for plek in (m / "overig" / "scripts", Path(__file__).resolve().parent):
        if (plek / "mainframe_sleutels.py").exists() and str(plek) not in sys.path:
            sys.path.insert(0, str(plek))
    return importlib.import_module("mainframe_sleutels")


def check_sleutels(m: Path, herstel: bool) -> dict:
    naam = "Je sleutels zijn veilig"
    script = m / "overig" / "scripts" / "mainframe_sleutels.py"
    venster = (f"Start op de achtergrond `python3 overig/scripts/mainframe_sleutels.py wizard \"{m}\"` (Windows: py). Er "
               "gaat een venster open in de browser van het lid; daar maakt en bewaart hij zijn hoofdsleutel. Zeg "
               "alleen: Er staat een venster open in je browser, volg daar de stappen. Vraag of toon de hoofdsleutel "
               "NOOIT in dit gesprek en open nooit een .env. Wacht tot het script eindigt met 'Klaar: je sleutels zijn "
               "veilig.' Staat het script er niet, volg dan link.slimwerken.ai/sleutels.")
    try:
        mod = sleutelmodule(m)
        st = mod.status(m)
    except Exception as fout:
        if not script.exists():
            return uitkomst("sleutels", naam, FOUT, "Het sleutelscript ontbreekt.", door="claude", wat_nu=venster)
        return uitkomst("sleutels", naam, ONBEKEND, f"Kon de sleutels niet nalopen ({type(fout).__name__}).")
    if st.get("klaar"):
        return uitkomst("sleutels", naam, GOED)
    if herstel and st.get("hoofdsleutel") and st.get("bewaard"):
        # De hoofdsleutel is er al en is bewaard: versleutelen kan dan zonder het lid.
        try:
            mod.beveilig(m)
            if mod.status(m).get("klaar"):
                return uitkomst("sleutels", naam, GOED, "Nog niet alles was versleuteld; dat is nu gedaan.")
        except Exception:
            pass
    if not st.get("hoofdsleutel"):
        return uitkomst("sleutels", naam, FOUT, "Je hebt nog geen hoofdsleutel; je sleutels zijn niet versleuteld.",
                        door="lid", wat_nu=venster)
    if not st.get("bewaard"):
        return uitkomst("sleutels", naam, FOUT, "Je hoofdsleutel is gemaakt, maar je hebt nog niet bevestigd dat je "
                        "hem bewaard hebt.", door="lid", wat_nu=venster)
    if st.get("klopt") is False:
        return uitkomst("sleutels", naam, FOUT, "De versleutelde sleutels passen niet bij je hoofdsleutel.",
                        door="lid", wat_nu=venster + " Het lid kiest daar Ik heb al een hoofdsleutel en plakt de "
                        "hoofdsleutel van zijn eerste computer.")
    return uitkomst("sleutels", naam, FOUT, f"{st.get('versleuteld')} van {st.get('bestanden')} sleutelbestanden zijn "
                    "versleuteld.", door="script" if not herstel else "claude", wat_nu=venster)


def check_overjou(m: Path) -> dict:
    naam = "Je Mainframe kent jou"
    open_ = []
    for pad in ("CLAUDE.md", "kennis/over-mij.md"):
        try:
            tekst = (m / pad).read_text(encoding="utf-8", errors="replace")
        except OSError:
            open_.append(pad + " ontbreekt")
            continue
        if re.search(r"\{\{[A-Z_]{3,}\}\}", tekst):
            open_.append(pad + " heeft nog lege invulplekken")
    if not open_:
        return uitkomst("overjou", naam, GOED, ernst="advies")
    return uitkomst("overjou", naam, FOUT, "; ".join(open_) + ".", ernst="advies", door="claude",
                    wat_nu="Vraag het lid kort wie hij is, wat zijn bedrijf doet en hoe hij aangesproken wil worden, en "
                           "vul daarmee de lege plekken ({{...}}) in CLAUDE.md en kennis/over-mij.md. Of wijs op Leer mij "
                           "kennen in de app onder Verstand.")


def check_git(m: Path) -> dict:
    naam = "Je werk wordt bijgehouden (git)"
    git = vind("git")
    if not git:
        return uitkomst("git", naam, ONBEKEND, "Git staat er niet op.", ernst="advies")
    if not (m / ".git").exists():
        return uitkomst("git", naam, FOUT, "Deze map houdt nog geen geschiedenis bij.", ernst="advies", door="claude",
                        wat_nu="Draai in de Mainframe-map `git init` en maak een eerste commit 'Mijn Mainframe'. "
                               "Controleer eerst dat .env in .gitignore staat.")
    code, _ = draai([git, "log", "-1", "--format=%H"], cwd=m, timeout=30)
    if code == 0:
        return uitkomst("git", naam, GOED, ernst="advies")
    return uitkomst("git", naam, FOUT, "Er is nog niets vastgelegd.", ernst="advies", door="claude",
                    wat_nu="Maak een eerste commit 'Mijn Mainframe'. Controleer eerst dat .env in .gitignore staat.")


def check_skills(m: Path) -> dict:
    naam = "De vaste skills staan erin"
    mist = [s for s in KERNSKILLS if not (m / ".claude" / "skills" / s / "SKILL.md").exists()]
    if not mist:
        return uitkomst("skills", naam, GOED)
    return uitkomst("skills", naam, FOUT, "Deze skills ontbreken: " + ", ".join("/" + s for s in mist), door="claude",
                    wat_nu="Draai `python3 overig/scripts/mainframe_update.py` (Windows: py); dat zet ontbrekende skills "
                           "terug zonder iets van het lid te overschrijven.")


def check_script(m: Path, id_: str, naam: str, pad: str, wat_nu: str) -> dict | None:
    """Een controle die al in het Mainframe zit (zelftest, veiligheidscheck). None als hij er niet is."""
    script = m / pad
    if not script.exists():
        return None
    code, uit = draai(python() + [str(script)], cwd=m, timeout=300)
    if code == 0:
        return uitkomst(id_, naam, GOED, ernst="advies")
    if code in (124, 127):
        return uitkomst(id_, naam, ONBEKEND, "De controle zelf liep niet.", ernst="advies")
    if id_ == "veiligheid":
        # Oudere versies van de check kijken ook in de pakketten van de app; dat zijn geen sleutels van het lid.
        try:
            rapport = json.loads(uit[uit.index("{"):])
            lijst = rapport.get("findings") or rapport.get("bevindingen") or []
            echt = [f for f in lijst if f.get("level") == "fail" and "node_modules" not in str(f.get("path") or "")]
            if not echt:
                return uitkomst(id_, naam, GOED, ernst="advies")
        except (ValueError, AttributeError):
            pass
    return uitkomst(id_, naam, FOUT, "Deze controle gaf een waarschuwing.", ernst="advies", door="claude", wat_nu=wat_nu)


def check_stem(m: Path, sloten: dict | None) -> dict | None:
    """Alleen als Jarvis voor dit lid open staat (cursus: vanaf de week waarin Jarvis opengaat)."""
    if not sloten or not (sloten.get("open") or {}).get("jarvis", False):
        return None
    naam = "Jarvis heeft een stem"
    try:
        tekst = (m / ".env").read_text(encoding="utf-8", errors="replace")
    except OSError:
        tekst = ""
    if re.search(r"^\s*(?:export\s+)?(GEMINI_API_KEY|GOOGLE_API_KEY)\s*=\s*\S{10,}", tekst, re.M):
        return uitkomst("stem", naam, GOED, ernst="advies")
    return uitkomst("stem", naam, FOUT, "Er staat nog geen sleutel van Google voor Jarvis' stem.", ernst="advies",
                    door="lid", wat_nu="Zeg dat het lid `Mainframe wizard` in zijn Mainframe-map start (of /wizard typt) "
                                       "en de stap Jarvis' stem doet. Vraag de sleutel nooit in dit gesprek.")


# ---------- alles bij elkaar ----------

def meet(m: Path, herstel: bool = False) -> dict:
    controles: list[dict] = []

    def doe(fn, *args):
        try:
            uit = fn(*args)
        except Exception as fout:  # een controle die omvalt houdt de rest nooit tegen
            naam = getattr(fn, "__name__", "controle").replace("check_", "")
            uit = uitkomst(naam, naam, ONBEKEND, f"Deze controle liep zelf vast ({type(fout).__name__}).")
        if uit:
            controles.append(uit)
        return uit

    doe(check_map, m)
    doe(check_plek, m)
    sloten = None
    try:
        lic, sloten = check_licentie(m)
        controles.append(lic)
    except Exception as fout:
        controles.append(uitkomst("licentie", "Je licentie klopt", ONBEKEND, type(fout).__name__))
    doe(check_gereedschap)
    doe(check_claude)
    doe(check_vscode, herstel)
    doe(check_app, m, herstel)
    doe(check_sleutels, m, herstel)
    doe(check_skills, m)
    doe(check_overjou, m)
    doe(check_git, m)
    doe(check_versie, m)
    doe(check_script, m, "zelftest", "De zelftest van je Mainframe is groen", "overig/scripts/setup/self_test.py",
        "Draai `python3 overig/scripts/setup/self_test.py`, lees welke regel niet goed is en los die op.")
    doe(check_script, m, "veiligheid", "Er staan geen sleutels op de verkeerde plek",
        "overig/scripts/setup/security_check.py",
        "Draai `python3 overig/scripts/setup/security_check.py`, en zet elke gevonden sleutel in .env. Toon de waarde "
        "van een sleutel nooit in dit gesprek.")
    doe(check_stem, m, sloten)

    fout_kern = [c for c in controles if c["status"] == FOUT and c["ernst"] == "kern"]
    fout_advies = [c for c in controles if c["status"] == FOUT and c["ernst"] == "advies"]
    app_versie = _GEZIEN.get("app_versie", "")
    return {"ok": not fout_kern, "helemaal_groen": not fout_kern and not fout_advies,
            "systeem": systeem(), "systeem_versie": platform.platform()[:80], "app_versie": app_versie,
            "map": str(m), "tijd": time.strftime("%Y-%m-%dT%H:%M:%S"), "hersteld": herstel, "controles": controles}


def meld(m: Path, rapport: dict) -> bool:
    """Geef de uitslag door aan Slim Werken. Nooit bestanden of sleutels; lukt het niet, dan niet."""
    lic = licentie(m)
    if not lic.get("code"):
        return False
    try:
        antwoord = http_json(f"{SERVER}/licentie/installatie", {
            "code": lic["code"], "email": lic.get("email") or "", "bron": "check",
            "soort": "check_goed" if rapport["ok"] else "check_fout",
            "systeem": rapport["systeem"], "systeem_versie": rapport["systeem_versie"],
            "versie": rapport["app_versie"], "apparaat": socket.gethostname()[:60],
            "controles": [{"id": c["id"], "status": c["status"], "ernst": c["ernst"], "uitleg": c["uitleg"][:300]}
                          for c in rapport["controles"]],
        }, timeout=15)
        return bool(antwoord.get("ok"))
    except Exception:
        return False


def tekst(rapport: dict) -> str:
    regels = [f"MAINFRAME-CHECK ({rapport['systeem']}, app {rapport['app_versie'] or 'onbekend'}, {rapport['map']})", ""]
    woord = {GOED: "GOED    ", FOUT: "NIET GOED", ONBEKEND: "NIET GEMETEN"}
    for c in rapport["controles"]:
        soort = "" if c["ernst"] == "kern" else " (advies)"
        regels.append(f"{woord[c['status']]}  {c['naam']}{soort}" + (f": {c['uitleg']}" if c["uitleg"] else ""))
        if c["status"] == FOUT:
            wie = {"script": "een script kan dit: draai opnieuw met --herstel", "claude": "Claude lost dit op",
                   "lid": "het lid moet zelf iets doen, Claude begeleidt"}.get(c["door"], "")
            regels.append(f"           WIE: {wie}")
            regels.append(f"           WAT NU: {c['wat_nu']}")
    fout = [c for c in rapport["controles"] if c["status"] == FOUT]
    regels.append("")
    if not fout:
        regels.append("UITSLAG: alles staat goed.")
    else:
        kern = sum(1 for c in fout if c["ernst"] == "kern")
        regels.append(f"UITSLAG: {len(fout)} van {len(rapport['controles'])} niet goed"
                      + (f", waarvan {kern} nodig om verder te kunnen." if kern else ", alleen adviezen."))
    return "\n".join(regels)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Staat je Mainframe goed?")
    ap.add_argument("map", nargs="?", help="je Mainframe-map (standaard: de map waar dit script in staat)")
    ap.add_argument("--herstel", action="store_true", help="repareer eerst wat een script veilig kan")
    ap.add_argument("--json", action="store_true", help="het rapport als JSON")
    ap.add_argument("--niet-melden", action="store_true", help="geef de uitslag niet door aan Slim Werken")
    args = ap.parse_args(argv)
    m = mainframe_map(args.map)
    rapport = meet(m, herstel=args.herstel)
    rapport["gemeld"] = False if args.niet_melden else meld(m, rapport)
    try:
        doel = m / ".mainframe" / "check.json"
        if doel.parent.exists():
            doel.write_text(json.dumps(rapport, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass
    if args.json:
        print(json.dumps(rapport, indent=2, ensure_ascii=False))
    else:
        print(tekst(rapport))
        if rapport["gemeld"]:
            print("De uitslag is doorgegeven aan Slim Werken (alleen goed of niet goed per controle).")
    return 0 if rapport["ok"] else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    sys.exit(main())
