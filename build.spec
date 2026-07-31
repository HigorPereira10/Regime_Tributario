# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ("app.py", "."),
    ("src", "src"),
    ("assets", "assets"),
    (".streamlit", ".streamlit"),
]
binaries = []
# app.py e src/*.py são executados dinamicamente pelo Streamlit (via exec do
# arquivo), não importados diretamente por main.py — o rastreador estático do
# PyInstaller não os enxerga, então suas dependências de terceiros precisam
# ser declaradas aqui manualmente.
hiddenimports = ["httpx", "httpcore", "tenacity", "xlsxwriter", "openpyxl"]

for pacote in ("streamlit", "altair", "pydeck"):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pacote)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RegimeTributario",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RegimeTributario",
)
