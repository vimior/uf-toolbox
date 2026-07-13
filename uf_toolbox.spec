# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for UF Toolbox."""

import os

_spec_dir = os.path.abspath(SPECPATH)
_extra_hidden = ['psutil', 'ctypes']

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
        'plugins', 'plugins.base',
        'common', 'common.common', 'common.state',
        'ui', 'ui.menu', 'ui.log', 'ui.config',
        'tools', 'tools.scanner',
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
