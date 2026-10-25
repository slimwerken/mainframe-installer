#!/usr/bin/env python3
"""Je Mainframe-sleutels veilig: versleutelen, hoofdsleutel bewaren, leesbare versie uit de map.

WAAROM (Bart, 25 oktober 2026). In de .env van je Mainframe-map staan de sleutels
waarmee je Mainframe namens jou bij je mail, agenda en andere programma's mag. Gaat
die map mee naar een back-up, een cloudmap of GitHub, of raakt je laptop weg, dan
gaan je sleutels mee. Dit script doet op elke computer hetzelfde, op Mac, Windows
en Linux:

1. Een hoofdsleutel maken (eerste computer) of plakken (volgende computer).
2. Naast elke .env een versleutelde versie zetten (`.env.versleuteld`). Zonder de
   hoofdsleutel is daar niets uit te halen, dus die mag mee in een back-up.
3. Controleren dat de versleutelde versie precies dezelfde sleutels teruggeeft.
4. Pas dan, op Mac en Linux: de leesbare versie naar `~/.config/mainframe/leesbaar/`
   (alleen voor jou leesbaar) en een verwijzing op de oude plek. Alles wat de .env
   leest, leest precies hetzelfde. Op Windows blijft de leesbare versie staan:
   Windows staat zo'n verwijzing alleen toe met beheerdersrechten.

Er wordt nooit iets weggegooid. Een verkeerde hoofdsleutel verandert niets.
De hoofdsleutel komt nooit in een gesprek met de AI: alleen in het venster van de
wizard of in het bestand `~/.config/mainframe/sleutel`.

    python3 mainframe_sleutels.py status [map]       # hoe staat het (JSON, zonder waarden)
    python3 mainframe_sleutels.py wizard [map]       # de wizard in je browser
    python3 mainframe_sleutels.py bijwerken [map]    # versleutelde versie bijwerken (stil, voor de hook)
    python3 mainframe_sleutels.py terug [map]        # alles terug zoals het was

Zelfde opzet als overig/scripts/sleutels.py in Barts eigen Mainframe; dit is de
versie voor leden (alleen de standaardbibliotheek, Python 3.9+).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

THUIS = Path.home()
CONFIG = THUIS / ".config" / "mainframe"
SLEUTELBESTAND = CONFIG / "sleutel"
LEESBAAR = CONFIG / "leesbaar"
BIN = CONFIG / "bin"
STAAT = CONFIG / "sleutels-staat.json"
ACHTERVOEGSEL = ".versleuteld"

# dotenvx, vaste versie met de controlegetallen van GitHub (release v2.33.0, 5 okt 2026).
DOTENVX_VERSIE = "2.33.0"
DOTENVX_PAKKET = {
    ("darwin", "arm64"): ("darwin-arm64.tar.gz", "83d60e39014f223fcabbf53f673b1747ed9cebabf69c0723aef3e565352f62bc"),
    ("darwin", "x86_64"): ("darwin-x86_64.tar.gz", "2f7851b91af587f3dda98d30f23dd49bb2d94b5b18788884b023443d72fb5744"),
    ("linux", "x86_64"): ("linux-x86_64.tar.gz", "3844f3e52459df1e16fb92c51b776425d0e8411b0f75149b6aa2593876db1bc3"),
    ("linux", "arm64"): ("linux-arm64.tar.gz", "e75dea840fe409fbd16c9958bfb9927cfb6176ed72bea98c2308fc018c384455"),
    ("windows", "x86_64"): ("windows-x86_64.zip", "e32ffd47b0ad41a9c67a2f380a83a089ade76abb4c1f6374f2b21c9fde8824e4"),
}
DOTENVX_VLAGGEN = ["--no-native", "--no-armor", "--no-1password", "--no-bitwarden"]

OVERSLAAN_MAPPEN = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build",
                    ".cache", ".turbo", "site-packages", ".mainframe-installer"}
NIET_MEE = (ACHTERVOEGSEL, ".example", ".sample", ".template", ".tmp", "-tmp", ".nieuw", ".keys")
REGEL = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
SLEUTELVORM = re.compile(r"^[0-9a-f]{64}$")


class SleutelFout(Exception):
    """Iets ging niet zoals verwacht; er is dan niets veranderd aan je bestanden."""


def is_windows() -> bool:
    return sys.platform.startswith("win")


# ---------- dotenvx ----------

def _systeem() -> tuple[str, str]:
    s = "windows" if is_windows() else ("darwin" if sys.platform == "darwin" else "linux")
    m = platform.machine().lower()
    m = "arm64" if m in ("arm64", "aarch64") else "x86_64" if m in ("x86_64", "amd64") else m
    return s, m


def dotenvx() -> str:
    """Het pad naar dotenvx; zet de vaste versie neer als hij er nog niet is."""
    naam = "dotenvx.exe" if is_windows() else "dotenvx"
    eigen = BIN / naam
    if eigen.exists():
        return str(eigen)
    gevonden = shutil.which("dotenvx")
    if gevonden:
        return gevonden
    sleutel = _systeem()
    if sleutel not in DOTENVX_PAKKET:
        raise SleutelFout(f"dotenvx is er niet voor deze computer ({sleutel[0]} {sleutel[1]})")
    bestand, controle = DOTENVX_PAKKET[sleutel]
    url = f"https://github.com/dotenvx/dotenvx/releases/download/v{DOTENVX_VERSIE}/dotenvx-{DOTENVX_VERSIE}-{bestand}"
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            data = r.read()
    except Exception as fout:
        raise SleutelFout(f"dotenvx downloaden lukte niet ({type(fout).__name__}); probeer het zo opnieuw") from None
    if hashlib.sha256(data).hexdigest() != controle:
        raise SleutelFout("de download van dotenvx klopt niet met het controlegetal; niets geinstalleerd")
    BIN.mkdir(parents=True, exist_ok=True)
    if bestand.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            lid = next(n for n in z.namelist() if n.rsplit("/", 1)[-1] == naam)
            eigen.write_bytes(z.read(lid))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            lid = next(m for m in t.getmembers() if m.isfile() and m.name.rsplit("/", 1)[-1] == naam)
            eigen.write_bytes(t.extractfile(lid).read())
    if not is_windows():
        os.chmod(eigen, 0o755)
    return str(eigen)


def _dotenvx(args: list[str], prive: str | None = None, vlaggen: bool = True) -> str:
    omg = {k: v for k, v in os.environ.items() if not k.startswith("DOTENV_")}
    if prive:
        omg["DOTENV_PRIVATE_KEY"] = prive
    try:
        r = subprocess.run([dotenvx(), *args, *(DOTENVX_VLAGGEN if vlaggen else [])],
                           capture_output=True, text=True, timeout=120, env=omg)
    except (OSError, subprocess.SubprocessError) as fout:
        raise SleutelFout(f"dotenvx start niet: {type(fout).__name__}") from None
    if r.returncode != 0:
        # dotenvx noemt in een fout alleen namen, nooit waarden.
        raise SleutelFout(f"dotenvx {args[0]} lukte niet: {r.stderr.strip()[:200]}")
    return r.stdout


# ---------- hoofdsleutel ----------

def _schrijf_veilig(doel: Path, inhoud: bytes) -> None:
    doel.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=doel.parent, prefix=f".{doel.name}.", suffix=".tmp")
    try:
        if not is_windows():
            os.chmod(tmp, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(inhoud)
        os.replace(tmp, doel)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _alleen_ik(p: Path) -> None:
    if not is_windows():
        try:
            os.chmod(p, 0o700 if p.is_dir() else 0o600)
        except OSError:
            pass


def hoofdsleutel() -> str | None:
    try:
        for regel in SLEUTELBESTAND.read_text(encoding="utf-8").splitlines():
            regel = regel.strip()
            if regel and not regel.startswith("#"):
                return regel.split("=", 1)[-1].strip().strip('"')
    except OSError:
        return None
    return None


def _lees_staat() -> dict:
    try:
        return json.loads(STAAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _zet_staat(**velden) -> None:
    s = _lees_staat()
    s.update(velden)
    _schrijf_veilig(STAAT, json.dumps(s, indent=1).encode())


def maak_hoofdsleutel() -> str:
    """Eerste computer: een nieuwe hoofdsleutel. Bestaat er al een, dan blijft die (nooit overschrijven)."""
    bestaand = hoofdsleutel()
    if bestaand:
        return bestaand
    prive = secrets.token_hex(32)
    _dotenvx(["primitives", "derive", prive], vlaggen=False)   # controleert dat dotenvx hem accepteert
    CONFIG.mkdir(parents=True, exist_ok=True)
    _alleen_ik(CONFIG)
    _schrijf_veilig(SLEUTELBESTAND, (prive + "\n").encode())
    _zet_staat(bewaard=False, gemaakt=time.strftime("%Y-%m-%dT%H:%M:%S"))
    return prive


def bevestig_bewaard() -> None:
    _zet_staat(bewaard=True, bewaard_op=time.strftime("%Y-%m-%dT%H:%M:%S"))


def is_bewaard() -> bool:
    return bool(_lees_staat().get("bewaard"))


def zet_hoofdsleutel(sleutel: str, map_: Path) -> str:
    """Volgende computer: de geplakte hoofdsleutel. Een verkeerde sleutel verandert niets."""
    sleutel = sleutel.strip().strip('"').lower()
    if not SLEUTELVORM.match(sleutel):
        raise SleutelFout("dit lijkt geen hoofdsleutel: die bestaat uit 64 tekens, cijfers en de letters a tot f")
    bestaand = hoofdsleutel()
    if bestaand and bestaand != sleutel:
        raise SleutelFout("op deze computer staat al een andere hoofdsleutel; er is niets veranderd")
    # Staan er al versleutelde bestanden (ook zonder leesbare versie, uit GitHub), dan moet de sleutel ze openen.
    for v in versleutelde(map_):
        _ontsleutel(v, sleutel)   # gooit SleutelFout bij een verkeerde sleutel
        break
    CONFIG.mkdir(parents=True, exist_ok=True)
    _alleen_ik(CONFIG)
    _schrijf_veilig(SLEUTELBESTAND, (sleutel + "\n").encode())
    _zet_staat(bewaard=True, geplakt=time.strftime("%Y-%m-%dT%H:%M:%S"))
    return "hoofdsleutel staat erop"


# ---------- bestanden ----------

def parse(tekst: str) -> dict[str, str]:
    uit: dict[str, str] = {}
    for regel in tekst.splitlines():
        m = REGEL.match(regel)
        if not m or regel.lstrip().startswith("#"):
            continue
        waarde = m.group(2).strip()
        if len(waarde) >= 2 and waarde[0] == waarde[-1] and waarde[0] in "\"'":
            waarde = waarde[1:-1]
        elif " #" in waarde:
            waarde = waarde.split(" #", 1)[0].rstrip()
        uit[m.group(1)] = waarde
    return uit


def versleuteld_pad(p: Path) -> Path:
    return p.with_name(p.name + ACHTERVOEGSEL)


def leesbare_plek(p: Path) -> Path:
    try:
        rel = Path(os.path.abspath(p)).relative_to(THUIS)
    except ValueError:
        rel = Path("buiten-thuismap") / Path(os.path.abspath(p)).relative_to(Path(os.path.abspath(p)).anchor)
    return LEESBAAR / rel


def _onder_leesbaar(p: Path) -> bool:
    try:
        Path(os.path.abspath(p)).relative_to(LEESBAAR)
        return True
    except ValueError:
        return False


def _linkdoel(p: Path) -> Path:
    doel = Path(os.readlink(p))
    return doel if doel.is_absolute() else (p.parent / doel)


def is_env_naam(naam: str) -> bool:
    return (naam == ".env" or naam.startswith(".env.")) and not naam.endswith(NIET_MEE)


def kandidaten(map_: Path) -> list[Path]:
    """Elke .env en .env.<iets> in de Mainframe-map, zonder voorbeelden, versleutelde versies en bouwmappen."""
    uit = []
    for wortel, mappen, bestanden in os.walk(map_):
        mappen[:] = [m for m in mappen if m not in OVERSLAAN_MAPPEN]
        for naam in bestanden:
            if is_env_naam(naam):
                p = Path(wortel) / naam
                if p.is_symlink() and not _onder_leesbaar(_linkdoel(p)):
                    continue   # een verwijzing naar elders: daar gaan wij niet over
                uit.append(p)
    return sorted(uit)


def versleutelde(map_: Path) -> list[Path]:
    """Elke versleutelde .env in de map, ook als de leesbare versie (nog) ontbreekt."""
    uit = []
    for wortel, mappen, bestanden in os.walk(map_):
        mappen[:] = [m for m in mappen if m not in OVERSLAAN_MAPPEN]
        uit += [Path(wortel) / n for n in bestanden
                if n.endswith(ACHTERVOEGSEL) and is_env_naam(n[:-len(ACHTERVOEGSEL)])]
    return sorted(uit)


def _leesbare_inhoud(p: Path) -> bytes:
    return p.read_bytes()


def versleutel(p: Path, prive: str) -> Path:
    """Zet `<p>.versleuteld` neer uit de leesbare versie (via de verwijzing als die er is)."""
    waarden = parse(_leesbare_inhoud(p).decode("utf-8"))
    waarden.pop("DOTENV_PUBLIC_KEY", None)
    publiek = _dotenvx(["primitives", "derive", prive], vlaggen=False).strip().strip('"')
    regels = [f'DOTENV_PUBLIC_KEY="{publiek}"']
    for naam, waarde in waarden.items():
        if "'" in waarde and re.search(r"[$\\\"]", waarde):
            raise SleutelFout(f"{naam}: deze waarde is niet letterlijk op te slaan (' samen met $ of \\)")
        regels.append(f"{naam}='{waarde}'" if re.search(r"[$\\\"]", waarde) else f'{naam}="{waarde}"')
    doel = versleuteld_pad(p)
    with tempfile.TemporaryDirectory(prefix="mainframe-sleutels-") as werk:
        _alleen_ik(Path(werk))
        tmp = Path(werk) / ".env"
        tmp.write_text("\n".join(regels) + "\n", encoding="utf-8")
        _alleen_ik(tmp)
        _dotenvx(["encrypt", "-f", str(tmp), "-fk", str(Path(werk) / ".env.keys")], prive)
        inhoud = tmp.read_text(encoding="utf-8")
    if waarden and "encrypted:" not in inhoud:
        raise SleutelFout("de versleutelde versie ziet er niet uit zoals verwacht")
    _schrijf_veilig(doel, inhoud.encode("utf-8"))
    return doel


def _ontsleutel(doel: Path, prive: str) -> dict[str, str]:
    # Een eigen lege map voor het sleutelbestand van dotenvx: /dev/null bestaat niet op Windows.
    with tempfile.TemporaryDirectory(prefix="mainframe-sleutels-") as werk:
        try:
            uit = json.loads(_dotenvx(["get", "-f", str(doel), "-fk", str(Path(werk) / ".env.keys"),
                                       "--format", "json"], prive))
        except ValueError:
            raise SleutelFout("de versleutelde versie is niet te lezen") from None
    uit.pop("DOTENV_PUBLIC_KEY", None)
    if any(isinstance(v, str) and v.startswith("encrypted:") for v in uit.values()):
        raise SleutelFout("deze hoofdsleutel opent je versleutelde sleutels niet; er is niets veranderd")
    return uit


def _controleer(p: Path, prive: str) -> None:
    oud = parse(_leesbare_inhoud(p).decode("utf-8"))
    oud.pop("DOTENV_PUBLIC_KEY", None)
    gelezen = _ontsleutel(versleuteld_pad(p), prive)
    anders = sorted(n for n in set(gelezen) | set(oud) if gelezen.get(n) != oud.get(n))
    if anders:
        raise SleutelFout(f"de versleutelde versie wijkt af voor {', '.join(anders)}; er is niets verplaatst")


def uit_de_map(p: Path) -> str:
    """Leesbare versie naar ~/.config/mainframe/leesbaar, verwijzing op de plek. Niet op Windows."""
    p = Path(os.path.abspath(p))
    if p.is_symlink():
        return "al buiten de map"
    if is_windows():
        return "blijft staan (Windows)"
    inhoud = p.read_bytes()
    st = p.stat()
    doel = leesbare_plek(p)
    doel.parent.mkdir(parents=True, exist_ok=True)
    q = doel.parent
    while _onder_leesbaar(q) or q == LEESBAAR:
        _alleen_ik(q)
        if q == LEESBAAR:
            break
        q = q.parent
    _alleen_ik(CONFIG)
    if doel.exists() and doel.read_bytes() != inhoud:
        _schrijf_veilig(doel.with_name(doel.name + f".vorige-{time.strftime('%Y%m%d-%H%M%S')}"), doel.read_bytes())
    _schrijf_veilig(doel, inhoud)
    os.utime(doel, (st.st_atime, st.st_mtime))
    tmp = p.with_name(f".{p.name}.verwijzing.tmp")
    tmp.unlink(missing_ok=True)
    os.symlink(doel, tmp)
    if p.read_bytes() != inhoud or p.stat().st_mtime != st.st_mtime:
        tmp.unlink(missing_ok=True)
        return "intussen veranderd, volgende keer"
    os.replace(tmp, p)
    if p.read_bytes() != inhoud:
        raise SleutelFout("na het verplaatsen leest de plek iets anders")
    return "uit de map"


GITIGNORE_REGELS = ("# Mainframe: de versleutelde sleutels mogen mee naar GitHub (zonder hoofdsleutel onleesbaar)",
                    "!.env.versleuteld", "!.env*.versleuteld")


def gitignore_openzetten(map_: Path) -> bool:
    """Zet de versleutelde versies open voor git; de leesbare .env blijft genegeerd."""
    gi = map_ / ".gitignore"
    try:
        tekst = gi.read_text(encoding="utf-8") if gi.exists() else ""
    except OSError:
        return False
    if all(r in tekst.splitlines() for r in GITIGNORE_REGELS[1:]):
        return False
    regels = [r for r in GITIGNORE_REGELS if r not in tekst.splitlines()]
    _schrijf_veilig(gi, ((tekst.rstrip("\n") + "\n\n" if tekst.strip() else "") + "\n".join(regels) + "\n").encode())
    return True


def _env_tekst(waarden: dict[str, str]) -> str:
    regels = []
    for naam, waarde in waarden.items():
        regels.append(f"{naam}='{waarde}'" if re.search(r"[\s#\"$\\]", waarde) and "'" not in waarde
                      else f'{naam}="{waarde}"' if re.search(r"[\s#']", waarde) else f"{naam}={waarde}")
    return "\n".join(regels) + "\n"


def herstel(map_: Path, prive: str | None = None) -> dict[str, str]:
    """Volgende computer: zet een leesbare versie neer waar alleen de versleutelde staat (uit GitHub of een back-up)."""
    prive = prive or hoofdsleutel()
    if not prive:
        return {}
    uit = {}
    for v in versleutelde(map_):
        p = v.with_name(v.name[:-len(ACHTERVOEGSEL)])
        if p.exists():
            continue
        try:
            waarden = _ontsleutel(v, prive)
            inhoud = _env_tekst(waarden).encode("utf-8")
            if parse(inhoud.decode("utf-8")) != waarden:
                raise SleutelFout("de herstelde versie leest anders dan de versleutelde")
            if p.is_symlink():                      # verwijzing zonder doel: het doel vullen
                _schrijf_veilig(_linkdoel(p), inhoud)
            else:
                _schrijf_veilig(p, inhoud)
                _alleen_ik(p)
            uit[str(p.relative_to(map_))] = "teruggezet uit de versleutelde versie"
        except (SleutelFout, OSError) as fout:
            uit[str(p.relative_to(map_))] = f"niet gedaan: {fout}"
    return uit


def beveilig(map_: Path) -> dict[str, str]:
    """Alles in een keer: per .env versleutelen, controleren, dan (Mac/Linux) uit de map."""
    prive = hoofdsleutel()
    if not prive:
        raise SleutelFout("er staat nog geen hoofdsleutel op deze computer")
    uit = herstel(map_, prive)
    for p in kandidaten(map_):
        naam = str(p.relative_to(map_)) if str(p).startswith(str(map_)) else str(p)
        try:
            if not p.exists():
                uit[naam] = "leesbare versie ontbreekt"
                continue
            versleutel(p, prive)
            _controleer(p, prive)
            uit[naam] = uit_de_map(p)
        except (SleutelFout, OSError, UnicodeDecodeError) as fout:
            uit[naam] = f"niet gedaan: {fout}"
    if any(v in ("uit de map", "al buiten de map", "blijft staan (Windows)") for v in uit.values()):
        gitignore_openzetten(map_)
    _zet_staat(laatst_beveiligd=time.strftime("%Y-%m-%dT%H:%M:%S"))
    return uit


def bijwerken(map_: Path) -> dict[str, str]:
    """Stil en snel (voor de sessiestart): nieuwere leesbare versie opnieuw versleutelen.

    Verving een programma de verwijzing door een gewoon bestand, dan gaat dat
    bestand na de controle weer uit de map. Zonder hoofdsleutel doet dit niets.
    """
    prive = hoofdsleutel()
    if not prive:
        return {}
    uit = {}
    for p in kandidaten(map_):
        try:
            v = versleuteld_pad(p)
            if not p.exists():
                continue
            # Een gewoon bestand op de plek (een programma verving de verwijzing) altijd opnieuw:
            # zijn tijd kan ouder zijn dan de versleutelde versie terwijl de inhoud nieuwer is.
            if not v.exists() or not p.is_symlink() or p.stat().st_mtime > v.stat().st_mtime:
                versleutel(p, prive)
                _controleer(p, prive)
                uit[p.name] = "bijgewerkt"
            if not p.is_symlink() and not is_windows() and time.time() - p.stat().st_mtime > 120:
                uit[p.name] = uit_de_map(p)
        except (SleutelFout, OSError, UnicodeDecodeError) as fout:
            uit[p.name] = f"niet gedaan: {fout}"
    return uit


def terug(map_: Path) -> dict[str, str]:
    """Terugdraaien: de leesbare versie weer als gewoon bestand op zijn plek. De hoofdsleutel blijft."""
    uit = {}
    for p in kandidaten(map_):
        if not p.is_symlink():
            continue
        doel = _linkdoel(p)
        if not doel.is_file():
            uit[p.name] = "leesbare versie ontbreekt"
            continue
        st = doel.stat()
        tmp = p.with_name(f".{p.name}.terug.tmp")
        tmp.write_bytes(doel.read_bytes())
        _alleen_ik(tmp)
        os.utime(tmp, (st.st_atime, st.st_mtime))
        os.replace(tmp, p)
        uit[p.name] = "terug in de map"
    return uit


def status(map_: Path) -> dict:
    """Hoe het ervoor staat, zonder waarden."""
    lijst = kandidaten(map_)
    prive = hoofdsleutel()
    versleuteld = [p for p in lijst if versleuteld_pad(p).exists()]
    buiten = [p for p in lijst if p.is_symlink()]
    klopt = None
    if prive and versleuteld:
        try:
            for p in versleuteld:
                if p.exists():
                    _controleer(p, prive)
            klopt = True
        except (SleutelFout, OSError, UnicodeDecodeError):
            klopt = False
    windows = is_windows()
    klaar = bool(prive) and is_bewaard() and lijst != [] and len(versleuteld) == len(lijst) \
        and (windows or len(buiten) == len(lijst)) and klopt is not False
    return {"hoofdsleutel": bool(prive), "bewaard": is_bewaard(), "bestanden": len(lijst),
            "heeft_versleuteld": bool(versleutelde(map_)),
            "versleuteld": len(versleuteld), "buiten_de_map": len(buiten), "klopt": klopt,
            "windows": windows, "klaar": klaar or (bool(prive) and is_bewaard() and not lijst)}


def mainframe_map(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    try:
        staat = json.loads((THUIS / ".mainframe-installer" / "staat.json").read_text(encoding="utf-8"))
        if staat.get("map"):
            return Path(staat["map"]).expanduser()
    except (OSError, ValueError):
        pass
    for kandidaat in (THUIS / "Mainframe", THUIS / "Mainframe-2", Path.cwd()):
        if (kandidaat / ".env").exists() or (kandidaat / "CLAUDE.md").exists():
            return kandidaat
    return Path.cwd()


# ---------- de wizard in de browser ----------

WIZARD_HTML = r"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sleutels veilig</title>
<style>
:root{--bg:#0a0e17;--vlak:#121826;--rand:rgba(255,255,255,.1);--tekst:#f3f5f9;--zacht:#9aa4b6;--stil:#687286;--oranje:#ff5a2e;--groen:#3ecf8e;
--sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;min-height:100vh;color:var(--tekst);font:400 16px/1.55 var(--sans);
background:radial-gradient(900px 520px at 50% -140px,rgba(255,90,46,.10),transparent 70%),var(--bg)}
main{max-width:560px;margin:0 auto;padding:7vh 20px 60px}h1{margin:0 0 10px;font-size:32px;line-height:1.15;font-weight:600;letter-spacing:-.02em}
p{margin:0 0 14px;color:var(--zacht)}b{color:var(--tekst)}.kaart{padding:18px;border-radius:14px;background:var(--vlak);border:1px solid var(--rand);margin:18px 0}
.knop{display:inline-flex;align-items:center;justify-content:center;min-height:46px;padding:0 22px;border:0;border-radius:12px;
background:linear-gradient(180deg,#ff5a2e,#e0431f);color:#fff;font:600 15.5px var(--sans);cursor:pointer;margin:6px 8px 0 0}
.knop.licht{background:var(--vlak);border:1px solid var(--rand);color:var(--tekst);font-weight:500}.knop:disabled{opacity:.4;cursor:default}
.sleutel{font:15px/1.5 ui-monospace,Menlo,Consolas,monospace;word-break:break-all;padding:14px;border-radius:10px;background:#0d1320;border:1px solid var(--rand);color:var(--tekst);user-select:all}
label.vink{display:flex;gap:10px;align-items:flex-start;margin:16px 0 4px;color:var(--tekst);cursor:pointer}label.vink input{width:20px;height:20px;margin-top:2px}
input[type=password],input[type=text]{width:100%;height:46px;padding:0 14px;border-radius:10px;border:1px solid var(--rand);background:#0d1320;color:var(--tekst);font:15px ui-monospace,Menlo,Consolas,monospace}
ul{margin:8px 0 0;padding-left:20px;color:var(--zacht)}li{margin:4px 0}.fout{color:#ff8a70;margin-top:12px}.goed{color:var(--groen)}[hidden]{display:none!important}
</style></head><body><main>
<section id="s-start"><h1>Je sleutels veilig</h1>
<p>In je Mainframe staan sleutels: de codes waarmee je Mainframe namens jou bij je mail, agenda en andere programma's mag. Deze wizard maakt ze onleesbaar voor iedereen die je hoofdsleutel niet heeft.</p>
<div class="kaart"><p style="margin:0"><b>Is dit de eerste computer waarop je dit doet?</b></p>
<button class="knop" id="eerste">Ja, maak mijn hoofdsleutel</button>
<button class="knop licht" id="volgende">Nee, ik heb al een hoofdsleutel</button></div></section>

<section id="s-sleutel" hidden><h1>Dit is je hoofdsleutel</h1>
<p>Je ziet hem <b>maar een keer</b>. Bewaar hem nu, dan kan je er altijd bij.</p>
<div class="sleutel" id="sleutel"></div>
<button class="knop" id="kopieer">Kopieer</button>
<div class="kaart"><p style="margin:0"><b>Waar bewaar je hem?</b></p>
<ul><li>In je wachtwoordmanager, zoals NordPass, 1Password of Bitwarden. Maak een nieuw item met de naam <b>Mainframe-hoofdsleutel</b> en plak hem erin.</li>
<li>Of schrijf hem op papier en leg dat op een veilige plek, bijvoorbeeld in een kluis.</li></ul>
<p style="margin:12px 0 0">Zet hem niet in een gesprek met je AI, niet in een mail en niet in een notitie-app zonder wachtwoord.</p></div>
<label class="vink"><input type="checkbox" id="bewaard"> <span>Ik heb mijn hoofdsleutel bewaard</span></label>
<button class="knop" id="verder" disabled>Verder</button></section>

<section id="s-plak" hidden><h1>Plak je hoofdsleutel</h1>
<p>Dezelfde hoofdsleutel als op je eerste computer. Je vindt hem in je wachtwoordmanager onder <b>Mainframe-hoofdsleutel</b>.</p>
<input type="password" id="plak" autocomplete="off" placeholder="64 tekens">
<button class="knop" id="plakverder">Verder</button><div class="fout" id="plakfout"></div></section>

<section id="s-bezig" hidden><h1>Bezig...</h1><p>Je sleutels worden versleuteld en gecontroleerd. Dit duurt meestal minder dan een minuut.</p></section>

<section id="s-klaar" hidden><h1 class="goed">Klaar</h1><p id="klaartekst"></p>
<div class="kaart"><ul id="lijst"></ul></div><p>Je kunt dit venster sluiten. Je Mainframe werkt gewoon zoals altijd.</p></section>

<section id="s-fout" hidden><h1>Dat lukte niet</h1><p class="fout" id="fouttekst"></p><p>Er is niets veranderd aan je bestanden. Probeer het opnieuw, of vraag het in de community.</p>
<button class="knop licht" onclick="location.reload()">Opnieuw</button></section>
</main><script>
const T=location.pathname.split("/")[1];const api=(p,b)=>fetch("/"+T+"/api/"+p,{method:b?"POST":"GET",headers:{"Content-Type":"application/json"},body:b?JSON.stringify(b):undefined}).then(r=>r.json());
const toon=id=>document.querySelectorAll("section").forEach(s=>s.hidden=s.id!==id);
const fout=t=>{document.getElementById("fouttekst").textContent=t;toon("s-fout")};
async function beveilig(){toon("s-bezig");const r=await api("beveilig",{});if(r.fout)return fout(r.fout);
const l=document.getElementById("lijst");l.innerHTML="";for(const [k,v] of Object.entries(r.bestanden)){const li=document.createElement("li");li.textContent=k+": "+v;l.appendChild(li)}
document.getElementById("klaartekst").textContent=r.windows?"Je sleutels hebben nu een versleutelde versie. Op Windows blijft de leesbare versie in je map staan.":"Je sleutels hebben nu een versleutelde versie, en de leesbare versie staat buiten je Mainframe-map.";toon("s-klaar")}
async function sleutelScherm(){const r=await api("sleutel");if(r.fout)return fout(r.fout);document.getElementById("sleutel").textContent=r.sleutel;toon("s-sleutel")}
document.getElementById("eerste").onclick=async()=>{const r=await api("maak",{});if(r.fout)return fout(r.fout);sleutelScherm()};
document.getElementById("volgende").onclick=()=>toon("s-plak");
document.getElementById("kopieer").onclick=async e=>{try{await navigator.clipboard.writeText(document.getElementById("sleutel").textContent)}catch(_){}e.target.textContent="Gekopieerd";setTimeout(()=>e.target.textContent="Kopieer",1800)};
document.getElementById("bewaard").onchange=e=>document.getElementById("verder").disabled=!e.target.checked;
document.getElementById("verder").onclick=async()=>{await api("bewaard",{});document.getElementById("sleutel").textContent="";beveilig()};
document.getElementById("plakverder").onclick=async()=>{const v=document.getElementById("plak").value;const r=await api("plak",{sleutel:v});
if(r.fout){document.getElementById("plakfout").textContent=r.fout;return}document.getElementById("plak").value="";beveilig()};
api("status").then(s=>{if(s.hoofdsleutel&&s.bewaard)beveilig();else if(s.hoofdsleutel)sleutelScherm();else if(s.heeft_versleuteld)toon("s-plak");});
</script></body></html>"""


