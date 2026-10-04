# Mainframe installeren op Windows.
#
#   irm https://slimwerken.ai/installeer/installeer.ps1 | iex
#
# Met $env:MF_ACHTERGROND = "1" (zo start Claude hem) draait de installer los
# verder en is dit script meteen klaar.
#
# Zorgt dat er een Python is, haalt de installer op en opent hem in je browser.
# Alle echte stappen doe je in de wizard, met uitleg erbij.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Bronnen = @("https://raw.githubusercontent.com/slimwerken/mainframe-installer/main", "https://slimwerken.ai/installeer")
$WizardZip = "wizard-3e29b7a113.zip"
$Map = Join-Path $env:USERPROFILE ".mainframe-installer"

Write-Host ""
Write-Host "  Mainframe"
Write-Host "  Ik zet de installer voor je klaar. Dat duurt even."
Write-Host ""

function Ververs-Pad {
  $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
  $gebruiker = [Environment]::GetEnvironmentVariable("Path", "User")
  $env:Path = "$machine;$gebruiker"
}

function Vind-Python {
  foreach ($kandidaat in @("py", "python")) {
    $cmd = Get-Command $kandidaat -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    # De lege Store-snelkoppeling van Windows geeft geen versie terug.
    $argumenten = @()
    if ($kandidaat -eq "py") { $argumenten = @("-3") }
    try {
      $versie = & $cmd.Source @argumenten -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
      if ($versie -and [version]$versie -ge [version]"3.10") { return ,@($cmd.Source) + $argumenten }
    } catch { }
  }
  return $null
}

$py = Vind-Python
if (-not $py) {
  Write-Host "  Python installeren (de taal waarin de installer draait)..."
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    & winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Null
  } else {
    $installer = Join-Path $env:TEMP "python-installer.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" -OutFile $installer -UseBasicParsing
    Start-Process $installer -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1" -Wait
  }
  Ververs-Pad
  $py = Vind-Python
  if (-not $py) {
    $los = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $los) { $py = @($los) }
  }
  if (-not $py) {
    Write-Host "  Python kon niet geinstalleerd worden. Installeer het via python.org en start deze regel opnieuw."
    exit 1
  }
}

New-Item -ItemType Directory -Force -Path $Map | Out-Null
$zip = Join-Path $Map "wizard-download.zip"
$gelukt = $false
foreach ($Basis in $Bronnen) {
  try { Invoke-WebRequest "$Basis/$WizardZip" -OutFile $zip -UseBasicParsing; $gelukt = $true; break } catch { }
}
if (-not $gelukt) {
  Write-Host "  Ik kan de installer niet downloaden. Kijk of de wifi aan staat en probeer het opnieuw."
  exit 1
}
$nieuw = Join-Path $Map "wizard.nieuw"
$doel = Join-Path $Map "wizard"
if (Test-Path $nieuw) { Remove-Item -Recurse -Force $nieuw }
Expand-Archive -Path $zip -DestinationPath $nieuw -Force
if (Test-Path $doel) { Remove-Item -Recurse -Force $doel }
Move-Item $nieuw $doel
Remove-Item $zip -Force

$exe = $py[0]
$rest = @()
if ($py.Count -gt 1) { $rest = $py[1..($py.Count - 1)] }
$server = Join-Path $doel "server.py"

if ($env:MF_ACHTERGROND -eq "1") {
  $adres = Join-Path $Map "adres.txt"
  $voor = if (Test-Path $adres) { (Get-Item $adres).LastWriteTime } else { [datetime]::MinValue }
  & $exe @rest $server --los
  for ($i = 0; $i -lt 30; $i++) {
    if ((Test-Path $adres) -and ((Get-Item $adres).LastWriteTime -gt $voor)) { break }
    Start-Sleep 1
  }
  Write-Host ""
  Write-Host "  De installatie staat open in je browser."
  Write-Host ("  MAINFRAME_INSTALLER=" + (Get-Content $adres -ErrorAction SilentlyContinue))
  return
}

Write-Host "  De installer opent nu in je browser."
Write-Host "  Laat dit venster open tot je klaar bent."
& $exe @rest $server
