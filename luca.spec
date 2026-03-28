# -*- mode: python ; coding: utf-8 -*-
import os, customtkinter as ctk
_ctk_dir = os.path.dirname(ctk.__file__)

# Optional assets — included only when the files exist on disk.
# luca_logo.png and audit_icon.ico are created by running make_icon.py first.
_here = os.path.dirname(os.path.abspath(SPEC))
def _opt(fname, dest='.'):
    path = os.path.join(_here, fname)
    return [(path, dest)] if os.path.exists(path) else []

a = Analysis(
    ['audit_gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        (_ctk_dir, 'customtkinter'),
        *_opt('audit_icon.ico'),
        *_opt('luca_logo.png'),
        *_opt('luca_knowledge.yaml'),
    ],
    hiddenimports=[
        'customtkinter', 'darkdetect',
        'google.genai', 'google.genai.types',
        'google.auth', 'google.auth.transport',
    ],
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
    name='Luca',
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
    icon=['audit_icon.ico'],
)
