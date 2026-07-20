#!/usr/bin/env bash
# ============================================================
# Nuitka build script for UF Toolbox
# ============================================================

set -e

python -m nuitka \
    --onefile \
    --windows-console-mode=disable \
    --windows-icon-from-ico=icons/uf_toolbox.ico \
    --output-dir=build_nuitka \
    --output-filename=UFToolBox \
    --include-package=themes \
    --include-package=themes.light \
    --include-package=themes.dark \
    --include-package=i18n \
    --include-package=i18n.zh \
    --include-package=i18n.en \
    --include-package=plugins \
    --include-package=plugins.plugin \
    --include-package=common \
    --include-package=common.common \
    --include-package=common.eventbus \
    --include-package=common.state \
    --include-package=common.store \
    --include-package=common.services \
    --include-package=ui \
    --include-package=ui.menu \
    --include-package=ui.log \
    --include-package=ui.settings \
    --include-package=ui.about \
    --include-package=tools \
    --include-package=tools.manager \
    --include-package=xarm \
    --include-package=xarm.core \
    --include-package=xarm.core.comm \
    --include-package=xarm.core.config \
    --include-package=xarm.core.utils \
    --include-package=xarm.core.wrapper \
    --include-package=xarm.tools \
    --include-package=xarm.tools.blockly \
    --include-package=xarm.wrapper \
    --include-package=xarm.x3 \
    --include-data-dir=icons=icons \
    --include-data-files=tools/tools.json=tools/tools.json \
    --plugin-enable=tk-inter \
    --include-package=json.encoder \
    --include-package=json.decoder \
    --include-package=json.scanner \
    --include-package=csv \
    --include-package=xml.etree.ElementTree \
    --include-package=urllib.request \
    --include-package=urllib.parse \
    --include-package=webbrowser \
    --include-package=configparser \
    --include-package=logging.handlers \
    --include-package=zipfile \
    --include-package=shutil \
    --include-package=inspect \
    --include-package=pkgutil \
    --include-package=importlib.util \
    --include-package=psutil \
    --include-package=ctypes \
    --include-package=tempfile \
    --include-package=tkinter.font \
    --include-package=tkinter.ttk \
    --include-package=tkinter.messagebox \
    --include-package=tkinter.filedialog \
    --include-package=tkinter.scrolledtext \
    --include-package=colorsys \
    --nofollow-import-to=PIL \
    --nofollow-import-to=pywinusb \
    --nofollow-import-to=matplotlib \
    --nofollow-import-to=numpy \
    --nofollow-import-to=pandas \
    --nofollow-import-to=IPython \
    --nofollow-import-to=jupyter \
    --nofollow-import-to=zmq \
    --nofollow-import-to=sqlalchemy \
    --nofollow-import-to=lxml \
    --jobs=4 \
    uf_toolbox.py

# ---- copy to dist ----
if [ -f "build_nuitka/UFToolBox" ]; then
    mkdir -p dist
    cp "build_nuitka/UFToolBox" "dist/UFToolBox_nuitka"
fi
