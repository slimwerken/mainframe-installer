@echo off
title Mainframe installeren
echo.
echo   Mainframe installeren
echo   Laat dit venster open staan. De installatie opent zo in je browser.
echo.
powershell -NoProfile -Command "irm https://slimwerken.ai/installeer/installeer.ps1 | iex"
