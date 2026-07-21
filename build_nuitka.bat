@echo off
:: ============================================================
:: Nuitka build script for UF Toolbox
:: ============================================================

setlocal

python -m nuitka ^
    --onefile ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico=icons\uf_toolbox.ico ^
    --output-dir=build_nuitka ^
    --output-filename=UFToolBox.exe ^
    --include-package=themes ^
    --include-package=themes.light ^
    --include-package=themes.dark ^
    --include-package=i18n ^
    --include-package=i18n.zh ^
    --include-package=i18n.en ^
    --include-package=plugins ^
    --include-package=plugins.plugin ^
    --include-package=plugins.plugin_creator ^
    --include-data-files=plugins\plugin_creator\__init__.py=plugins\plugin_creator\__init__.py ^
    --include-data-files=plugins\plugin_creator\plugin_creator.py=plugins\plugin_creator\plugin_creator.py ^
    --include-package=plugins.plugin_guide ^
    --include-data-files=plugins\plugin_guide\__init__.py=plugins\plugin_guide\__init__.py ^
    --include-data-files=plugins\plugin_guide\plugin_guide.py=plugins\plugin_guide\plugin_guide.py ^
    --include-package=plugins.plugin_inspector ^
    --include-data-files=plugins\plugin_inspector\__init__.py=plugins\plugin_inspector\__init__.py ^
    --include-data-files=plugins\plugin_inspector\plugin_inspector.py=plugins\plugin_inspector\plugin_inspector.py ^
    --include-package=common ^
    --include-package=common.common ^
    --include-package=common.state ^
    --include-package=common.infra ^
    --include-package=ui ^
    --include-package=ui.menu ^
    --include-package=ui.log ^
    --include-package=ui.settings ^
    --include-package=ui.about ^
    --include-package=tools ^
    --include-package=tools.manager ^
    --include-package=xarm ^
    --include-package=xarm.core ^
    --include-package=xarm.core.comm ^
    --include-package=xarm.core.config ^
    --include-package=xarm.core.utils ^
    --include-package=xarm.core.wrapper ^
    --include-package=xarm.tools ^
    --include-package=xarm.tools.blockly ^
    --include-package=xarm.wrapper ^
    --include-package=xarm.x3 ^
    --include-data-dir=icons=icons ^
    --include-data-files=tools\tools.json=tools\tools.json ^
    --include-data-files=docs\plugin-guide.md=docs\plugin-guide.md ^
    --include-data-files=docs\plugin-guide-zh.md=docs\plugin-guide-zh.md ^
    --plugin-enable=tk-inter ^
    --include-package=json.encoder ^
    --include-package=json.decoder ^
    --include-package=json.scanner ^
    --include-package=csv ^
    --include-package=xml.etree.ElementTree ^
    --include-package=urllib.request ^
    --include-package=urllib.parse ^
    --include-package=webbrowser ^
    --include-package=configparser ^
    --include-package=logging.handlers ^
    --include-package=zipfile ^
    --include-package=shutil ^
    --include-package=inspect ^
    --include-package=pkgutil ^
    --include-package=importlib.util ^
    --include-package=psutil ^
    --include-package=ctypes ^
    --include-package=tempfile ^
    --include-package=tkinter.font ^
    --include-package=tkinter.ttk ^
    --include-package=tkinter.messagebox ^
    --include-package=tkinter.filedialog ^
    --include-package=tkinter.scrolledtext ^
    --include-package=colorsys ^
    --nofollow-import-to=PIL ^
    --nofollow-import-to=pywinusb ^
    --nofollow-import-to=matplotlib ^
    --nofollow-import-to=numpy ^
    --nofollow-import-to=pandas ^
    --nofollow-import-to=IPython ^
    --nofollow-import-to=jupyter ^
    --nofollow-import-to=zmq ^
    --nofollow-import-to=sqlalchemy ^
    --nofollow-import-to=lxml ^
    --jobs=4 ^
    uf_toolbox.py

:: ---- copy to dist ----
if exist "build_nuitka\UFToolBox.exe" (
    if not exist "dist" mkdir dist
    copy /y "build_nuitka\UFToolBox.exe" "dist\UFToolBox_nuitka.exe"
)

endlocal
