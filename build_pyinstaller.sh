#!/usr/bin/env bash
# ============================================================
# PyInstaller build script for UF Toolbox
# ============================================================

set -e

pyinstaller uf_toolbox.spec --clean
