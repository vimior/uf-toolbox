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
    'configparser', 'logging.handlers', 'zipfile', 'shutil', 'code',
    # introspection — plugins may load dynamically (~160 KB total)
    'inspect', 'pkgutil', 'importlib.util',
    'xarm', 'xarm.core', 'xarm.core.comm',
    'xarm.core.config', 'xarm.core.utils', 'xarm.core.wrapper',
    'xarm.tools', 'xarm.tools.blockly',
    'xarm.wrapper', 'xarm.x3'
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
        ('tools/tools_linux.json', 'tools'),
        ('plugins/plugin_guide', 'plugins/plugin_guide'),
        ('plugins/plugin_creator', 'plugins/plugin_creator'),
        ('plugins/plugin_store', 'plugins/plugin_store'),
        ('plugins/plugin_inspector', 'plugins/plugin_inspector'),
        ('plugins/plugin_debugger', 'plugins/plugin_debugger'),
        ('plugins/task_scheduler', 'plugins/task_scheduler'),
        ('docs/plugin-guide.md', 'docs'),
        ('docs/plugin-guide-zh.md', 'docs'),
        ('docs/task-scheduler.md', 'docs'),
        ('docs/task-scheduler-zh.md', 'docs'),
        ('docs/tool-guide.md', 'docs'),
        ('docs/tool-guide-zh.md', 'docs'),
    ],
    hiddenimports=[
        'themes', 'themes.light', 'themes.dark',
        'i18n', 'i18n.zh', 'i18n.en',
        'plugins', 'plugins.plugin',
        'common', 'common.common', 'common.state',
        'common.infra', 'common.components',
        'ui', 'ui.menu', 'ui.log', 'ui.settings',
        'tools', 'tools.manager',
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