def wizard(map_: Path, open_browser: bool = True, poort: int = 0) -> int:
    """Een kleine pagina op deze computer (127.0.0.1) die de stappen met je doorloopt."""
    import http.server
    import threading
    import webbrowser

    token = secrets.token_urlsafe(16)
    klaar = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _stuur(self, code: int, body: bytes, soort: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", soort)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: dict) -> None:
            self._stuur(200, json.dumps(data).encode())

        def _pad(self) -> str | None:
            delen = self.path.split("?")[0].strip("/").split("/")
            if not delen or delen[0] != token:
                return None
            return "/".join(delen[1:])

        def do_GET(self):
            pad = self._pad()
            if pad is None:
                return self._stuur(404, b"niet gevonden", "text/plain")
            if pad == "":
                return self._stuur(200, WIZARD_HTML.encode(), "text/html; charset=utf-8")
            if pad == "api/status":
                return self._json(status(map_))
            if pad == "api/sleutel":
                # Alleen zolang hij nog niet als bewaard is aangevinkt.
                if is_bewaard():
                    return self._json({"fout": "je hoofdsleutel is al bewaard en wordt niet nog eens getoond"})
                return self._json({"sleutel": hoofdsleutel() or ""})
            self._stuur(404, b"niet gevonden", "text/plain")

        def do_POST(self):
            pad = self._pad()
            if pad is None or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._stuur(404, b"niet gevonden", "text/plain")
            lengte = min(int(self.headers.get("Content-Length") or 0), 10000)
            try:
                invoer = json.loads(self.rfile.read(lengte) or b"{}")
            except ValueError:
                invoer = {}
            try:
                if pad == "api/maak":
                    maak_hoofdsleutel()
                    return self._json({"ok": True})
                if pad == "api/bewaard":
                    bevestig_bewaard()
                    return self._json({"ok": True})
                if pad == "api/plak":
                    return self._json({"ok": zet_hoofdsleutel(str(invoer.get("sleutel", "")), map_)})
                if pad == "api/beveilig":
                    bestanden = beveilig(map_)
                    klaar.set()
                    return self._json({"bestanden": bestanden, "windows": is_windows()})
            except SleutelFout as fout:
                return self._json({"fout": str(fout)})
            self._stuur(404, b"niet gevonden", "text/plain")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", poort), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/{token}/"
    print(f"De wizard staat open in je browser. Lukt dat niet, open dan: {url}", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if open_browser:
        webbrowser.open(url)
    # Na afloop nog even blijven, zodat de pagina het resultaat kan tonen; anders na een half uur stoppen.
    klaar.wait(timeout=1800)
    time.sleep(5)
    server.shutdown()
    st = status(map_)
    print("Klaar: je sleutels zijn veilig." if st["klaar"] else "De wizard is gestopt; nog niet alles is klaar.")
    return 0 if st["klaar"] else 1


def main(argv: list[str]) -> int:
    actie = argv[1] if len(argv) > 1 else "status"
    map_ = mainframe_map(argv[2] if len(argv) > 2 else None)
    try:
        if actie == "status":
            print(json.dumps(status(map_), indent=1))
        elif actie == "bijwerken":
            uit = bijwerken(map_)
            if any(v.startswith("niet gedaan") for v in uit.values()):
                print("Sleutels: niet alles kon worden bijgewerkt: " + ", ".join(f"{k} ({v})" for k, v in uit.items()))
        elif actie == "terug":
            for k, v in terug(map_).items():
                print(f"{v}: {k}")
        elif actie == "wizard":
            return wizard(map_, open_browser="--geen-browser" not in argv)
        else:
            print(__doc__)
            return 2
    except SleutelFout as fout:
        print(f"Niets veranderd: {fout}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
