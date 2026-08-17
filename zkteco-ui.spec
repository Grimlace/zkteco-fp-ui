# -*- mode: python ; coding: utf-8 -*-

"""PyInstaller spec for building the ZKTeco attendance UI as a single
standalone executable.

Build with:

    pyinstaller zkteco-ui.spec --noconfirm

The output is a single self-contained binary (onefile mode):

    dist/ZKTecoController              (Linux / macOS)
    dist/ZKTecoController.exe          (Windows)
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("zkteco")
hiddenimports = collect_submodules("zkteco") + collect_submodules("openpyxl")

a = Analysis(
    ["launcher.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ZKTecoController",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)