@echo off
:: ============================================================
:: PyInstaller build script for UF Toolbox
:: ============================================================

setlocal

pyinstaller uf_toolbox.spec --clean

endlocal
