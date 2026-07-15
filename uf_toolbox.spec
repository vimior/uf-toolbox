# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for UF Toolbox."""

import os

_spec_dir = os.path.abspath(SPECPATH)
_extra_hidden = [
    # system / process
    'psutil', 'ctypes', '__future__', 'tempfile',
    # tkinter sub-modules (often missed by analysis)
    'tkinter.font', 'tkinter.ttk', 'tkinter.messagebox',
    'tkinter.filedialog', 'tkinter.scrolledtext', 'colorsys',
    # serialization / data (~150 KB total)
    'json.encoder', 'json.decoder', 'json.scanner',
    'csv', 'xml.etree.ElementTree',
    # network / web (~170 KB total)
    'urllib.request', 'urllib.parse', 'webbrowser',
    # config / file / db (~830 KB total)
    'configparser', 'logging.handlers', 'zipfile', 'shutil',
    # introspection — plugins may load dynamically (~160 KB total)
    'inspect', 'pkgutil', 'importlib.util',
    'xarm', 'xarm.x3', 'xarm.x3.base',
    'xarm.x3.code', 'xarm.x3.thread',
    'xarm.x3.utils', 'xarm.wrapper'
]

a = Analysis(
    ['uf_toolbox.py'],
    pathex=[_spec_dir],
    binaries=[],
    datas=[
        ('icons/uf_toolbox.ico', 'icons'),
        ('icons/uf_toolbox.png', 'icons'),
        ('icons/uf_toolbox_close.png', 'icons'),
        ('icons/uf_toolbox_close_hover.png', 'icons'),
        ('tools/tools.json', 'tools'),
    ],
    hiddenimports=[
        'themes', 'themes.light', 'themes.dark',
        'i18n', 'i18n.zh', 'i18n.en',
        'plugins', 'plugins.plugin',
        'common', 'common.common', 'common.state',
        'ui', 'ui.menu', 'ui.log', 'ui.settings',
        'tools', 'tools.manager'
    ] + _extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL', 'pywinusb', 'matplotlib', 'numpy', 'pandas',
              'IPython', 'jupyter', 'zmq', 'sqlalchemy', 'lxml'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='UFToolBox',
    icon='icons/uf_toolbox.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=['libcrypto*', 'libssl*'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
